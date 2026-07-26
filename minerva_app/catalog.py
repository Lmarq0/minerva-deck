"""Disk-backed full-text catalog for the MiNERVA archive."""

from __future__ import annotations

import gzip
import re
import shutil
import sqlite3
import threading
from contextlib import closing
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

from .config import (
    CACHE_DIR,
    CATALOG_SCHEMA_VERSION,
    MAX_SEARCH_RESULTS,
    SEARCH_INDEX_URL,
    USER_AGENT,
)
from .routes import emudeck_route_for_path
from .utils import normalize_minerva_path, normalized_match_text, now_ms


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


class SearchIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._index_file = CACHE_DIR / "index.txt.gz"
        self._database_file = CACHE_DIR / "catalog.sqlite3"
        self._checked = False
        self._ready = False
        self._loading = False
        self._stage = "Not prepared"
        self._processed = 0
        self._count = 0
        self._loaded_at: Optional[int] = None
        self._error: Optional[str] = None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            if not self._checked:
                self._checked = True
                if self._database_is_valid():
                    self._ready = True
                    self._stage = "Ready"
                    self._count = self._database_count()
            return {
                "loaded": self._ready,
                "ready": self._ready,
                "loading": self._loading,
                "stage": self._stage,
                "processed": self._processed,
                "count": self._count,
                "loadedAt": self._loaded_at,
                "error": self._error,
                "cacheFile": str(self._database_file),
            }

    def _database_is_valid(self) -> bool:
        if not self._database_file.exists() or self._database_file.stat().st_size < 4096:
            return False
        try:
            with closing(sqlite3.connect(self._database_file)) as connection:
                row = connection.execute(
                    "SELECT value FROM catalog_meta WHERE key = 'schema_version'"
                ).fetchone()
                return bool(row and int(row[0]) == CATALOG_SCHEMA_VERSION)
        except (OSError, sqlite3.Error, ValueError):
            return False

    def _database_count(self) -> int:
        try:
            with closing(sqlite3.connect(self._database_file)) as connection:
                row = connection.execute("SELECT COUNT(*) FROM files").fetchone()
                return int(row[0]) if row else 0
        except sqlite3.Error:
            return 0

    def ensure_started(self) -> bool:
        if self.status()["ready"]:
            return True
        with self._lock:
            if self._loading:
                return False
            self._loading = True
            self._stage = "Starting"
            self._error = None
            threading.Thread(target=self._build_database, daemon=True).start()
        return False

    def _set_progress(self, stage: str, processed: Optional[int] = None) -> None:
        with self._lock:
            self._stage = stage
            if processed is not None:
                self._processed = processed

    def _download_index(self) -> None:
        temporary = self._index_file.with_suffix(".tmp")
        self._set_progress("Downloading archive index")
        request = Request(SEARCH_INDEX_URL, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(self._index_file)

    def _build_database(self) -> None:
        temporary_database = self._database_file.with_suffix(".sqlite3.tmp")
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            if not self._index_file.exists() or self._index_file.stat().st_size < 1024:
                self._download_index()
            if temporary_database.exists():
                temporary_database.unlink()
            if self._database_file.exists():
                self._database_file.unlink()

            self._set_progress("Preparing catalog", 0)
            connection = sqlite3.connect(temporary_database)
            try:
                connection.execute("PRAGMA journal_mode=OFF")
                connection.execute("PRAGMA synchronous=OFF")
                connection.execute("PRAGMA temp_store=MEMORY")
                connection.execute("PRAGMA cache_size=-32768")
                connection.executescript(
                    """
                    CREATE TABLE files (
                        id INTEGER PRIMARY KEY,
                        directory_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        extension TEXT NOT NULL,
                        kind INTEGER NOT NULL,
                        format_group INTEGER NOT NULL
                    );
                    CREATE TABLE directories (
                        id INTEGER PRIMARY KEY,
                        path TEXT NOT NULL UNIQUE
                    );
                    CREATE TABLE catalog_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE VIRTUAL TABLE files_fts USING fts5(
                        title_terms,
                        path_terms,
                        content='',
                        tokenize='unicode61 remove_diacritics 2'
                    );
                    """
                )

                file_batch: List[Tuple[int, int, str, str, int, int]] = []
                search_batch: List[Tuple[int, str, str]] = []
                directory_cache: Dict[str, int] = {}
                processed = 0

                def directory_id_for(path: str) -> int:
                    cached = directory_cache.get(path)
                    if cached is not None:
                        return cached
                    try:
                        cursor = connection.execute(
                            "INSERT INTO directories(path) VALUES (?)",
                            (path,),
                        )
                        directory_id = int(cursor.lastrowid)
                    except sqlite3.IntegrityError:
                        row = connection.execute(
                            "SELECT id FROM directories WHERE path = ?",
                            (path,),
                        ).fetchone()
                        if not row:
                            raise RuntimeError(f"Could not catalog directory: {path}")
                        directory_id = int(row[0])
                    if len(directory_cache) >= 200000:
                        directory_cache.clear()
                    directory_cache[path] = directory_id
                    return directory_id

                def flush_batches() -> None:
                    if not file_batch:
                        return
                    connection.executemany(
                        """
                        INSERT INTO files (
                            id, directory_id, title, extension, kind, format_group
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        file_batch,
                    )
                    connection.executemany(
                        "INSERT INTO files_fts(rowid, title_terms, path_terms) VALUES (?, ?, ?)",
                        search_batch,
                    )
                    file_batch.clear()
                    search_batch.clear()

                with gzip.open(self._index_file, "rt", encoding="utf-8", errors="replace") as handle:
                    for raw_line in handle:
                        original = raw_line.strip()
                        if not original:
                            continue
                        normalized = normalize_minerva_path(original)
                        parts = normalized.split("/")
                        title = parts[-1] if parts else original
                        directory_path = "/".join(parts[:-1])
                        extension = catalog_extension(title)
                        processed += 1
                        file_batch.append(
                            (
                                processed,
                                directory_id_for(directory_path),
                                title,
                                extension,
                                1 if catalog_kind(normalized, extension) == "game" else 0,
                                FORMAT_GROUP_CODES[catalog_format_group(extension)],
                            )
                        )
                        search_batch.append(
                            (
                                processed,
                                catalog_title_search_text(title),
                                catalog_parent_search_text(normalized),
                            )
                        )
                        if len(file_batch) >= 5000:
                            flush_batches()
                            if processed % 50000 == 0:
                                connection.commit()
                                self._set_progress("Organizing archive entries", processed)

                flush_batches()
                connection.commit()
                self._set_progress("Creating fast search", processed)
                connection.execute("CREATE INDEX files_kind_format ON files(kind, format_group)")
                connection.executemany(
                    "INSERT INTO catalog_meta(key, value) VALUES (?, ?)",
                    (
                        ("schema_version", str(CATALOG_SCHEMA_VERSION)),
                        ("entry_count", str(processed)),
                        ("built_at", str(now_ms())),
                    ),
                )
                connection.commit()
                connection.execute("PRAGMA optimize")
            finally:
                connection.close()

            temporary_database.replace(self._database_file)
            with self._lock:
                self._ready = True
                self._count = processed
                self._processed = processed
                self._loaded_at = now_ms()
                self._stage = "Ready"
                self._error = None
        except Exception as exc:
            with self._lock:
                self._error = str(exc)
                self._stage = "Catalog preparation failed"
            if temporary_database.exists():
                temporary_database.unlink()
        finally:
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
                    f.kind, f.format_group,
                    bm25(files_fts, 9.0, 1.0) AS relevance
                FROM files_fts
                JOIN files f ON f.id = files_fts.rowid
                JOIN directories d ON d.id = f.directory_id
                WHERE {where}
                ORDER BY
                    CASE
                        WHEN lower(substr(f.title, 1, length(f.title) - length(f.extension) - 1)) = ? THEN 0
                        WHEN lower(f.title) LIKE ? THEN 1
                        ELSE 2
                    END,
                    CASE
                        WHEN lower(d.path) LIKE 'no-intro/%' THEN 0
                        WHEN lower(d.path) LIKE 'retroachievements/%' THEN 1
                        ELSE 2
                    END,
                    CASE
                        WHEN lower(f.title) LIKE ? THEN length(f.title)
                        ELSE 100000
                    END,
                    relevance,
                    length(f.title)
                LIMIT ?
                """,
                parameters
                + [
                    normalized_query,
                    normalized_query + "%",
                    normalized_query + "%",
                    limit,
                ],
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
                }
            )

        return {
            "results": results,
            "total": int(total_row[0]) if total_row else 0,
            "indexing": self.status(),
        }


SEARCH_INDEX = SearchIndex()
