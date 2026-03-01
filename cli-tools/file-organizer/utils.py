"""
utils.py
========
Shared utilities for file_organizer.py and subcategorizer.py.
"""

from __future__ import annotations

import os


def remove_empty_dirs(folder: str) -> None:
    """Remove subdirectories that became empty after files were moved out."""
    for root, _dirs, _files in os.walk(folder, topdown=False):
        if root == folder:
            continue  # never remove the root itself
        if not os.listdir(root):
            os.rmdir(root)
