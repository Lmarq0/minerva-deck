"""Box art from libretro-thumbnails, cached on disk.

libretro names its folders after No-Intro/Redump systems and its images
after the exact dump names, so catalog entries map onto it directly.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from pathlib import Path
from typing import List, Optional
from urllib.error import HTTPError
from urllib.parse import quote

from .config import CACHE_DIR
from .utils import fetch_bytes


THUMBNAILS_URL = "https://thumbnails.libretro.com"
COVER_DIR = CACHE_DIR / "covers"
MISS_RETRY_SECONDS = 7 * 24 * 60 * 60
CACHE_LIMIT_BYTES = 300 * 1024 * 1024
PRUNE_EVERY = 50

_lock = threading.Lock()
_saves = 0


def libretro_name(value: str) -> str:
    # libretro replaces characters that are invalid in file names.
    return re.sub(r'[&*/:`<>?\\|"]', "_", value)


def system_candidates(system: str) -> List[str]:
    # "Sony - PlayStation (PS one Classics) (PSN)" -> also "Sony - PlayStation".
    base = re.sub(r"\s*\(.*$", "", system).strip()
    return list(dict.fromkeys(name for name in (system, base) if name))


def title_candidates(title: str) -> List[str]:
    # "Game (USA) (Virtual Console)" -> also "Game (USA)" and "Game".
    first_tag = re.match(r"^(.*?\([^)]*\))", title)
    base = re.split(r"\s*[(\[]", title, 1)[0].strip()
    return list(dict.fromkeys(
        name for name in (title, first_tag.group(1) if first_tag else "", base) if name
    ))


def _prune() -> None:
    files = sorted(
        (path for path in COVER_DIR.iterdir() if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    total = sum(path.stat().st_size for path in files)
    for path in files:
        if total <= CACHE_LIMIT_BYTES:
            break
        total -= path.stat().st_size
        path.unlink(missing_ok=True)


def cover_image(system: str, title: str) -> Optional[bytes]:
    """Return PNG bytes for a game's box art, or None if libretro has none."""
    global _saves
    key = hashlib.sha1(f"{system}\n{title}".encode("utf-8")).hexdigest()
    image_path = COVER_DIR / f"{key}.png"
    miss_path = COVER_DIR / f"{key}.miss"
    if image_path.is_file():
        return image_path.read_bytes()
    if miss_path.is_file() and time.time() - miss_path.stat().st_mtime < MISS_RETRY_SECONDS:
        return None

    image = None
    for system_name in system_candidates(system):
        for title_name in title_candidates(title):
            url = "/".join(
                quote(libretro_name(part))
                for part in (system_name, "Named_Boxarts", f"{title_name}.png")
            )
            try:
                image = fetch_bytes(f"{THUMBNAILS_URL}/{url}", timeout=15)
                break
            except HTTPError as exc:
                if exc.code != 404:
                    return None  # Server trouble: don't record a miss.
            except OSError:
                return None  # Offline: try again next time.
        if image:
            break

    COVER_DIR.mkdir(parents=True, exist_ok=True)
    if image is None:
        miss_path.touch()
        return None
    image_path.write_bytes(image)
    with _lock:
        _saves += 1
        if _saves % PRUNE_EVERY == 0:
            _prune()
    return image
