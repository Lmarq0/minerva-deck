"""Application paths, remote endpoints, and runtime configuration."""

from __future__ import annotations

import os
from pathlib import Path

from .resources import public_root


APP_NAME = "MiNERVA Deck"
APP_VERSION = "1.0.2"
PUBLIC_ROOT = public_root()
MINERVA_BASE = "https://minerva-archive.org"
MINERVA_CDN = "https://cdn.minerva-archive.org"
USER_AGENT = f"MiNERVA-Deck/{APP_VERSION} (+local selective torrent helper)"
DEFAULT_PORT = 8765
MAX_SEARCH_RESULTS = 48
CATALOG_SCHEMA_VERSION = 6
SEARCH_INDEX_URL = f"{MINERVA_BASE}/assets/index.txt.gz"
TORRENT_LIST_URL = f"{MINERVA_CDN}/torrents/"
ARCHIVE_EXTENSIONS = (
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
)


def app_data_dir() -> Path:
    override = os.environ.get("MINERVA_DECK_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "MinervaDeck"
    base = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    return Path(base) / "minerva-deck"


DATA_DIR = app_data_dir()
CACHE_DIR = DATA_DIR / "cache"
JOB_DIR = DATA_DIR / "jobs"
WEB_PROFILE_DIR = DATA_DIR / "web-profile"


def ensure_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    JOB_DIR.mkdir(parents=True, exist_ok=True)


def default_destination() -> str:
    if os.name == "nt":
        return str(Path.home() / "Emulation" / "roms")
    deck_sd = Path("/run/media/deck/SDeck/Emulation/roms")
    if deck_sd.exists():
        return str(deck_sd)
    return str(Path.home() / "Emulation" / "roms")
