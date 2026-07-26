"""Locate packaged assets and native libraries in source and frozen builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


def resource_root() -> Path:
    override = os.environ.get("MINERVA_RESOURCE_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    executable_root = Path(sys.executable).resolve().parent
    for root in (Path(__file__).resolve().parent.parent, executable_root):
        if (root / "public" / "index.html").is_file():
            return root
    return Path(__file__).resolve().parent.parent


def public_root() -> Path:
    return resource_root() / "public"


def native_library_path(stem: str) -> Optional[Path]:
    names = (
        (f"{stem}.dll", f"lib{stem}.dll")
        if os.name == "nt"
        else (f"lib{stem}.so", f"lib{stem}.so.13", f"lib{stem}.so.19")
    )
    roots = (
        resource_root(),
        resource_root() / "native",
        resource_root() / "build" / "native",
        Path(sys.executable).resolve().parent,
    )
    for root in roots:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return candidate
        pattern = f"*{stem}*.dll" if os.name == "nt" else f"lib{stem}.so*"
        for candidate in sorted(root.glob(pattern)):
            if candidate.is_file():
                return candidate
    return None
