"""
file_organizer.py
=================
Recursively organizes a messy folder by:

  1. Categorizing every file by extension into named subfolders
     (Images, Documents, Archives, Installables, Logs, ...).
  2. Renaming each file to <clean-stem>_<YYYY-MM-DD_HH-MM-SS><ext>
     using the file's creation (or modification) timestamp.
  3. Detecting duplicates via MD5 fingerprinting and moving them into
     a per-category Duplicates/ subfolder - nothing is ever deleted.
  4. Previewing all planned changes with --dry-run before touching files.

Usage
-----
    python file_organizer.py <folder> [--dry-run]
"""

from __future__ import annotations

import os
import re
import shutil
import argparse
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set

from utils import remove_empty_dirs

# ---------------------------------------------------------------------------
# Category map: folder name -> lowercase extensions that belong to it.
# Files whose extension is not listed here land in "Others".
# ---------------------------------------------------------------------------
CATEGORIES: Dict[str, List[str]] = {
    "Images":       [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".jfif"],
    "Videos":       [".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv"],
    "Documents":    [".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx", ".pptx", ".ppt",
                     ".csv", ".epub", ".md", ".odt", ".arff", ".ics", ".html", ".htm"],
    "Audio":        [".mp3", ".wav", ".aac", ".flac", ".ogg"],
    "Archives":     [".zip", ".tar", ".rar", ".7z", ".tgz", ".gz", ".bz2"],
    "Code":         [".py", ".js", ".ts", ".css", ".json", ".sh", ".cpp", ".c",
                     ".java", ".go", ".rb"],
    "Installables": [".exe", ".msi", ".msix", ".msp", ".dmg", ".pkg", ".deb", ".rpm",
                     ".vbox-extpack"],
    "Logs":         [".log", ".slack"],
}

# Reverse lookup built once at import time for O(1) ext -> category resolution.
_EXT_TO_CATEGORY: Dict[str, str] = {
    ext: cat for cat, exts in CATEGORIES.items() for ext in exts
}

# Compound extensions that os.path.splitext cannot split correctly.
_COMPOUND_EXTS = (".tar.gz", ".tar.bz2")

# Subfolder name used for detected duplicates inside each category folder.
DUPLICATES_DIR = "Duplicates"

# Hashing tuning: files above SAMPLE_THRESHOLD are fingerprinted by reading
# SAMPLE_SIZE bytes from the start and end plus the exact byte count.
SAMPLE_THRESHOLD = 10 * 1024 * 1024   # 10 MB
SAMPLE_SIZE = 512 * 1024               # 512 KB per sampled region
CHUNK_SIZE = 8_192                     # streaming read size for small files


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class Stats:
    """Running totals updated as files are processed."""
    moved: int = 0
    renamed: int = 0
    duplicates: int = 0


@dataclass
class _RunContext:
    """Shared mutable state passed through the processing pipeline."""
    folder: str
    dry_run: bool
    seen_hashes: Dict[str, str]
    created_dirs: Set[str]
    stats: Stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_stem_ext(filename: str):
    """Return (stem, ext), correctly handling compound extensions like .tar.gz."""
    lower = filename.lower()
    for compound in _COMPOUND_EXTS:
        if lower.endswith(compound):
            return filename[: -len(compound)], compound
    return os.path.splitext(filename)


def _walk_skip_duplicates(folder: str):
    """Yield os.walk tuples, pruning Duplicates/ subfolders from traversal."""
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d != DUPLICATES_DIR]
        yield root, dirs, files


def get_category(filepath: str) -> str:
    """Map a file path to its destination category folder name."""
    filename = os.path.basename(filepath).lower()
    # Compound extensions must be checked before the single-ext dict lookup.
    if filename.endswith(_COMPOUND_EXTS):
        return "Archives"
    ext = os.path.splitext(filename)[1]
    return _EXT_TO_CATEGORY.get(ext, "Others")


def get_file_hash(filepath: str) -> Optional[str]:
    """
    Return an MD5 hex digest used for duplicate detection.

    Small files are hashed in full. Large files are fingerprinted from
    start + end chunks plus their exact byte count.
    Returns None on any I/O error so the caller treats the file as unique.
    """
    hasher = hashlib.md5()
    try:
        with open(filepath, "rb") as file_obj:
            # Seek to end for size in one syscall - avoids a separate
            # os.path.getsize() call and the TOCTOU race it would introduce.
            size = file_obj.seek(0, 2)
            file_obj.seek(0)
            if size <= SAMPLE_THRESHOLD:
                while chunk := file_obj.read(CHUNK_SIZE):
                    hasher.update(chunk)
            else:
                hasher.update(file_obj.read(SAMPLE_SIZE))
                hasher.update(size.to_bytes(8, "little"))
                file_obj.seek(-SAMPLE_SIZE, 2)
                hasher.update(file_obj.read(SAMPLE_SIZE))
    except OSError as err:
        print(f"  Warning: cannot hash '{filepath}': {err}")
        return None
    return hasher.hexdigest()


def get_creation_dt(filepath: str) -> datetime:
    """
    Return the best available creation timestamp for a file.

    Uses st_birthtime on platforms that expose it (macOS, some BSDs).
    Falls back to st_mtime on Linux / WSL where birth time is not always
    surfaced by the underlying filesystem.
    """
    stat = os.stat(filepath)
    ts = getattr(stat, "st_birthtime", None) or stat.st_mtime
    return datetime.fromtimestamp(ts)


def clean_name(name: str) -> str:
    """
    Sanitize a filename stem for safe, readable use.

    Replaces every run of non-alphanumeric/non-hyphen characters with a
    single underscore in one pass, then strips leading/trailing underscores.
    """
    return re.sub(r"[^\w\-]+", "_", name).strip("_")


def make_new_filename(filepath: str) -> str:
    """
    Build the destination filename: <clean-stem>_<YYYY-MM-DD_HH-MM-SS><ext>.

    The timestamp reflects when the file was originally created so the name
    carries meaningful context about the file's age.
    """
    filename = os.path.basename(filepath)
    stem, ext = _split_stem_ext(filename)
    dt_str = get_creation_dt(filepath).strftime("%Y-%m-%d_%H-%M-%S")
    return f"{clean_name(stem)}_{dt_str}{ext}"


def unique_path(path: str) -> str:
    """
    Return a collision-free path by appending _1, _2, ... when necessary.

    Only called during live runs (not dry-run) so all existence checks
    reflect the real filesystem state.
    """
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base}_{i}{ext}"):
        i += 1
    return f"{base}_{i}{ext}"


def _log_action(
        filepath: str,
        dest: str,
        folder: str,
        is_dup: bool,
        already_in_place: bool) -> None:
    """Print the move/rename action being taken for a file."""
    tag = "[DUP]  " if is_dup else "       "
    action = "Rename" if already_in_place else "Move+Rename"
    print(f"  {tag}{action}: {os.path.basename(filepath)}")
    print(f"          -> {os.path.relpath(dest, folder)}")


def _process_file(filepath: str, ctx: _RunContext) -> None:
    """
    Categorize, fingerprint, rename and move a single file.

    Updates ctx.seen_hashes, ctx.created_dirs, and ctx.stats in place.
    """
    category = get_category(filepath)
    file_hash = get_file_hash(filepath)
    is_dup = file_hash is not None and file_hash in ctx.seen_hashes
    if file_hash and not is_dup:
        ctx.seen_hashes[file_hash] = filepath

    dest_dir = (
        os.path.join(ctx.folder, category, DUPLICATES_DIR)
        if is_dup
        else os.path.join(ctx.folder, category)
    )
    new_filename = make_new_filename(filepath)
    dest = (
        unique_path(os.path.join(dest_dir, new_filename))
        if not ctx.dry_run
        else os.path.join(dest_dir, new_filename)
    )

    already_in_place = os.path.dirname(filepath) == dest_dir
    _log_action(filepath, dest, ctx.folder, is_dup, already_in_place)

    if not ctx.dry_run:
        if dest_dir not in ctx.created_dirs:
            os.makedirs(dest_dir, exist_ok=True)
            ctx.created_dirs.add(dest_dir)
        shutil.move(filepath, dest)

    if is_dup:
        ctx.stats.duplicates += 1
    elif already_in_place:
        ctx.stats.renamed += 1
    else:
        ctx.stats.moved += 1


# ---------------------------------------------------------------------------
# Main organizer
# ---------------------------------------------------------------------------

def organize(folder: str, dry_run: bool = False) -> None:
    """
    Organize all files under *folder* into category subfolders.

    For each file the steps are:
      1. Determine category from extension (O(1) dict lookup).
      2. Fingerprint the content for duplicate detection.
      3. Build a clean, timestamped destination filename.
      4. Move/rename on disk unless *dry_run* is True.

    Duplicates land in <category>/Duplicates/ - nothing is ever deleted.
    """
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a valid directory.")
        return

    if dry_run:
        print("[DRY RUN] No files will be moved or renamed.\n")

    # Collect all paths up-front so in-flight moves don't confuse the walk.
    script_name = os.path.basename(__file__)
    all_files = [
        os.path.join(root, f)
        for root, _dirs, files in _walk_skip_duplicates(folder)
        for f in files
        if f != script_name
    ]

    ctx = _RunContext(
        folder=folder,
        dry_run=dry_run,
        seen_hashes={},
        created_dirs=set(),
        stats=Stats(),
    )

    for filepath in all_files:
        # Guard against files that vanish between collection and processing.
        if not os.path.isfile(filepath):
            continue
        _process_file(filepath, ctx)

    if not dry_run:
        remove_empty_dirs(folder)

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{prefix}Done.")
    print(f"  Moved     : {ctx.stats.moved}")
    print(f"  Renamed   : {ctx.stats.renamed}")
    print(f"  Duplicates: {ctx.stats.duplicates}")
    if dry_run:
        print("\nRun without --dry-run to apply changes.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Organize files in a folder by type, renaming with timestamps.",
    )
    parser.add_argument("folder", help="Path to the folder to organize")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without moving or renaming any files",
    )
    args = parser.parse_args()
    organize(args.folder, dry_run=args.dry_run)
