"""Small shared helpers without application-level dependencies."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen

from .config import USER_AGENT


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def now_ms() -> int:
    return int(time.time() * 1000)


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
    return f"{value:.2f} TB"


def path_stem_for_archive(path: Path) -> str:
    name = path.name
    lowered = name.lower()
    for suffix in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz"):
        if lowered.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def url_head_ok(url: str, timeout: int = 12) -> bool:
    request = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 400
    except Exception:
        return False


def fetch_bytes(url: str, timeout: int = 60) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def quote_path_for_url(path: str) -> str:
    return "/".join(quote(part) for part in path.split("/"))
