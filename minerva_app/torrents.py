"""Resolve grouped torrents and identify one selected archive entry."""

from __future__ import annotations

import html.parser
import posixpath
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen

from .config import CACHE_DIR, MINERVA_BASE, MINERVA_CDN, TORRENT_LIST_URL, USER_AGENT
from .utils import (
    fetch_bytes,
    format_bytes,
    normalize_minerva_path,
    quote_path_for_url,
    safe_filename,
    url_head_ok,
)


class TorrentListParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href and href.endswith(".torrent"):
            self.hrefs.append(unquote(href))


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
        for index, file_info in enumerate(files):
            parts = [btext(part) for part in file_info.get(b"path", [])]
            result.append(
                TorrentFile(
                    index=index,
                    path="/".join(parts),
                    length=int(file_info.get(b"length", 0)),
                )
            )
        return root, result
    name = btext(info.get(b"name", b"download"))
    length = int(info.get(b"length", 0))
    return root, [TorrentFile(index=0, path=name, length=length)]


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
        for depth in range(min(len(parts) - 1, 8), 0, -1):
            label = " - ".join(parts[:depth])
            filename = f"Minerva_Myrient - {label}.torrent"
            urls.append(f"{MINERVA_CDN}/torrents/{quote(filename)}")
    return list(dict.fromkeys(urls))


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
            if all(part in lowered for part in parts[:2]) or (
                parts[0] in lowered and normalized.split("/")[0] in lowered
            ):
                urls.append(f"{MINERVA_CDN}/torrents/{quote(filename)}")
    except Exception:
        return []
    return urls


def all_torrent_url_candidates(torrent_hint: str, rom_path: str) -> List[str]:
    return list(
        dict.fromkeys(
            candidate_torrent_urls(torrent_hint, rom_path)
            + fallback_torrent_urls(rom_path)
        )
    )


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
            return TorrentSelection(root_name, selected, url, torrent_path)
        except Exception as exc:
            errors.append(f"{posixpath.basename(urlparse(url).path)}: {exc}")
    if errors:
        raise RuntimeError(
            "No candidate torrent contained the selected ROM. "
            + " | ".join(errors[-4:])
        )
    raise RuntimeError("Could not resolve the grouped torrent for this ROM")


def download_torrent_file(url: str, work_dir: Path) -> Path:
    filename = safe_filename(unquote(posixpath.basename(urlparse(url).path)) or "rom.torrent")
    torrent_path = work_dir / filename
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response, torrent_path.open("wb") as output:
        shutil.copyfileobj(response, output)
    return torrent_path


def find_torrent_file(files: List[TorrentFile], rom_path: str) -> TorrentFile:
    target = normalize_minerva_path(rom_path)
    target_lower = target.lower()
    target_name = posixpath.basename(target_lower)
    exact: List[TorrentFile] = []
    basename_matches: List[TorrentFile] = []
    suffix_matches: List[TorrentFile] = []
    for file in files:
        lowered = normalize_minerva_path(file.path).lower()
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


def expected_download_paths(download_dir: Path, root_name: str, relative_path: str) -> List[Path]:
    normalized = normalize_minerva_path(relative_path)
    return [
        download_dir / root_name / Path(*normalized.split("/")),
        download_dir / Path(*normalized.split("/")),
    ]


def locate_downloaded_file(download_dir: Path, root_name: str, relative_path: str) -> Path:
    for candidate in expected_download_paths(download_dir, root_name, relative_path):
        if candidate.exists() and candidate.is_file():
            return candidate
    basename = posixpath.basename(relative_path).lower()
    matches = [
        path
        for path in download_dir.rglob("*")
        if path.is_file() and path.name.lower() == basename
    ]
    if len(matches) == 1:
        return matches[0]
    if matches:
        return max(matches, key=lambda path: path.stat().st_size)
    raise RuntimeError("Download finished, but the selected file could not be located")


def metadata_for_path(full_path: str, torrent_hint: str = "") -> dict:
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
            "fileIndex": selection.file.index + 1,
            "torrentPath": selection.file.path,
            "sizeBytes": selection.file.length,
            "size": format_bytes(selection.file.length),
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
