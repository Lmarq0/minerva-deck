"""Safely extract and place downloaded files without external executables."""

from __future__ import annotations

import os
import shutil
import stat
from importlib import import_module
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from .config import ARCHIVE_EXTENSIONS
from .resources import native_library_path
from .utils import path_stem_for_archive, safe_filename


LIBARCHIVE_EXPECTED_VERSION = "3.8.7"
_DLL_DIRECTORY_HANDLE = None


@dataclass
class ExtractionResult:
    files: List[Path]
    warnings: List[str]


def _libarchive():
    global _DLL_DIRECTORY_HANDLE
    configured = os.environ.get("LIBARCHIVE")
    bundled = (
        Path(configured).expanduser()
        if configured and Path(configured).expanduser().is_file()
        else native_library_path("archive")
    )
    if bundled:
        os.environ.setdefault("LIBARCHIVE", str(bundled))
        if os.name == "nt" and hasattr(os, "add_dll_directory"):
            if _DLL_DIRECTORY_HANDLE is None:
                _DLL_DIRECTORY_HANDLE = os.add_dll_directory(str(bundled.parent))
    try:
        import libarchive
    except (ImportError, OSError, TypeError) as exc:
        raise RuntimeError(
            "The archive engine is unavailable. Install the project dependencies "
            "or use an official packaged build."
        ) from exc
    return libarchive


def archive_engine_status() -> dict:
    try:
        _libarchive()
    except RuntimeError:
        return {
            "ready": False,
            "engine": "libarchive",
            "version": None,
            "formats": ["zip", "tar", "7z", "rar"],
        }
    version = LIBARCHIVE_EXPECTED_VERSION
    try:
        number = int(import_module("libarchive.ffi").version_number())
        version = f"{number // 1_000_000}.{(number // 1_000) % 1_000}.{number % 1_000}"
    except Exception:
        pass
    return {
        "ready": True,
        "engine": "libarchive",
        "version": version,
        "formats": ["zip", "tar", "7z", "rar"],
    }


def is_archive(path: Path) -> bool:
    return any(path.name.lower().endswith(extension) for extension in ARCHIVE_EXTENSIONS)


def safe_extract_path(base: Path, member_name: str) -> Path:
    normalized = member_name.replace("\\", "/")
    if normalized.startswith("/") or (
        len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha()
    ):
        raise RuntimeError(f"Archive member uses an absolute path: {member_name}")
    destination = (base / Path(*normalized.split("/"))).resolve()
    base_resolved = base.resolve()
    if base_resolved != destination and base_resolved not in destination.parents:
        raise RuntimeError(f"Archive member escapes extraction directory: {member_name}")
    return destination


def _entry_flag(entry, name: str) -> bool:
    value = getattr(entry, name, False)
    return bool(value() if callable(value) else value)


def _entry_kind(entry) -> str:
    mode = int(getattr(entry, "mode", 0) or 0)
    if stat.S_ISDIR(mode) or _entry_flag(entry, "isdir"):
        return "directory"
    if stat.S_ISREG(mode) or _entry_flag(entry, "isfile") or _entry_flag(entry, "isreg"):
        return "file"
    return "special"


def _entry_is_link(entry) -> bool:
    return (
        _entry_flag(entry, "islnk")
        or _entry_flag(entry, "issym")
        or bool(getattr(entry, "hardlink", None))
        or bool(getattr(entry, "symlink", None))
    )


def _validated_entries(archive: Path, target: Path) -> Iterable[tuple[str, Path, int]]:
    libarchive = _libarchive()
    seen_paths = set()
    with libarchive.file_reader(str(archive)) as entries:
        for entry in entries:
            name = str(getattr(entry, "pathname", "") or "")
            if not name:
                raise RuntimeError("Archive contains an unnamed entry")
            destination = safe_extract_path(target, name)
            normalized_destination = os.path.normcase(str(destination))
            if normalized_destination in seen_paths:
                raise RuntimeError(f"Archive contains a duplicate path: {name}")
            seen_paths.add(normalized_destination)
            if _entry_is_link(entry):
                raise RuntimeError(f"Archive links are not allowed: {name}")
            kind = _entry_kind(entry)
            if kind == "special":
                raise RuntimeError(f"Archive special entries are not allowed: {name}")
            yield kind, destination, max(0, int(getattr(entry, "size", 0) or 0))


def extract_archive(archive: Path, target: Path) -> ExtractionResult:
    target.mkdir(parents=True, exist_ok=True)
    entries = list(_validated_entries(archive, target))
    required_bytes = sum(size for kind, _, size in entries if kind == "file")
    free_bytes = shutil.disk_usage(target).free
    if required_bytes and free_bytes < required_bytes:
        raise RuntimeError(
            f"Not enough disk space to extract {archive.name}: "
            f"{required_bytes:,} bytes required"
        )

    libarchive = _libarchive()
    extracted: List[Path] = []
    with libarchive.file_reader(str(archive)) as archive_entries:
        for entry in archive_entries:
            name = str(getattr(entry, "pathname", "") or "")
            destination = safe_extract_path(target, name)
            if _entry_is_link(entry):
                raise RuntimeError(f"Archive links are not allowed: {name}")
            kind = _entry_kind(entry)
            if kind == "directory":
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if kind != "file":
                raise RuntimeError(f"Archive special entries are not allowed: {name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as output:
                for block in entry.get_blocks():
                    output.write(block)
            extracted.append(destination)

    if not extracted:
        raise RuntimeError("Archive extraction produced no files")
    return ExtractionResult(files=extracted, warnings=[])


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10000):
        candidate = path.parent / f"{path.stem} ({index}){path.suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find an available filename for {path.name}")


def move_unique(source: Path, target: Path) -> Path:
    target = unique_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    return target


def move_tree_contents(source: Path, destination: Path, base_name: str) -> List[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    files = [path for path in source.rglob("*") if path.is_file()]
    if not files:
        raise RuntimeError("Archive extraction produced no files")
    if len(files) == 1:
        return [move_unique(files[0], destination / files[0].name)]

    game_directory = unique_path(destination / safe_filename(base_name))
    game_directory.mkdir(parents=True, exist_ok=False)
    moved: List[Path] = []
    for path in files:
        target = game_directory / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        moved.append(move_unique(path, target))
    return moved


def place_downloaded_file(
    downloaded: Path,
    destination: Path,
    extract: bool,
) -> ExtractionResult:
    destination = destination.expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    if extract and is_archive(downloaded):
        extract_directory = downloaded.parent / "_extracted"
        if extract_directory.exists():
            shutil.rmtree(extract_directory)
        extract_directory.mkdir(parents=True, exist_ok=True)
        try:
            extraction = extract_archive(downloaded, extract_directory)
            moved = move_tree_contents(
                extract_directory,
                destination,
                path_stem_for_archive(downloaded),
            )
            return ExtractionResult(files=moved, warnings=extraction.warnings)
        except Exception as exc:
            if downloaded.name.lower().endswith(".rar"):
                output = move_unique(downloaded, destination / downloaded.name)
                return ExtractionResult(
                    files=[output],
                    warnings=[
                        "This RAR could not be extracted by the bundled archive "
                        f"engine and was kept as an archive: {exc}"
                    ],
                )
            raise
    return ExtractionResult(
        files=[move_unique(downloaded, destination / downloaded.name)],
        warnings=[],
    )
