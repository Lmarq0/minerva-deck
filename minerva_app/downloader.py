"""In-process selective BitTorrent downloads powered by libtorrent."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

from .torrents import TorrentSelection, locate_downloaded_file
from .utils import normalize_minerva_path


STALL_TIMEOUT_SECONDS = 10 * 60
POLL_INTERVAL_SECONDS = 0.5
FATAL_ALERTS = {
    "file_error_alert",
    "metadata_failed_alert",
    "torrent_error_alert",
}


class DownloadCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class DownloadProgress:
    downloaded_bytes: int
    total_bytes: int
    rate_bytes_per_second: int
    peers: int


def _libtorrent():
    try:
        import libtorrent as lt
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "The libtorrent download engine is unavailable. "
            "Install the project dependencies or use an official packaged build."
        ) from exc
    return lt


def libtorrent_version() -> str:
    try:
        lt = _libtorrent()
        value = getattr(lt, "version", "unknown")
        version = str(value() if callable(value) else value)
        return version[:-2] if version.endswith(".0") else version
    except RuntimeError:
        return ""


def torrent_engine_status() -> dict:
    version = libtorrent_version()
    return {
        "ready": bool(version),
        "engine": "libtorrent",
        "version": version or None,
    }


def selected_file_priorities(file_count: int, selected_index: int) -> List[int]:
    if file_count <= 0:
        raise RuntimeError("Torrent contains no files")
    if selected_index < 0 or selected_index >= file_count:
        raise RuntimeError("Selected torrent file index is out of range")
    priorities = [0] * file_count
    priorities[selected_index] = 4
    return priorities


def _paths_match(engine_path: str, selected_path: str) -> bool:
    engine = normalize_minerva_path(engine_path).casefold()
    selected = normalize_minerva_path(selected_path).casefold()
    return (
        engine == selected
        or engine.endswith("/" + selected)
        or selected.endswith("/" + engine)
    )


def validate_selection(torrent_info, selection: TorrentSelection) -> None:
    files = torrent_info.files()
    file_count = files.num_files()
    index = selection.file.index
    if index < 0 or index >= file_count:
        raise RuntimeError("Selected torrent file index is out of range")
    engine_path = files.file_path(index)
    if not _paths_match(engine_path, selection.file.path):
        raise RuntimeError(
            "Torrent metadata changed: the selected file path no longer matches "
            f"index {index + 1}"
        )
    engine_size = int(files.file_size(index))
    if engine_size != selection.file.length:
        raise RuntimeError("Torrent metadata changed: selected file size no longer matches")


def _fatal_alert_message(alerts) -> str:
    for alert in alerts:
        if type(alert).__name__ in FATAL_ALERTS:
            return str(alert)
    return ""


def download_selected(
    selection: TorrentSelection,
    destination: Path,
    progress_callback: Callable[[DownloadProgress], None],
    log_callback: Callable[[str], None],
    cancel_event: threading.Event,
) -> Path:
    lt = _libtorrent()
    destination.mkdir(parents=True, exist_ok=True)
    torrent_info = lt.torrent_info(str(selection.torrent_path))
    validate_selection(torrent_info, selection)

    params = lt.add_torrent_params()
    params.ti = torrent_info
    params.save_path = str(destination)
    params.file_priorities = selected_file_priorities(
        torrent_info.files().num_files(),
        selection.file.index,
    )

    session = lt.session(
        {
            "listen_interfaces": "0.0.0.0:0",
            "enable_dht": True,
            "enable_lsd": True,
            "enable_upnp": True,
            "enable_natpmp": True,
            "alert_mask": int(lt.alert.category_t.error_notification),
        }
    )
    handle = None
    last_downloaded = 0
    last_progress_at = time.monotonic()
    try:
        handle = session.add_torrent(params)
        log_callback(f"libtorrent {libtorrent_version()} started")
        log_callback(
            f"Selected file #{selection.file.index + 1}: {selection.file.path}"
        )

        while True:
            if cancel_event.is_set():
                raise DownloadCancelled("Download cancelled")

            alerts = session.pop_alerts()
            fatal = _fatal_alert_message(alerts)
            if fatal:
                raise RuntimeError(fatal)

            progress_values = handle.file_progress()
            downloaded = (
                min(int(progress_values[selection.file.index]), selection.file.length)
                if len(progress_values) > selection.file.index
                else 0
            )
            status = handle.status()
            progress_callback(
                DownloadProgress(
                    downloaded_bytes=downloaded,
                    total_bytes=selection.file.length,
                    rate_bytes_per_second=max(0, int(status.download_rate)),
                    peers=max(0, int(status.num_peers)),
                )
            )

            if downloaded >= selection.file.length:
                break
            if downloaded > last_downloaded:
                last_downloaded = downloaded
                last_progress_at = time.monotonic()
            elif time.monotonic() - last_progress_at >= STALL_TIMEOUT_SECONDS:
                raise RuntimeError(
                    "Download stalled for ten minutes without receiving data"
                )
            cancel_event.wait(POLL_INTERVAL_SECONDS)

        progress_callback(
            DownloadProgress(
                downloaded_bytes=selection.file.length,
                total_bytes=selection.file.length,
                rate_bytes_per_second=0,
                peers=0,
            )
        )
    finally:
        if handle is not None:
            try:
                session.remove_torrent(handle)
            except Exception:
                pass

    return locate_downloaded_file(
        destination,
        selection.root_name,
        selection.file.path,
    )
