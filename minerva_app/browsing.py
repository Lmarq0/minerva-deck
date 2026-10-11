"""Validate folders chosen in the system folder dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

from .config import default_destination
from .routes import validate_emudeck_subfolder


# Opens the system folder dialog: (title, start folder) -> chosen path or "".
FolderPicker = Callable[[str, str], str]


def closest_existing_dir(path: Path) -> Path:
    current = path.expanduser()
    if current.is_file():
        return current.parent
    while not current.exists() and current != current.parent:
        current = current.parent
    if current.exists() and current.is_dir():
        return current
    return Path.home()


def pick_folder_payload(
    picker: FolderPicker, mode: str, root_value: str, current_value: str
) -> Dict[str, Optional[str]]:
    """Run the picker for the ROMs root or a system subfolder inside it."""
    root = closest_existing_dir(Path(root_value or default_destination()))
    if mode == "root":
        chosen = picker("Choose your EmuDeck ROMs folder", str(root))
        return {"path": chosen or None}
    if mode != "subfolder":
        raise RuntimeError("Unknown folder picker mode")

    start = root
    if current_value.strip():
        start = closest_existing_dir(root / Path(*validate_emudeck_subfolder(current_value).split("/")))
    chosen = picker("Choose the system folder", str(start))
    if not chosen:
        return {"path": None}
    resolved_root = root.resolve()
    resolved = Path(chosen).resolve()
    if resolved == resolved_root or resolved_root not in resolved.parents:
        raise RuntimeError(f"Choose a folder inside {resolved_root}")
    return {"path": validate_emudeck_subfolder(resolved.relative_to(resolved_root).as_posix())}
