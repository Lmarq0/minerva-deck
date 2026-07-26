"""Collect installed third-party license files for frozen release artifacts."""

from __future__ import annotations

import argparse
import importlib.metadata
import shutil
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


PACKAGES = ("PySide6", "shiboken6", "libtorrent", "libarchive-c")
REMOTE_LICENSES = {
    "LGPL-3.0.txt": (
        "https://raw.githubusercontent.com/qt/qtbase/v6.11.1/"
        "LICENSES/LGPL-3.0-only.txt"
    ),
    "libtorrent-COPYING.txt": (
        "https://raw.githubusercontent.com/arvidn/libtorrent/RC_2_0/COPYING"
    ),
    "libarchive-COPYING.txt": (
        "https://raw.githubusercontent.com/libarchive/libarchive/v3.8.7/COPYING"
    ),
    "libarchive-c-LICENSE.txt": (
        "https://raw.githubusercontent.com/Changaco/python-libarchive-c/5.3/LICENSE.md"
    ),
    "Chromium-LICENSE.txt": (
        "https://raw.githubusercontent.com/chromium/chromium/main/LICENSE"
    ),
}


def download_license(filename: str, url: str, output: Path) -> None:
    """Download a release notice, retrying transient network failures."""
    attempts = 4
    for attempt in range(1, attempts + 1):
        request = Request(url, headers={"User-Agent": "MiNERVA-Deck-build/1.0"})
        try:
            with urlopen(request, timeout=60) as response:
                output.write_bytes(response.read())
            print(f"Collected {filename}")
            return
        except (TimeoutError, URLError) as error:
            if attempt == attempts:
                raise RuntimeError(
                    f"Could not collect {filename} after {attempts} attempts: {error}"
                ) from error
            delay = attempt * 5
            print(
                f"Could not collect {filename} (attempt {attempt}/{attempts}): "
                f"{error}; retrying in {delay}s"
            )
            time.sleep(delay)


def copy_tree_files(source: Path, destination: Path) -> int:
    copied = 0
    if not source.exists():
        return copied
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--vcpkg-root", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    notice = Path(__file__).resolve().parent / "THIRD_PARTY_NOTICES.md"
    shutil.copy2(notice, args.output / notice.name)
    for filename, url in REMOTE_LICENSES.items():
        download_license(filename, url, args.output / filename)

    for package in PACKAGES:
        distribution = importlib.metadata.distribution(package)
        package_target = args.output / package
        for file in distribution.files or ():
            lowered = str(file).lower()
            if "license" not in lowered and not lowered.endswith(
                ("copying", "copyright")
            ):
                continue
            source = Path(distribution.locate_file(file))
            if source.is_file():
                target = package_target / Path(str(file)).name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    pyside_root = Path(importlib.metadata.distribution("PySide6").locate_file("PySide6"))
    copy_tree_files(pyside_root / "Qt" / "licenses", args.output / "Qt")
    copy_tree_files(pyside_root / "LICENSES", args.output / "PySide6")

    if args.vcpkg_root:
        for triplet in ("x64-windows", "x64-linux-dynamic"):
            share = args.vcpkg_root / triplet / "share" / "libarchive"
            copy_tree_files(share, args.output / "libarchive")


if __name__ == "__main__":
    main()
