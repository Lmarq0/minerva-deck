"""Safe filesystem browsing for destination selection."""

from __future__ import annotations

import os
import string
from pathlib import Path
from typing import Any, Dict, List

from .config import default_destination
from .routes import validate_emudeck_subfolder


def closest_existing_dir(path: Path) -> Path:
    current = path.expanduser()
    if current.is_file():
        return current.parent
    while not current.exists() and current != current.parent:
        current = current.parent
    if current.exists() and current.is_dir():
        return current
    return Path.home()


def directory_entries(path: Path) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    try:
        children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except OSError:
        return entries
    for child in children:
        if child.is_dir():
            entries.append({"name": child.name, "path": str(child)})
    return entries


def browse_root_payload(path_value: str = "") -> Dict[str, Any]:
    if os.name == "nt" and not path_value:
        drives = []
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if drive.exists():
                drives.append({"name": f"{letter}:\\", "path": str(drive)})
        return {"mode": "root", "current": "", "parent": None, "entries": drives}

    current = closest_existing_dir(Path(path_value or default_destination()))
    parent = str(current.parent) if current != current.parent else None
    return {
        "mode": "root",
        "current": str(current),
        "parent": parent,
        "entries": directory_entries(current),
    }


def browse_subfolder_payload(root_value: str, relative_value: str = "") -> Dict[str, Any]:
    root = closest_existing_dir(Path(root_value or default_destination())).resolve()
    if relative_value.strip():
        relative = validate_emudeck_subfolder(relative_value)
        current = (root / Path(*relative.split("/"))).resolve()
    else:
        current = root

    if root != current and root not in current.parents:
        raise RuntimeError("Subfolder browser cannot leave the ROMs root")
    current = closest_existing_dir(current).resolve()
    if root != current and root not in current.parents:
        current = root

    relative_current = "" if current == root else current.relative_to(root).as_posix()
    parent = None
    if current != root:
        parent_path = current.parent
        parent = "" if parent_path == root else parent_path.relative_to(root).as_posix()

    entries = []
    for entry in directory_entries(current):
        entry_path = Path(entry["path"]).resolve()
        entry["path"] = entry_path.relative_to(root).as_posix()
        entries.append(entry)

    return {
        "mode": "subfolder",
        "root": str(root),
        "current": relative_current,
        "parent": parent,
        "entries": entries,
    }
