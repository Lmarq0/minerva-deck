"""Build the offline catalog from every torrent on MiNERVA's CDN.

Run by .github/workflows/catalog.yml:

    python -m minerva_app.catalog_build OUTPUT_DIR

Writes ``minerva-catalog-<timestamp>.sqlite3.xz`` and the ``catalog.json``
manifest that the app reads to find and verify it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterator, List, Sequence, Tuple
from urllib.parse import quote

from .catalog import build_catalog
from .config import CATALOG_SCHEMA_VERSION, TORRENT_LIST_URL
from .torrents import parse_torrent_data, torrent_list
from .utils import fetch_bytes


DOWNLOAD_WORKERS = 8
DOWNLOAD_ATTEMPTS = 4


def fetch_file_list(name: str) -> Tuple[str, List[Tuple[int, str, int]]]:
    url = TORRENT_LIST_URL + quote(name)
    for attempt in range(DOWNLOAD_ATTEMPTS):
        try:
            _, files = parse_torrent_data(fetch_bytes(url, timeout=120))
            return name, [(file.index, file.path, file.length) for file in files]
        except Exception as exc:
            if attempt == DOWNLOAD_ATTEMPTS - 1:
                raise RuntimeError(f"{name}: {exc}") from exc
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def file_lists(names: Sequence[str]) -> Iterator[Tuple[str, List[Tuple[int, str, int]]]]:
    # Fetch in small batches so only a few parsed torrents are held in memory.
    with ThreadPoolExecutor(DOWNLOAD_WORKERS) as pool:
        for start in range(0, len(names), DOWNLOAD_WORKERS * 4):
            batch = names[start : start + DOWNLOAD_WORKERS * 4]
            yield from pool.map(fetch_file_list, batch)
            print(f"{min(start + len(batch), len(names))}/{len(names)} torrents", flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)

    names = sorted(
        dict.fromkeys(name for name in torrent_list() if name.endswith(".torrent"))
    )
    if not names:
        raise SystemExit("No torrents found on the CDN")

    args.output.mkdir(parents=True, exist_ok=True)
    database = args.output / "catalog.sqlite3"
    stats = build_catalog(database, file_lists(names))

    stamp = time.strftime("%Y%m%d%H%M", time.gmtime(stats["builtAt"] / 1000))
    archive = args.output / f"minerva-catalog-{stamp}.sqlite3.xz"
    with database.open("rb") as source, lzma.open(archive, "wb", preset=9) as target:
        shutil.copyfileobj(source, target, 1024 * 1024)
    database.unlink()

    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    manifest = {
        "schema": CATALOG_SCHEMA_VERSION,
        "file": archive.name,
        "size": archive.stat().st_size,
        "sha256": digest.hexdigest(),
        **stats,
    }
    (args.output / "catalog.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
