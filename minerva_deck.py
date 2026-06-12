#!/usr/bin/env python3
"""
MiNERVA Deck

A local Steam Deck friendly web app for selecting one file from a MiNERVA
grouped torrent, downloading only that torrent entry with aria2c, and moving
or extracting the result into a user-selected directory.
"""

from __future__ import annotations

import argparse
import gzip
import html.parser
import json
import mimetypes
import os
import posixpath
import queue
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen


APP_NAME = "MiNERVA Deck"
APP_ROOT = Path(__file__).resolve().parent
PUBLIC_ROOT = APP_ROOT / "public"
MINERVA_BASE = "https://minerva-archive.org"
MINERVA_CDN = "https://cdn.minerva-archive.org"
USER_AGENT = "MiNERVA-Deck/1.0 (+local selective torrent helper)"
DEFAULT_PORT = 8765
MAX_SEARCH_RESULTS = 100
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


EMUDECK_ROUTE_RULES: List[Tuple[str, List[str], str]] = [
    ("Nintendo Wii U", ["nintendo", "wii u"], "wiiu/roms"),
    ("Nintendo Wii", ["nintendo", "wii"], "wii"),
    ("Nintendo GameCube", ["nintendo", "gamecube"], "gc"),
    ("Nintendo Switch", ["nintendo", "switch"], "switch"),
    ("Nintendo 3DS", ["nintendo", "3ds"], "n3ds"),
    ("Nintendo DSi", ["nintendo", "dsi"], "nds"),
    ("Nintendo DS", ["nintendo", "ds"], "nds"),
    ("Nintendo 64DD", ["nintendo", "64dd"], "n64dd"),
    ("Nintendo 64", ["nintendo", "64"], "n64"),
    ("Nintendo Game Boy Advance", ["nintendo", "game boy advance"], "gba"),
    ("Nintendo Game Boy Color", ["nintendo", "game boy color"], "gbc"),
    ("Nintendo Game Boy", ["nintendo", "game boy"], "gb"),
    ("Nintendo Virtual Boy", ["nintendo", "virtual boy"], "virtualboy"),
    ("Nintendo Pokemon Mini", ["nintendo", "pokemon mini"], "pokemini"),
    ("Nintendo Satellaview", ["nintendo", "satellaview"], "satellaview"),
    ("Nintendo Sufami Turbo", ["nintendo", "sufami"], "sufami"),
    ("Nintendo Super Famicom", ["nintendo", "super famicom"], "sfc"),
    ("Nintendo Super Nintendo", ["nintendo", "super nintendo"], "snes"),
    ("Nintendo SNES", ["nintendo", "snes"], "snes"),
    ("Nintendo Famicom Disk System", ["nintendo", "famicom disk"], "fds"),
    ("Nintendo Famicom", ["nintendo", "famicom"], "famicom"),
    ("Nintendo NES", ["nintendo", "entertainment system"], "nes"),
    ("Nintendo NES", ["nintendo", "nes"], "nes"),
    ("Nintendo Game and Watch", ["nintendo", "game and watch"], "gameandwatch"),
    ("Sega NAOMI 2", ["sega", "naomi 2"], "naomi2"),
    ("Sega NAOMI GD-ROM", ["sega", "naomi gd"], "naomigd"),
    ("Sega NAOMI", ["sega", "naomi"], "naomi"),
    ("Sega Atomiswave", ["atomiswave"], "atomiswave"),
    ("Sega Model 2", ["sega", "model 2"], "model2"),
    ("Sega Model 3", ["sega", "model 3"], "model3"),
    ("Sega Dreamcast", ["sega", "dreamcast"], "dreamcast"),
    ("Sega Saturn", ["sega", "saturn"], "saturn"),
    ("Sega CD", ["sega", "mega cd"], "megacd"),
    ("Sega CD", ["sega", "sega cd"], "segacd"),
    ("Sega 32X", ["sega", "32x"], "sega32x"),
    ("Sega Game Gear", ["sega", "game gear"], "gamegear"),
    ("Sega Genesis", ["sega", "genesis"], "genesis"),
    ("Sega Mega Drive", ["sega", "mega drive"], "megadrive"),
    ("Sega Master System", ["sega", "master system"], "mastersystem"),
    ("Sega SG-1000", ["sega", "sg 1000"], "sg-1000"),
    ("Sony PlayStation Portable", ["sony", "playstation portable"], "psp"),
    ("Sony PSP", ["sony", "psp"], "psp"),
    ("Sony PlayStation Vita", ["sony", "playstation vita"], "psvita/ux0"),
    ("Sony PlayStation 4", ["sony", "playstation 4"], "ps4"),
    ("Sony PlayStation 3", ["sony", "playstation 3"], "ps3"),
    ("Sony PlayStation 2", ["sony", "playstation 2"], "ps2"),
    ("Sony PlayStation", ["sony", "playstation"], "psx"),
    ("Microsoft Xbox 360 Live Arcade", ["xbox 360", "live arcade"], "xbox360/roms/xbla"),
    ("Microsoft Xbox 360", ["microsoft", "xbox 360"], "xbox360/roms"),
    ("Microsoft Xbox", ["microsoft", "xbox"], "xbox"),
    ("Microsoft MSX Turbo R", ["microsoft", "msx turbo"], "msxturbor"),
    ("Microsoft MSX2", ["microsoft", "msx2"], "msx2"),
    ("Microsoft MSX1", ["microsoft", "msx1"], "msx1"),
    ("Microsoft MSX", ["microsoft", "msx"], "msx"),
    ("NEC PC Engine CD", ["nec", "pc engine cd"], "pcenginecd"),
    ("NEC TurboGrafx-CD", ["nec", "turbografx cd"], "tg-cd"),
    ("NEC SuperGrafx", ["nec", "supergrafx"], "supergrafx"),
    ("NEC PC-9800", ["nec", "pc 9800"], "pc98"),
    ("NEC PC-9800", ["nec", "pc 98"], "pc98"),
    ("NEC PC-8800", ["nec", "pc 8800"], "pc88"),
    ("NEC PC-FX", ["nec", "pc fx"], "pcfx"),
    ("NEC PC Engine", ["nec", "pc engine"], "pcengine"),
    ("NEC TurboGrafx-16", ["nec", "turbografx 16"], "tg16"),
    ("SNK Neo Geo Pocket Color", ["snk", "neo geo pocket color"], "ngpc"),
    ("SNK Neo Geo Pocket", ["snk", "neo geo pocket"], "ngp"),
    ("SNK Neo Geo CD", ["snk", "neo geo cd"], "neogeocd"),
    ("SNK Neo Geo MVS", ["snk", "neo geo mvs"], "fbneo"),
    ("SNK Neo Geo", ["snk", "neo geo"], "neogeo"),
    ("Bandai WonderSwan Color", ["bandai", "wonderswan color"], "wonderswancolor"),
    ("Bandai WonderSwan", ["bandai", "wonderswan"], "wonderswan"),
    ("Bandai SuFami Turbo", ["bandai", "sufami"], "sufami"),
    ("Atari Jaguar CD", ["atari", "jaguar cd"], "atarijaguarcd"),
    ("Atari Jaguar", ["atari", "jaguar"], "atarijaguar"),
    ("Atari Lynx", ["atari", "lynx"], "atarilynx"),
    ("Atari 7800", ["atari", "7800"], "atari7800"),
    ("Atari 5200", ["atari", "5200"], "atari5200"),
    ("Atari 2600", ["atari", "2600"], "atari2600"),
    ("Atari 800", ["atari", "800"], "atari800"),
    ("Atari ST", ["atari", "st"], "atarist"),
    ("Panasonic 3DO", ["panasonic", "3do"], "3do"),
    ("Philips CD-i", ["philips", "cd i"], "cdimono1"),
    ("Philips Videopac", ["philips", "videopac"], "videopac"),
    ("Magnavox Odyssey2", ["magnavox", "odyssey2"], "odyssey2"),
    ("Mattel Intellivision", ["mattel", "intellivision"], "intellivision"),
    ("Commodore Amiga CD32", ["commodore", "amiga cd32"], "amigacd32"),
    ("Commodore Amiga 1200", ["commodore", "amiga 1200"], "amiga1200"),
    ("Commodore Amiga 600", ["commodore", "amiga 600"], "amiga600"),
    ("Commodore Amiga", ["commodore", "amiga"], "amiga"),
    ("Commodore 64", ["commodore", "64"], "c64"),
    ("Commodore 16", ["commodore", "16"], "c16"),
    ("Commodore VIC-20", ["commodore", "vic 20"], "vic20"),
    ("Amstrad CPC", ["amstrad", "cpc"], "amstradcpc"),
    ("Amstrad GX4000", ["amstrad", "gx4000"], "gx4000"),
    ("Apple IIgs", ["apple", "iigs"], "apple2gs"),
    ("Apple IIgs", ["apple", "ii gs"], "apple2gs"),
    ("Apple II", ["apple", "ii"], "apple2"),
    ("Apple Macintosh", ["apple", "macintosh"], "macintosh"),
    ("Fujitsu FM Towns", ["fujitsu", "fm towns"], "fmtowns"),
    ("Sharp X68000", ["sharp", "x68000"], "x68000"),
    ("Sharp X1", ["sharp", "x1"], "x1"),
    ("Sinclair ZX Spectrum", ["sinclair", "zx spectrum"], "zxspectrum"),
    ("Sinclair ZX81", ["sinclair", "zx81"], "zx81"),
    ("ColecoVision", ["coleco", "colecovision"], "colecovision"),
    ("Vectrex", ["vectrex"], "vectrex"),
    ("Watara Supervision", ["watara", "supervision"], "supervision"),
    ("Tiger Game.com", ["tiger", "game com"], "gamecom"),
    ("VTech V.Smile", ["vtech", "v smile"], "vsmile"),
    ("Doom", ["doom"], "doom"),
    ("Pico-8", ["pico 8"], "pico8"),
    ("ScummVM", ["scummvm"], "scummvm"),
    ("EasyRPG", ["easyrpg"], "easyrpg"),
    ("DOS", ["dos"], "dos"),
    ("MAME", ["mame"], "arcade"),
    ("FinalBurn Neo", ["finalburn neo"], "fbneo"),
    ("Final Burn Neo", ["final burn neo"], "fbneo"),
]


def app_data_dir() -> Path:
    override = os.environ.get("MINERVA_DECK_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "MinervaDeck"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "minerva-deck"


DATA_DIR = app_data_dir()
CACHE_DIR = DATA_DIR / "cache"
JOB_DIR = DATA_DIR / "jobs"


def ensure_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    JOB_DIR.mkdir(parents=True, exist_ok=True)


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def now_ms() -> int:
    return int(time.time() * 1000)


def command_path(name: str) -> Optional[str]:
    local_candidates = [
        APP_ROOT / "bin" / name,
        APP_ROOT / "vendor" / "aria2" / "usr" / "bin" / name,
    ]
    if os.name == "nt":
        local_candidates.extend(
            [
                APP_ROOT / "bin" / f"{name}.exe",
                APP_ROOT / "vendor" / "aria2" / "usr" / "bin" / f"{name}.exe",
            ]
        )
    for candidate in local_candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def process_env() -> Dict[str, str]:
    env = os.environ.copy()
    vendor_lib = APP_ROOT / "vendor" / "aria2" / "usr" / "lib"
    if vendor_lib.exists():
        current = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{vendor_lib}:{current}" if current else str(vendor_lib)
    return env


def find_7z() -> Optional[str]:
    for candidate in ("7zz", "7z", "7za"):
        path = command_path(candidate)
        if path:
            return path
    return None


def default_destination() -> str:
    if os.name == "nt":
        return str(Path.home() / "Emulation" / "roms")
    deck_sd = Path("/run/media/deck/SDeck/Emulation/roms")
    if deck_sd.exists():
        return str(deck_sd)
    return str(Path.home() / "Emulation" / "roms")


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
        if not child.is_dir():
            continue
        entries.append({"name": child.name, "path": str(child)})
    return entries


def browse_root_payload(path_value: str = "") -> Dict[str, Any]:
    if os.name == "nt" and not path_value:
        import string

        drives = []
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if drive.exists():
                drives.append({"name": f"{letter}:\\", "path": str(drive)})
        return {"mode": "root", "current": "", "parent": None, "entries": drives}

    current = closest_existing_dir(Path(path_value or default_destination()))
    parent = str(current.parent) if current != current.parent else None
    return {"mode": "root", "current": str(current), "parent": parent, "entries": directory_entries(current)}


def browse_subfolder_payload(root_value: str, relative_value: str = "") -> Dict[str, Any]:
    root = closest_existing_dir(Path(root_value or default_destination())).resolve()
    if relative_value.strip():
        relative = validate_emudeck_subfolder(relative_value)
        current = (root / Path(*relative.split("/"))).resolve()
    else:
        relative = ""
        current = root

    if root != current and root not in current.parents:
        raise RuntimeError("Subfolder browser cannot leave the ROMs root")
    current = closest_existing_dir(current).resolve()
    if root != current and root not in current.parents:
        current = root

    rel_current = "" if current == root else current.relative_to(root).as_posix()
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
        "current": rel_current,
        "parent": parent,
        "entries": entries,
    }


def normalized_match_text(value: str) -> str:
    text = unquote(value or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_minerva_path(value: str) -> str:
    decoded = unquote(value or "").replace("\\", "/").strip()
    while decoded.startswith("./"):
        decoded = decoded[2:]
    decoded = decoded.lstrip("/")
    parts = [part for part in decoded.split("/") if part and part != "."]
    return "/".join(parts)


def emudeck_route_for_path(full_path: str) -> Optional[Dict[str, str]]:
    normalized = normalize_minerva_path(full_path)
    parts = normalized.split("/")
    searchable = normalized_match_text(" ".join(parts[:-1] if len(parts) > 1 else parts))
    for label, tokens, folder in EMUDECK_ROUTE_RULES:
        if all(normalized_match_text(token) in searchable for token in tokens):
            return {"system": label, "folder": folder, "path": normalized}
    return None


def validate_emudeck_subfolder(value: str) -> str:
    raw = (value or "").strip().replace("\\", "/")
    if re.match(r"^[A-Za-z]:", raw) or raw.startswith("/"):
        raise RuntimeError("EmuDeck system folder must be relative to the ROMs root")
    cleaned = raw.strip("/")
    if not cleaned:
        raise RuntimeError("No EmuDeck system folder was detected")
    parts = [part for part in cleaned.split("/") if part]
    if any(part in (".", "..") for part in parts):
        raise RuntimeError("EmuDeck system folder cannot contain '.' or '..'")
    if any(re.search(r'[<>:"|?*\x00-\x1f]', part) for part in parts):
        raise RuntimeError("EmuDeck system folder contains invalid path characters")
    return "/".join(parts)


def emudeck_destination(
    roms_root: Path,
    full_path: str,
    override: str = "",
    allow_root_fallback: bool = False,
) -> Tuple[Path, str, str]:
    if override.strip():
        folder = validate_emudeck_subfolder(override)
        system = "Manual override"
    else:
        route = emudeck_route_for_path(full_path)
        if not route:
            if allow_root_fallback:
                return roms_root.expanduser(), ".", "ROMs root fallback"
            raise RuntimeError("Could not map this MiNERVA system to an EmuDeck ROM folder")
        folder = validate_emudeck_subfolder(route["folder"])
        system = route["system"]
    target = roms_root.expanduser()
    for part in folder.split("/"):
        target = target / part
    return target, folder, system


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" .")
    return cleaned or "download"


def format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024


def path_stem_for_archive(path: Path) -> str:
    name = path.name
    lowered = name.lower()
    for suffix in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz"):
        if lowered.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def url_head_ok(url: str, timeout: int = 12) -> bool:
    req = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def fetch_bytes(url: str, timeout: int = 60) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def quote_path_for_url(path: str) -> str:
    return "/".join(quote(part) for part in path.split("/"))


class TorrentListParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        if href and href.endswith(".torrent"):
            self.hrefs.append(unquote(href))


class SearchIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._loading = False
        self._paths: List[str] = []
        self._lower_paths: List[str] = []
        self._index_file = CACHE_DIR / "index.txt.gz"
        self._loaded_at: Optional[int] = None

    def status(self) -> Dict[str, Any]:
        return {
            "loaded": self._loaded,
            "loading": self._loading,
            "count": len(self._paths),
            "loadedAt": self._loaded_at,
            "cacheFile": str(self._index_file),
        }

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._loading = True
            try:
                if not self._index_file.exists() or self._index_file.stat().st_size < 1024:
                    self._download_index()
                with gzip.open(self._index_file, "rt", encoding="utf-8", errors="replace") as handle:
                    paths = [line.strip() for line in handle if line.strip()]
                self._paths = paths
                self._lower_paths = [path.lower() for path in paths]
                self._loaded = True
                self._loaded_at = now_ms()
            finally:
                self._loading = False

    def _download_index(self) -> None:
        tmp = self._index_file.with_suffix(".tmp")
        req = Request(SEARCH_INDEX_URL, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=120) as resp, tmp.open("wb") as out:
            shutil.copyfileobj(resp, out)
        tmp.replace(self._index_file)

    def search(self, query: str, limit: int = MAX_SEARCH_RESULTS) -> Dict[str, Any]:
        self.ensure_loaded()
        query = (query or "").strip().lower()
        tokens = re.sub(r"[^a-z0-9\s]+", " ", query).split()
        if len(query) < 3 or not tokens:
            return {"results": [], "total": 0, "loaded": self.status()}

        token_patterns = [re.compile("".join(re.escape(ch) + r"[^a-z0-9]*" for ch in token)) for token in tokens]
        results: List[Dict[str, str]] = []
        total = 0
        for original, lowered in zip(self._paths, self._lower_paths):
            if all(pattern.search(lowered) for pattern in token_patterns):
                total += 1
                if len(results) < limit:
                    normalized = normalize_minerva_path(original)
                    parts = normalized.split("/")
                    results.append(
                        {
                            "path": original,
                            "normalizedPath": normalized,
                            "fileName": parts[-1] if parts else original,
                            "collection": parts[0] if len(parts) > 0 else "",
                            "system": parts[1] if len(parts) > 1 else "",
                        }
                    )
        return {"results": results, "total": total, "loaded": self.status()}


SEARCH_INDEX = SearchIndex()


class BencodeError(ValueError):
    pass


def bdecode(data: bytes, index: int = 0) -> Tuple[Any, int]:
    if index >= len(data):
        raise BencodeError("Unexpected end of torrent data")
    token = data[index : index + 1]
    if token == b"i":
        end = data.index(b"e", index)
        return int(data[index + 1 : end]), end + 1
    if token == b"l":
        result = []
        index += 1
        while data[index : index + 1] != b"e":
            item, index = bdecode(data, index)
            result.append(item)
        return result, index + 1
    if token == b"d":
        result = {}
        index += 1
        while data[index : index + 1] != b"e":
            key, index = bdecode(data, index)
            value, index = bdecode(data, index)
            result[key] = value
        return result, index + 1
    if token.isdigit():
        colon = data.index(b":", index)
        length = int(data[index:colon])
        start = colon + 1
        return data[start : start + length], start + length
    raise BencodeError(f"Invalid bencode token at {index}")


def btext(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


@dataclass
class TorrentFile:
    index: int
    path: str
    length: int


@dataclass
class TorrentSelection:
    root_name: str
    file: TorrentFile
    torrent_url: str
    torrent_path: Path


def parse_torrent(torrent_path: Path) -> Tuple[str, List[TorrentFile]]:
    decoded, _ = bdecode(torrent_path.read_bytes())
    info = decoded.get(b"info")
    if not isinstance(info, dict):
        raise BencodeError("Torrent info dictionary is missing")
    root = btext(info.get(b"name", b""))
    files = info.get(b"files")
    if isinstance(files, list):
        result = []
        for index, file_info in enumerate(files, start=1):
            raw_parts = file_info.get(b"path", [])
            parts = [btext(part) for part in raw_parts]
            result.append(TorrentFile(index=index, path="/".join(parts), length=int(file_info.get(b"length", 0))))
        return root, result
    name = btext(info.get(b"name", b"download"))
    length = int(info.get(b"length", 0))
    return root, [TorrentFile(index=1, path=name, length=length)]


def candidate_torrent_urls(torrent_hint: str, rom_path: str) -> List[str]:
    urls: List[str] = []
    hint = (torrent_hint or "").strip()
    if hint:
        if hint.startswith("http://") or hint.startswith("https://"):
            urls.append(hint)
        else:
            cleaned = unquote(hint).lstrip("/")
            cleaned = cleaned[7:] if cleaned.startswith("assets/") else cleaned
            basename = posixpath.basename(cleaned)
            if basename.endswith(".torrent"):
                urls.append(f"{MINERVA_CDN}/torrents/{quote(basename)}")
                if cleaned.startswith("torrents/"):
                    urls.append(f"{MINERVA_CDN}/{quote_path_for_url(cleaned)}")
                urls.append(f"{MINERVA_BASE}/assets/{quote_path_for_url(cleaned)}")

    normalized = normalize_minerva_path(rom_path)
    parts = normalized.split("/")
    if len(parts) > 1:
        max_depth = min(len(parts) - 1, 8)
        for depth in range(max_depth, 0, -1):
            label = " - ".join(parts[:depth])
            filename = f"Minerva_Myrient - {label}.torrent"
            urls.append(f"{MINERVA_CDN}/torrents/{quote(filename)}")

    deduped: List[str] = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


_torrent_list_cache: Optional[List[str]] = None
_torrent_list_lock = threading.Lock()


def torrent_list() -> List[str]:
    global _torrent_list_cache
    with _torrent_list_lock:
        if _torrent_list_cache is not None:
            return _torrent_list_cache
        parser = TorrentListParser()
        parser.feed(fetch_bytes(TORRENT_LIST_URL, timeout=60).decode("utf-8", errors="replace"))
        _torrent_list_cache = parser.hrefs
        return _torrent_list_cache


def fallback_torrent_urls(rom_path: str) -> List[str]:
    normalized = normalize_minerva_path(rom_path).lower()
    parts = [part.lower() for part in normalize_minerva_path(rom_path).split("/")[:-1]]
    if not parts:
        return []
    urls: List[str] = []
    try:
        for filename in torrent_list():
            lowered = filename.lower()
            if not lowered.endswith(".torrent"):
                continue
            if all(part in lowered for part in parts[:2]) or (parts[0] in lowered and normalized.split("/")[0] in lowered):
                urls.append(f"{MINERVA_CDN}/torrents/{quote(filename)}")
    except Exception:
        return []
    return urls


def all_torrent_url_candidates(torrent_hint: str, rom_path: str) -> List[str]:
    urls = candidate_torrent_urls(torrent_hint, rom_path) + fallback_torrent_urls(rom_path)
    deduped: List[str] = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def resolve_torrent_url(torrent_hint: str, rom_path: str) -> str:
    for url in all_torrent_url_candidates(torrent_hint, rom_path):
        if url_head_ok(url):
            return url
    raise RuntimeError("Could not resolve the grouped torrent for this ROM")


def resolve_torrent_selection(
    torrent_hint: str,
    rom_path: str,
    work_dir: Path,
    logger: Optional[Any] = None,
) -> TorrentSelection:
    errors: List[str] = []
    for url in all_torrent_url_candidates(torrent_hint, rom_path):
        if not url_head_ok(url):
            continue
        try:
            if logger:
                logger(f"Trying torrent: {url}")
            torrent_path = download_torrent_file(url, work_dir)
            root_name, files = parse_torrent(torrent_path)
            selected = find_torrent_file(files, rom_path)
            return TorrentSelection(root_name=root_name, file=selected, torrent_url=url, torrent_path=torrent_path)
        except Exception as exc:
            errors.append(f"{posixpath.basename(urlparse(url).path)}: {exc}")
    if errors:
        raise RuntimeError("No candidate torrent contained the selected ROM. " + " | ".join(errors[-4:]))
    raise RuntimeError("Could not resolve the grouped torrent for this ROM")


def download_torrent_file(url: str, work_dir: Path) -> Path:
    filename = safe_filename(unquote(posixpath.basename(urlparse(url).path)) or "rom.torrent")
    torrent_path = work_dir / filename
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=120) as resp, torrent_path.open("wb") as out:
        shutil.copyfileobj(resp, out)
    return torrent_path


def find_torrent_file(files: List[TorrentFile], rom_path: str) -> TorrentFile:
    target = normalize_minerva_path(rom_path)
    target_lower = target.lower()
    target_name = posixpath.basename(target_lower)

    exact: List[TorrentFile] = []
    basename_matches: List[TorrentFile] = []
    suffix_matches: List[TorrentFile] = []
    for file in files:
        file_path = normalize_minerva_path(file.path)
        lowered = file_path.lower()
        if lowered == target_lower:
            exact.append(file)
        elif lowered.endswith("/" + target_lower) or target_lower.endswith("/" + lowered):
            suffix_matches.append(file)
        elif posixpath.basename(lowered) == target_name:
            basename_matches.append(file)

    for matches in (exact, suffix_matches, basename_matches):
        if len(matches) == 1:
            return matches[0]
    if len(basename_matches) > 1:
        raise RuntimeError("Multiple torrent entries matched the same ROM filename")
    raise RuntimeError("The selected ROM was not found inside the resolved torrent")


def expected_download_paths(download_dir: Path, root_name: str, rel_path: str) -> List[Path]:
    normalized = normalize_minerva_path(rel_path)
    return [
        download_dir / root_name / Path(*normalized.split("/")),
        download_dir / Path(*normalized.split("/")),
    ]


def locate_downloaded_file(download_dir: Path, root_name: str, rel_path: str) -> Path:
    for candidate in expected_download_paths(download_dir, root_name, rel_path):
        if candidate.exists() and candidate.is_file():
            return candidate
    basename = posixpath.basename(rel_path).lower()
    matches = [path for path in download_dir.rglob("*") if path.is_file() and path.name.lower() == basename]
    if len(matches) == 1:
        return matches[0]
    if matches:
        return max(matches, key=lambda path: path.stat().st_size)
    raise RuntimeError("Download finished, but the selected file could not be located")


def metadata_for_path(full_path: str, torrent_hint: str = "") -> Dict[str, Any]:
    if not full_path:
        raise RuntimeError("No ROM path was provided")
    work_dir = CACHE_DIR / "metadata" / uuid.uuid4().hex[:10]
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        selection = resolve_torrent_selection(torrent_hint, full_path, work_dir)
        return {
            "fullPath": normalize_minerva_path(full_path),
            "torrentUrl": selection.torrent_url,
            "torrentRoot": selection.root_name,
            "fileIndex": selection.file.index,
            "torrentPath": selection.file.path,
            "sizeBytes": selection.file.length,
            "size": format_bytes(selection.file.length),
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def is_archive(path: Path) -> bool:
    lowered = path.name.lower()
    return any(lowered.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def safe_extract_zip(archive: Path, target: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            destination = safe_extract_path(target, info.filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, destination.open("wb") as out:
                shutil.copyfileobj(src, out)


def safe_extract_tar(archive: Path, target: Path) -> None:
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            destination = safe_extract_path(target, member.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            with src, destination.open("wb") as out:
                shutil.copyfileobj(src, out)


def safe_extract_path(base: Path, member_name: str) -> Path:
    destination = (base / member_name).resolve()
    base_resolved = base.resolve()
    if base_resolved != destination and base_resolved not in destination.parents:
        raise RuntimeError(f"Archive member escapes extraction directory: {member_name}")
    return destination


def run_7z_extract(seven_zip: str, archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    command = [seven_zip, "x", "-y", f"-o{target}", str(archive)]
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout.strip() or "7z extraction failed")


def move_tree_contents(source: Path, destination: Path, base_name: str) -> List[str]:
    destination.mkdir(parents=True, exist_ok=True)
    files = [path for path in source.rglob("*") if path.is_file()]
    if not files:
        raise RuntimeError("Archive extraction produced no files")

    if len(files) == 1:
        return [move_unique(files[0], destination / files[0].name)]

    game_dir = unique_path(destination / safe_filename(base_name))
    game_dir.mkdir(parents=True, exist_ok=False)
    moved = []
    for path in files:
        rel = path.relative_to(source)
        target = game_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        moved.append(move_unique(path, target))
    return moved


def move_unique(source: Path, target: Path) -> str:
    target = unique_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    return str(target)


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(1, 10000):
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find an available filename for {path.name}")


def place_downloaded_file(downloaded: Path, destination: Path, extract: bool, seven_zip: Optional[str]) -> List[str]:
    destination = destination.expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    if extract and is_archive(downloaded):
        extract_dir = downloaded.parent / "_extracted"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        lowered = downloaded.name.lower()
        if lowered.endswith(".zip"):
            safe_extract_zip(downloaded, extract_dir)
        elif lowered.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
            safe_extract_tar(downloaded, extract_dir)
        elif seven_zip:
            run_7z_extract(seven_zip, downloaded, extract_dir)
        else:
            raise RuntimeError("This archive needs 7z/7zz/7za for extraction")
        return move_tree_contents(extract_dir, destination, path_stem_for_archive(downloaded))
    return [move_unique(downloaded, destination / downloaded.name)]


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []
        self._worker: Optional[threading.Thread] = None

    def create(self, payload: Dict[str, Any]) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "status": "queued",
                "stage": "Queued",
                "progress": None,
                "createdAt": now_ms(),
                "updatedAt": now_ms(),
                "startedAt": None,
                "finishedAt": None,
                "payload": payload,
                "log": [],
                "outputs": [],
                "error": None,
            }
            self._order.append(job_id)
        return job_id

    def update(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(updates)
            job["updatedAt"] = now_ms()

    def log(self, job_id: str, message: str) -> None:
        clean = message.strip()
        if not clean:
            return
        with self._lock:
            job = self._jobs[job_id]
            job["log"].append(clean)
            job["log"] = job["log"][-200:]
            job["updatedAt"] = now_ms()

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return json.loads(json.dumps(job)) if job else None

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = [self._jobs[job_id] for job_id in self._order if job_id in self._jobs]
            return json.loads(json.dumps(jobs))

    def next_queued(self) -> Optional[str]:
        with self._lock:
            for job_id in self._order:
                if self._jobs[job_id]["status"] == "queued":
                    return job_id
        return None

    def ensure_worker(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=download_worker_loop, daemon=True)
            self._worker.start()


JOBS = JobStore()


def download_worker_loop() -> None:
    while True:
        job_id = JOBS.next_queued()
        if not job_id:
            return
        run_download_job(job_id)


def run_download_job(job_id: str) -> None:
    job = JOBS.get(job_id)
    if not job:
        return
    payload = job["payload"]
    work_dir = JOB_DIR / job_id
    download_dir = work_dir / "download"
    aria2c = command_path("aria2c")
    seven_zip = find_7z()

    try:
        if not aria2c:
            raise RuntimeError("aria2c is required for selective torrent downloads")

        full_path = payload.get("fullPath") or ""
        torrent_hint = payload.get("torrent") or ""
        roms_root = Path(payload.get("romsRoot") or payload.get("destination") or default_destination()).expanduser()
        system_folder_override = payload.get("systemFolderOverride") or ""
        allow_root_fallback = bool(payload.get("allowRomsRootFallback", False))
        extract = bool(payload.get("extract", True))
        if not full_path:
            raise RuntimeError("No ROM path was provided")
        if not payload.get("legalConfirm"):
            raise RuntimeError("Confirm that you have the right to download this file before starting")
        destination, emudeck_folder, emudeck_system = emudeck_destination(
            roms_root,
            full_path,
            system_folder_override,
            allow_root_fallback,
        )
        JOBS.log(job_id, f"EmuDeck route: {emudeck_system} -> {emudeck_folder}")

        if work_dir.exists():
            shutil.rmtree(work_dir)
        download_dir.mkdir(parents=True, exist_ok=True)

        JOBS.update(job_id, status="running", stage="Resolving torrent", progress=None, startedAt=now_ms())
        JOBS.update(job_id, stage="Downloading torrent metadata")
        selection = resolve_torrent_selection(torrent_hint, full_path, work_dir, lambda message: JOBS.log(job_id, message))
        torrent_path = selection.torrent_path
        root_name = selection.root_name
        selected = selection.file
        JOBS.log(job_id, f"Torrent: {selection.torrent_url}")
        JOBS.log(job_id, f"Selected file #{selected.index}: {selected.path}")

        JOBS.update(job_id, stage="Downloading selected file", progress=0)
        command = [
            aria2c,
            "--continue=true",
            "--seed-time=0",
            "--file-allocation=none",
            "--auto-file-renaming=false",
            "--allow-overwrite=false",
            "--summary-interval=1",
            "--console-log-level=notice",
            "--dir",
            str(download_dir),
            "--select-file",
            str(selected.index),
            str(torrent_path),
        ]
        run_aria2(job_id, command)

        downloaded = locate_downloaded_file(download_dir, root_name, selected.path)
        JOBS.update(job_id, stage="Placing files", progress=None)
        outputs = place_downloaded_file(downloaded, destination, extract, seven_zip)
        JOBS.update(job_id, status="done", stage="Done", progress=100, outputs=outputs, emudeckFolder=emudeck_folder, finishedAt=now_ms())
        JOBS.log(job_id, f"Output: {destination}")
    except Exception as exc:
        JOBS.update(job_id, status="error", stage="Error", error=str(exc), progress=None, finishedAt=now_ms())
        JOBS.log(job_id, str(exc))


def run_aria2(job_id: str, command: List[str]) -> None:
    percent_pattern = re.compile(r"\((\d{1,3})%\)")
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=process_env(),
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    assert proc.stdout is not None
    output_queue: "queue.Queue[str]" = queue.Queue()

    def reader() -> None:
        for raw in proc.stdout:
            output_queue.put(raw)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    last_progress_update = 0
    while proc.poll() is None:
        drain_aria2_output(job_id, output_queue, percent_pattern)
        if time.time() - last_progress_update > 2:
            last_progress_update = time.time()
        time.sleep(0.2)

    drain_aria2_output(job_id, output_queue, percent_pattern)
    if proc.returncode != 0:
        raise RuntimeError(f"aria2c exited with code {proc.returncode}")


def drain_aria2_output(job_id: str, output_queue: "queue.Queue[str]", percent_pattern: re.Pattern[str]) -> None:
    while True:
        try:
            raw = output_queue.get_nowait()
        except queue.Empty:
            return
        line = raw.replace("\r", "\n")
        for part in line.splitlines():
            part = part.strip()
            if not part:
                continue
            match = percent_pattern.search(part)
            if match:
                progress = max(0, min(100, int(match.group(1))))
                JOBS.update(job_id, progress=progress)
            if len(part) < 240:
                JOBS.log(job_id, part)


class AppHandler(BaseHTTPRequestHandler):
    server_version = "MinervaDeck/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            return self.serve_file(PUBLIC_ROOT / "index.html")
        if path.startswith("/static/"):
            return self.serve_file(PUBLIC_ROOT / path.lstrip("/"))
        if path == "/api/status":
            return self.send_json(status_payload())
        if path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            try:
                return self.send_json(SEARCH_INDEX.search(query))
            except Exception as exc:
                return self.send_json({"error": str(exc)}, status=500)
        if path == "/api/route":
            full_path = parse_qs(parsed.query).get("path", [""])[0]
            route = emudeck_route_for_path(full_path)
            if route:
                return self.send_json({"route": route})
            return self.send_json({"route": None, "error": "No EmuDeck folder mapping found"}, status=404)
        if path == "/api/browse":
            query = parse_qs(parsed.query)
            mode = query.get("mode", ["root"])[0]
            try:
                if mode == "subfolder":
                    return self.send_json(
                        browse_subfolder_payload(
                            query.get("root", [""])[0],
                            query.get("path", [""])[0],
                        )
                    )
                return self.send_json(browse_root_payload(query.get("path", [""])[0]))
            except Exception as exc:
                return self.send_json({"error": str(exc)}, status=400)
        if path == "/api/metadata":
            query = parse_qs(parsed.query)
            try:
                return self.send_json(
                    metadata_for_path(
                        query.get("path", [""])[0],
                        query.get("torrent", [""])[0],
                    )
                )
            except Exception as exc:
                return self.send_json({"error": str(exc)}, status=400)
        if path == "/api/jobs":
            return self.send_json({"jobs": JOBS.list()})
        if path.startswith("/api/jobs/"):
            job_id = path.rsplit("/", 1)[-1]
            job = JOBS.get(job_id)
            if not job:
                return self.send_json({"error": "Job not found"}, status=404)
            return self.send_json(job)
        if path.startswith("/proxy/"):
            return self.proxy_minerva(path[len("/proxy/") :])
        return self.send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/download":
            return self.send_json({"error": "Not found"}, status=404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            job_id = JOBS.create(payload)
            JOBS.ensure_worker()
            return self.send_json({"id": job_id, "status": "queued"}, status=201)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, status=500)

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/proxy/"):
            return self.proxy_minerva(parsed.path[len("/proxy/") :], head_only=True)
        if parsed.path == "/" or parsed.path.startswith("/static/"):
            file_path = PUBLIC_ROOT / ("index.html" if parsed.path == "/" else parsed.path.lstrip("/"))
            if not file_path.exists():
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def serve_file(self, file_path: Path) -> None:
        resolved = file_path.resolve()
        if PUBLIC_ROOT.resolve() not in resolved.parents and resolved != PUBLIC_ROOT.resolve():
            return self.send_json({"error": "Forbidden"}, status=403)
        if not resolved.exists() or not resolved.is_file():
            return self.send_json({"error": "Not found"}, status=404)
        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(resolved.stat().st_size))
        self.end_headers()
        with resolved.open("rb") as handle:
            shutil.copyfileobj(handle, self.wfile)

    def proxy_minerva(self, resource: str, head_only: bool = False) -> None:
        resource = unquote(resource).lstrip("/")
        allowed_exact = {
            "assets/hashes.db",
            "assets/index.txt.gz",
            "js/sqlite.worker.js",
            "js/sql-wasm.wasm",
        }
        if resource not in allowed_exact:
            return self.send_json({"error": "Proxy resource not allowed"}, status=403)

        remote_url = f"{MINERVA_BASE}/{quote_path_for_url(resource)}"
        headers = {"User-Agent": USER_AGENT}
        range_header = self.headers.get("Range")
        if range_header:
            headers["Range"] = range_header
        req = Request(remote_url, method="HEAD" if head_only else "GET", headers=headers)
        try:
            with urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                for header in ("Content-Type", "Content-Length", "Accept-Ranges", "Content-Range", "Last-Modified"):
                    value = resp.headers.get(header)
                    if value:
                        self.send_header(header, value)
                self.end_headers()
                if not head_only:
                    shutil.copyfileobj(resp, self.wfile)
        except HTTPError as exc:
            self.send_response(exc.code)
            self.end_headers()
        except URLError as exc:
            self.send_json({"error": str(exc)}, status=502)

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), format % args))


def status_payload() -> Dict[str, Any]:
    aria2c = command_path("aria2c")
    seven_zip = find_7z()
    return {
        "app": APP_NAME,
        "dataDir": str(DATA_DIR),
        "defaultDestination": default_destination(),
        "dependencies": {
            "aria2c": {"found": bool(aria2c), "path": aria2c},
            "sevenZip": {"found": bool(seven_zip), "path": seven_zip},
        },
        "searchIndex": SEARCH_INDEX.status(),
        "emudeckRoutes": len(EMUDECK_ROUTE_RULES),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the MiNERVA Deck local app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", DEFAULT_PORT)))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"{APP_NAME} running at {url}")
    print(f"Data directory: {DATA_DIR}")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
