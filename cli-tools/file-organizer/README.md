# File Organizer

A two-script Python toolkit that turns a chaotic downloads folder into a clean,
browsable structure — without ever deleting anything.

| Script | What it does |
|---|---|
| `file_organizer.py` | **Step 1** — sorts by file type, renames with timestamps, isolates duplicates |
| `subcategorizer.py` | **Step 2** — groups files within each type folder into topic subfolders |

---

## Recommended workflow

```bash
# Step 1: sort by file type and rename
python file_organizer.py /path/to/folder --dry-run   # preview first
python file_organizer.py /path/to/folder             # apply

# Step 2: group by topic within each category
python subcategorizer.py /path/to/folder --dry-run   # preview first
python subcategorizer.py /path/to/folder             # apply
```

Always run `--dry-run` first to review what will happen before applying.

---

## Step 1 — file_organizer.py

### What it does

#### Sorts files by extension
Every file is moved into a named subfolder:

| Folder | Extensions |
|---|---|
| `Images/` | `.jpg` `.jpeg` `.png` `.gif` `.bmp` `.svg` `.webp` `.jfif` |
| `Videos/` | `.mp4` `.mov` `.avi` `.mkv` `.flv` `.wmv` |
| `Documents/` | `.pdf` `.doc` `.docx` `.txt` `.xls` `.xlsx` `.pptx` `.csv` `.epub` `.md` `.html` and more |
| `Audio/` | `.mp3` `.wav` `.aac` `.flac` `.ogg` |
| `Archives/` | `.zip` `.tar` `.tar.gz` `.tar.bz2` `.rar` `.7z` `.tgz` `.gz` `.bz2` |
| `Code/` | `.py` `.js` `.ts` `.json` `.sh` `.cpp` `.java` `.go` `.rb` and more |
| `Installables/` | `.exe` `.msi` `.msix` `.dmg` `.pkg` `.deb` `.rpm` `.vbox-extpack` |
| `Logs/` | `.log` `.slack` |
| `Others/` | Anything not matched above |

#### Renames files with timestamps
Every file is renamed to reflect its original creation date:

```
old name:  report.pdf
new name:  report_2024-03-15_09-22-44.pdf
```

The timestamp comes from the file's creation date (falls back to last-modified
on Linux/WSL where birth time is not always available).

#### Detects and isolates duplicates
Files with identical content are moved to a `Duplicates/` subfolder — the
original is always kept, nothing is deleted.

```
Documents/
├── report_2024-03-15_09-22-44.pdf             ← original kept here
└── Duplicates/
    └── report_copy_2024-03-15_09-22-44.pdf    ← duplicate isolated here
```

Duplicate detection is content-based (MD5 fingerprint), so it catches copies
regardless of filename. Large files (over 10 MB) are sampled rather than fully
read to keep things fast.

### Usage

```bash
python file_organizer.py <folder> [--dry-run]
```

```bash
# Preview changes without touching anything
python file_organizer.py ~/Downloads --dry-run

# Organize a Windows Downloads folder from WSL
python file_organizer.py /mnt/d/Downloads

# Organize the current directory
python file_organizer.py .
```

### Output

```
       Move+Rename: invoice.pdf
          -> Documents/invoice_2024-01-10_14-30-00.pdf

[DUP]  Move+Rename: invoice_copy.pdf
          -> Documents/Duplicates/invoice_copy_2024-01-10_14-30-00.pdf

Done.
  Moved     : 312
  Renamed   : 48
  Duplicates: 27
```

---

## Step 2 — subcategorizer.py

### What it does

After `file_organizer.py` has sorted files by type, `subcategorizer.py` does a
second pass — grouping files within each category folder into topic subfolders
using keyword matching on filenames.

For example, `Documents/` gets broken down into:

```
Documents/
├── Travel/          ← flights, boarding passes, e-tickets
├── Finance_Banking/ ← bank statements, salary slips, NPS
├── Tax/             ← income tax returns, P11D, Form 16
├── Medical/         ← NHS letters, vaccinations, appointments
├── Legal/           ← NDAs, agreements, contracts
├── Property_Home/   ← rent receipts, maintenance invoices
├── Insurance/       ← policy documents, NCD certificates
├── Immigration/     ← right to work, CoS, visas, BRP
├── Government_ID/   ← Aadhaar, PAN card, passport scans
├── Work_Employment/ ← offer letters, experience letters
├── CV_Resume/       ← CVs and resumes
├── EV_Charging/     ← OCPP specs, charger documentation
├── Education/       ← university papers, assessments, courses
├── Certificates/    ← AWS, LinkedIn, completion certificates
├── Books_Technical/ ← technical books and whitepapers
└── Misc/            ← files that matched no rule
```

Other categories get similar treatment:

- **`Images/`** → `ID_Documents/`, `Medical/`, `Property_Home/`, `Work_Diagrams/`, `Project_Assets/`, `Personal/`
- **`Installables/`** → `Development/`, `Communication/`, `Security_Remote/`, `Browsers_Media/`, `Office_Apps/`, `System_Utils/`, `Printers/`
- **`Others/`** → `PHP_Web/`, `Protobuf_CPP/`, `Build_Artifacts/`, `Config_Data/`, `System_Junk/`

### How matching works

Each file's name is checked against a list of keywords for each subfolder. The
first matching rule wins. Files that match nothing go into `Misc/`.

Rules are defined in the `RULES` dictionary at the top of `subcategorizer.py`
and are easy to extend — add a new tuple with a folder name and keywords:

```python
"Documents": [
    ("Travel", ["air_india", "flight", "boarding", "eticket"]),
    ("Tax",    ["income_tax", "itr", "p11d"]),
    # add more rules here ...
],
```

### Usage

```bash
python subcategorizer.py <folder> [--dry-run]
```

```bash
# Preview groupings without moving anything
python subcategorizer.py /mnt/d/Downloads --dry-run

# Apply
python subcategorizer.py /mnt/d/Downloads
```

### Output

```
============================================================
  Documents/
============================================================
       report.pdf
        -> Finance_Banking/
  [MISC] unknown_file.pdf
        -> Misc/

Done.
  Subcategorized : 4339
  Sent to Misc/  : 1471
```

Files tagged `[MISC]` had no keyword match. Review `Misc/` manually after
running to either move files by hand or add new rules for patterns you notice.

---

## Requirements

- Python 3.8 or later
- No third-party packages — standard library only

---

## How duplicate detection works

Each file is fingerprinted using MD5:

- **Small files (≤ 10 MB):** the entire file is hashed.
- **Large files (> 10 MB):** the first 512 KB + exact byte count + last 512 KB
  are hashed. This keeps large ISOs and archives fast to process.

If two files produce the same fingerprint, the second is treated as a duplicate.
The first file seen is always the one kept in the main category folder.

> **Note:** Only exact duplicates are detected. Near-duplicates (e.g. the same
> photo at different quality, or a document with minor edits) are treated as
> different files.

---

## Re-running safely

Both scripts are safe to re-run on an already-organized folder:

- `file_organizer.py` renames files already in the right category in place
  (does not move them again). `Duplicates/` subfolders are skipped.
- `subcategorizer.py` only processes direct children of each category folder,
  so files already moved into topic subfolders are untouched.
- Empty directories are cleaned up automatically after each run.
