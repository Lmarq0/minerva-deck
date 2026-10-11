"""Offline game catalog built from the file lists of MiNERVA's torrents."""

from __future__ import annotations

import hashlib
import json
import lzma
import re
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote
from urllib.request import Request, urlopen

from .config import (
    CACHE_DIR,
    CATALOG_MANIFEST_URL,
    CATALOG_RELEASE_URL,
    CATALOG_SCHEMA_VERSION,
    MAX_SEARCH_RESULTS,
    TORRENT_LIST_URL,
    USER_AGENT,
)
from .routes import emudeck_route_for_path
from .utils import (
    fetch_bytes,
    format_bytes,
    normalize_minerva_path,
    normalized_match_text,
    now_ms,
)


ARCHIVE_FORMATS = {"zip", "7z", "rar", "tar", "gz", "bz2", "xz", "tgz", "tbz2", "txz"}
DISC_FORMATS = {"chd", "iso", "cue", "gdi", "cso", "rvz", "wbfs", "cdi", "mdf", "nrg"}
PACKAGE_FORMATS = {"pkg", "nsp", "xci", "wua", "cia", "wad", "vpk", "rap"}
ROM_FORMATS = {
    "32x", "3ds", "a26", "a52", "a78", "bin", "fds", "gb", "gba", "gbc", "gen",
    "gg", "lnx", "md", "nds", "nes", "n64", "ngc", "pce", "sfc", "smc", "sms",
    "smd", "vec", "ws", "wsc", "z64",
}
FORMAT_GROUP_CODES = {"": 0, "archive": 1, "disc": 2, "rom": 3, "package": 4}
FORMAT_GROUP_NAMES = {value: key for key, value in FORMAT_GROUP_CODES.items()}
AUXILIARY_EXTENSIONS = {
    "bmp", "cab", "cfg", "dll", "doc", "docx", "gif", "htm", "html", "ini",
    "jpg", "jpeg", "json", "md", "nfo", "pdf", "png", "svg", "txt", "xml",
}
AUXILIARY_PATH_MARKERS = (
    "/!extras/", "/extras/", "/support files/", "/artwork/", "/covers/",
    "/covers_", "/manuals/", "/manual/", "/snap/", "/snap_", "/snaps/",
    "/screenshots/", "/previews/", "/titles/", "/titles_", "/icons/",
    "/all_non-zipped_content/", "/themes/", "/soundtrack/", "/boxart/", "/box art/",
    "/audio cd/", "/audio cd -", "/nintendo - nintendo music (",
    "/spc music/", "/vgm music/", "/nsf music/", "/sid music/", "/psf music/",
    "/tosec-pix/", "/game guides/",
)


def catalog_extension(filename: str) -> str:
    lowered = filename.lower()
    for compound in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if lowered.endswith(compound):
            return compound[1:]
    return lowered.rsplit(".", 1)[-1] if "." in lowered else ""


def catalog_format_group(extension: str) -> str:
    simple = extension.rsplit(".", 1)[-1]
    if extension in ARCHIVE_FORMATS or simple in ARCHIVE_FORMATS:
        return "archive"
    if extension in DISC_FORMATS or simple in DISC_FORMATS:
        return "disc"
    if extension in PACKAGE_FORMATS or simple in PACKAGE_FORMATS:
        return "package"
    if extension in ROM_FORMATS or simple in ROM_FORMATS:
        return "rom"
    return ""


def catalog_kind(path: str, extension: str) -> str:
    lowered = "/" + normalize_minerva_path(path).lower().strip("/") + "/"
    simple = extension.rsplit(".", 1)[-1]
    if simple in AUXILIARY_EXTENSIONS or any(marker in lowered for marker in AUXILIARY_PATH_MARKERS):
        return "auxiliary"
    return "game"


def catalog_title_search_text(title: str) -> str:
    camel_title = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", title)
    camel_title = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", camel_title)
    return normalized_match_text(camel_title)


def catalog_parent_search_text(path: str) -> str:
    normalized = normalize_minerva_path(path)
    return normalized_match_text(" ".join(normalized.split("/")[:-1]))


def region_for_title(title: str) -> str:
    lowered = normalized_match_text(title)
    regions = (
        ("USA", (" usa ", " united states ", " north america ")),
        ("Europe", (" europe ", " eur ", " pal ")),
        ("Japan", (" japan ", " jpn ", " jap ")),
        ("World", (" world ",)),
        ("Brazil", (" brazil ", " bra ")),
        ("Korea", (" korea ", " kor ")),
        ("Australia", (" australia ", " aus ")),
    )
    padded = f" {lowered} "
    for label, markers in regions:
        if any(marker in padded for marker in markers):
            return label
    return ""


def useful_catalog_section(value: str) -> bool:
    normalized = normalized_match_text(value)
    if not normalized:
        return False
    return not (
        normalized.startswith("archiver ")
        or normalized.startswith("team")
        or normalized.startswith("user ")
        or normalized.startswith("storage manager")
        or normalized.startswith("item manager")
        or normalized.startswith("mirror ")
        or normalized in {"extras", "support files", "miscellaneous", "roms", "files"}
    )


CATALOG_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000
CATALOG_RETRY_SECONDS = 30
CATALOG_SCHEMA = """
CREATE TABLE torrents (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE directories (id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE);
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    torrent_id INTEGER NOT NULL,
    file_index INTEGER NOT NULL,
    directory_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    extension TEXT NOT NULL,
    size INTEGER NOT NULL,
    kind INTEGER NOT NULL,
    format_group INTEGER NOT NULL
);
CREATE TABLE catalog_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE VIRTUAL TABLE files_fts USING fts5(
    title_terms,
    path_terms,
    content='',
    detail=none,
    tokenize='unicode61 remove_diacritics 2'
);
"""


def build_catalog(
    output: Path,
    torrents: Iterable[Tuple[str, Sequence[Tuple[int, str, int]]]],
) -> Dict[str, int]:
    """Write a searchable catalog from (torrent name, [(index, path, size)]) pairs."""
    if output.exists():
        output.unlink()
    connection = sqlite3.connect(output)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.executescript(CATALOG_SCHEMA)
        directories: Dict[str, int] = {}
        file_batch: List[Tuple[Any, ...]] = []
        search_batch: List[Tuple[int, str, str]] = []
        entries = 0
        torrent_count = 0

        def flush() -> None:
            connection.executemany(
                "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", file_batch
            )
            connection.executemany(
                "INSERT INTO files_fts(rowid, title_terms, path_terms) VALUES (?, ?, ?)",
                search_batch,
            )
            file_batch.clear()
            search_batch.clear()

        for torrent_name, files in torrents:
            torrent_count += 1
            connection.execute(
                "INSERT INTO torrents(id, name) VALUES (?, ?)", (torrent_count, torrent_name)
            )
            for index, raw_path, size in files:
                path = normalize_minerva_path(raw_path)
                parts = path.split("/")
                title = parts[-1]
                # BitTorrent v2 padding files are not real archive entries.
                if not title or ".pad" in parts[:-1]:
                    continue
                directory = "/".join(parts[:-1])
                directory_id = directories.get(directory)
                if directory_id is None:
                    directory_id = directories[directory] = len(directories) + 1
                    connection.execute(
                        "INSERT INTO directories(id, path) VALUES (?, ?)",
                        (directory_id, directory),
                    )
                extension = catalog_extension(title)
                entries += 1
                file_batch.append(
                    (
                        entries,
                        torrent_count,
                        index,
                        directory_id,
                        title,
                        extension,
                        size,
                        1 if catalog_kind(path, extension) == "game" else 0,
                        FORMAT_GROUP_CODES[catalog_format_group(extension)],
                    )
                )
                search_batch.append(
                    (entries, catalog_title_search_text(title), catalog_parent_search_text(path))
                )
                if len(file_batch) >= 20000:
                    flush()
        flush()
        built_at = now_ms()
        connection.executemany(
            "INSERT INTO catalog_meta(key, value) VALUES (?, ?)",
            (
                ("schema_version", str(CATALOG_SCHEMA_VERSION)),
                ("entry_count", str(entries)),
                ("torrent_count", str(torrent_count)),
                ("built_at", str(built_at)),
            ),
        )
        connection.execute("INSERT INTO files_fts(files_fts) VALUES ('optimize')")
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()
    return {"entries": entries, "torrents": torrent_count, "builtAt": built_at}


def read_catalog_meta(database: Path) -> Optional[Dict[str, int]]:
    """Return catalog metadata, or None if the file is not a usable catalog."""
    if not database.is_file() or database.stat().st_size < 4096:
        return None
    try:
        with closing(sqlite3.connect(database)) as connection:
            meta = dict(connection.execute("SELECT key, value FROM catalog_meta").fetchall())
        if int(meta.get("schema_version", 0)) != CATALOG_SCHEMA_VERSION:
            return None
        return {
            "entries": int(meta.get("entry_count", 0)),
            "builtAt": int(meta.get("built_at", 0)),
        }
    except (OSError, sqlite3.Error, ValueError):
        return None


class SearchIndex:
    """Local catalog search. The catalog is downloaded once and refreshed weekly."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._database_file = CACHE_DIR / "catalog.sqlite3"
        self._checked = False
        self._ready = False
        self._loading = False
        self._update_checked = False
        self._stage = "Not prepared"
        self._processed = 0
        self._total = 0
        self._count = 0
        self._built_at: Optional[int] = None
        self._error: Optional[str] = None
        self._failed_at = 0.0

    def status(self) -> Dict[str, Any]:
        with self._lock:
            if not self._checked:
                self._checked = True
                meta = read_catalog_meta(self._database_file)
                if meta:
                    self._ready = True
                    self._stage = "Ready"
                    self._count = meta["entries"]
                    self._built_at = meta["builtAt"]
            return {
                "loaded": self._ready,
                "ready": self._ready,
                "loading": self._loading,
                "stage": self._stage,
                "processed": self._processed,
                "total": self._total,
                "count": self._count,
                "loadedAt": self._built_at,
                "error": self._error,
                "cacheFile": str(self._database_file),
            }

    def ensure_started(self) -> bool:
        """Start a download if the catalog is missing or stale. Returns readiness."""
        self.status()
        with self._lock:
            if self._loading:
                return self._ready
            if self._ready:
                if self._update_checked:
                    return True
                self._update_checked = True
                if self._built_at and now_ms() - self._built_at < CATALOG_MAX_AGE_MS:
                    return True
            elif self._error and time.monotonic() - self._failed_at < CATALOG_RETRY_SECONDS:
                return False
            self._loading = True
            self._error = None
            if not self._ready:
                self._stage = "Checking for the game catalog"
            threading.Thread(target=self._download_catalog, daemon=True).start()
            return self._ready

    def _set_progress(self, stage: str, processed: int, total: int) -> None:
        with self._lock:
            if not self._ready:
                self._stage = stage
            self._processed = processed
            self._total = total

    def _download_catalog(self) -> None:
        temporary = self._database_file.with_name(self._database_file.name + ".download")
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            manifest = json.loads(fetch_bytes(CATALOG_MANIFEST_URL, timeout=30))
            if int(manifest["schema"]) != CATALOG_SCHEMA_VERSION:
                raise RuntimeError("the published catalog needs a newer MiNERVA Deck")
            with self._lock:
                current = self._built_at if self._ready else None
            if current is not None and int(manifest["builtAt"]) <= current:
                return

            size = int(manifest["size"])
            digest = hashlib.sha256()
            decompressor = lzma.LZMADecompressor()
            received = 0
            self._set_progress("Downloading the game catalog", 0, size)
            request = Request(
                f"{CATALOG_RELEASE_URL}/{quote(manifest['file'])}",
                headers={"User-Agent": USER_AGENT},
            )
            with urlopen(request, timeout=60) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(decompressor.decompress(chunk))
                    received += len(chunk)
                    self._set_progress("Downloading the game catalog", received, size)
            if not decompressor.eof:
                raise RuntimeError("the download was incomplete")
            if digest.hexdigest() != str(manifest["sha256"]).lower():
                raise RuntimeError("the download was corrupted")
            meta = read_catalog_meta(temporary)
            if not meta:
                raise RuntimeError("the downloaded file is not a valid catalog")

            temporary.replace(self._database_file)
            with self._lock:
                self._ready = True
                self._count = meta["entries"]
                self._built_at = meta["builtAt"]
                self._stage = "Ready"
                self._error = None
        except Exception as exc:
            with self._lock:
                # A failed weekly refresh keeps the existing catalog silently.
                if not self._ready:
                    self._error = f"Could not download the game catalog: {exc}"
                    self._stage = "Catalog download failed"
                    self._failed_at = time.monotonic()
        finally:
            temporary.unlink(missing_ok=True)
            with self._lock:
                self._loading = False

    def search(
        self,
        query: str,
        limit: int = MAX_SEARCH_RESULTS,
        games_only: bool = True,
        format_group: str = "",
    ) -> Optional[Dict[str, Any]]:
        if not self.ensure_started():
            return None

        normalized_query = normalized_match_text(query)
        tokens = normalized_query.split()
        if len(normalized_query) < 2 or not tokens:
            return {"results": [], "total": 0, "indexing": self.status()}

        fts_query = " AND ".join(f'"{token}"*' for token in tokens[:10])
        clauses = ["files_fts MATCH ?"]
        parameters: List[Any] = [fts_query]
        if games_only:
            clauses.append("f.kind = 1")
        if format_group in {"archive", "disc", "rom", "package"}:
            clauses.append("f.format_group = ?")
            parameters.append(FORMAT_GROUP_CODES[format_group])
        where = " AND ".join(clauses)

        with closing(sqlite3.connect(self._database_file)) as connection:
            connection.row_factory = sqlite3.Row
            total_row = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM files_fts
                JOIN files f ON f.id = files_fts.rowid
                WHERE {where}
                """,
                parameters,
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT
                    d.path AS directory, f.title, f.extension,
                    f.kind, f.format_group, f.file_index, f.size,
                    t.name AS torrent
                FROM files_fts
                JOIN files f ON f.id = files_fts.rowid
                JOIN directories d ON d.id = f.directory_id
                JOIN torrents t ON t.id = f.torrent_id
                WHERE {where}
                ORDER BY
                    CASE
                        -- "Title.ext" and "Title (USA).ext" both count as exact.
                        WHEN lower(substr(f.title, 1, length(f.title) - length(f.extension) - 1)) = ?
                            OR lower(f.title) LIKE ? THEN 0
                        WHEN lower(f.title) LIKE ? THEN 1
                        ELSE 2
                    END,
                    CASE
                        WHEN lower(d.path) LIKE 'no-intro/%' THEN 0
                        WHEN lower(d.path) LIKE 'redump/%' THEN 1
                        WHEN lower(d.path) LIKE 'retroachievements/%' THEN 2
                        ELSE 3
                    END,
                    length(f.title)
                LIMIT ?
                """,
                parameters
                + [normalized_query, normalized_query + " (%", normalized_query + "%", limit * 2],
            ).fetchall()

        results: List[Dict[str, Any]] = []
        seen = set()
        for row in rows:
            normalized = normalize_minerva_path(
                f'{row["directory"]}/{row["title"]}' if row["directory"] else row["title"]
            )
            parts = normalized.split("/")
            collection = parts[0] if len(parts) > 1 else ""
            section = parts[1] if len(parts) > 2 else ""
            dedupe_key = normalized_match_text(re.sub(r"\.[^.]+$", "", row["title"]))
            dedupe_key = (dedupe_key, row["extension"], section)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            route = emudeck_route_for_path(normalized)
            platform = (
                route["system"]
                if route
                else section if useful_catalog_section(section) else "Unknown system"
            )
            results.append(
                {
                    "path": normalized,
                    "normalizedPath": normalized,
                    "fileName": row["title"],
                    "collection": collection,
                    "system": platform,
                    "platform": platform,
                    "region": region_for_title(row["title"]),
                    "extension": row["extension"],
                    "kind": "game" if row["kind"] else "auxiliary",
                    "formatGroup": FORMAT_GROUP_NAMES.get(row["format_group"], ""),
                    "route": route,
                    "torrentUrl": TORRENT_LIST_URL + quote(row["torrent"]),
                    "fileIndex": int(row["file_index"]) + 1,
                    "sizeBytes": int(row["size"]),
                    "size": format_bytes(int(row["size"])),
                }
            )
            if len(results) >= limit:
                break

        total = int(total_row[0]) if total_row else 0
        return {
            "results": results,
            "total": total,
            "more": total > len(results),
            "indexing": self.status(),
        }


SEARCH_INDEX = SearchIndex()
