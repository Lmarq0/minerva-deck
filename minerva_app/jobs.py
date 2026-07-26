"""Queued selective-download jobs backed by the in-process torrent engine."""

from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import JOB_DIR, default_destination
from .downloader import DownloadProgress, download_selected
from .routes import emudeck_destination
from .storage import place_downloaded_file
from .torrents import resolve_torrent_selection
from .utils import now_ms


JOB_HISTORY_VERSION = 1
MAX_HISTORY_JOBS = 100
PROGRESS_PERSIST_INTERVAL_SECONDS = 5.0


def _history_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _history_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


class JobStore:
    def __init__(self, history_path: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []
        self._cancel_events: Dict[str, threading.Event] = {}
        self._worker: Optional[threading.Thread] = None
        self._history_path = history_path or (JOB_DIR / "history.json")
        self._last_persisted_at = 0.0
        self._load_history()

    def _load_history(self) -> None:
        if not self._history_path.is_file():
            return
        try:
            payload = json.loads(self._history_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        records = payload.get("jobs", []) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            return

        interrupted = False
        for record in records[-MAX_HISTORY_JOBS:]:
            if not isinstance(record, dict):
                continue
            job_id = str(record.get("id") or "").strip()
            if not job_id or job_id in self._jobs:
                continue
            job = {
                "id": job_id,
                "status": record.get("status") or "error",
                "stage": record.get("stage") or "Unknown",
                "progress": record.get("progress"),
                "rateBytes": _history_int(record.get("rateBytes")),
                "peers": _history_int(record.get("peers")),
                "createdAt": record.get("createdAt") or now_ms(),
                "updatedAt": record.get("updatedAt") or now_ms(),
                "startedAt": record.get("startedAt"),
                "finishedAt": record.get("finishedAt"),
                "payload": record.get("payload")
                if isinstance(record.get("payload"), dict)
                else {},
                "log": _history_list(record.get("log"))[-200:],
                "outputs": _history_list(record.get("outputs")),
                "warnings": _history_list(record.get("warnings")),
                "error": record.get("error"),
            }
            if record.get("emudeckFolder"):
                job["emudeckFolder"] = record["emudeckFolder"]
            if job["status"] in {"queued", "running"}:
                interrupted = True
                message = "MiNERVA Deck closed before this download finished."
                job.update(
                    status="error",
                    stage="Interrupted",
                    progress=None,
                    rateBytes=0,
                    peers=0,
                    finishedAt=now_ms(),
                    updatedAt=now_ms(),
                    error=message,
                )
                job["log"].append(message)
            self._jobs[job_id] = job
            self._order.append(job_id)

        if interrupted:
            with self._lock:
                self._persist_locked(force=True)

    def _trim_locked(self) -> None:
        while len(self._order) > MAX_HISTORY_JOBS:
            removable = next(
                (
                    job_id
                    for job_id in self._order
                    if self._jobs.get(job_id, {}).get("status")
                    not in {"queued", "running"}
                ),
                None,
            )
            if removable is None:
                break
            self._order.remove(removable)
            self._jobs.pop(removable, None)
            self._cancel_events.pop(removable, None)

    def _persist_locked(self, *, force: bool = False) -> None:
        current_time = time.monotonic()
        if (
            not force
            and current_time - self._last_persisted_at
            < PROGRESS_PERSIST_INTERVAL_SECONDS
        ):
            return
        self._trim_locked()
        payload = {
            "version": JOB_HISTORY_VERSION,
            "jobs": [
                self._jobs[job_id]
                for job_id in self._order
                if job_id in self._jobs
            ],
        }
        temporary_path = self._history_path.with_suffix(
            f"{self._history_path.suffix}.tmp"
        )
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_path.replace(self._history_path)
            self._last_persisted_at = current_time
        except OSError:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    def create(self, payload: Dict[str, Any]) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "status": "queued",
                "stage": "Queued",
                "progress": None,
                "rateBytes": 0,
                "peers": 0,
                "createdAt": now_ms(),
                "updatedAt": now_ms(),
                "startedAt": None,
                "finishedAt": None,
                "payload": payload,
                "log": [],
                "outputs": [],
                "warnings": [],
                "error": None,
            }
            self._cancel_events[job_id] = threading.Event()
            self._order.append(job_id)
            self._persist_locked(force=True)
        return job_id

    def update(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(updates)
            job["updatedAt"] = now_ms()
            force = bool(
                {
                    "status",
                    "finishedAt",
                    "outputs",
                    "warnings",
                    "error",
                }
                & updates.keys()
            )
            self._persist_locked(force=force)

    def log(self, job_id: str, message: str) -> None:
        clean = message.strip()
        if not clean:
            return
        with self._lock:
            job = self._jobs[job_id]
            job["log"].append(clean)
            job["log"] = job["log"][-200:]
            job["updatedAt"] = now_ms()
            self._persist_locked(force=True)

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return json.loads(json.dumps(job)) if job else None

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = [
                self._jobs[job_id]
                for job_id in self._order
                if job_id in self._jobs
            ]
            return json.loads(json.dumps(jobs))

    def next_queued(self) -> Optional[str]:
        with self._lock:
            for job_id in self._order:
                if self._jobs[job_id]["status"] == "queued":
                    return job_id
        return None

    def cancel_event(self, job_id: str) -> threading.Event:
        with self._lock:
            return self._cancel_events.setdefault(job_id, threading.Event())

    def cancel_all(self) -> None:
        with self._lock:
            for job_id, event in self._cancel_events.items():
                if self._jobs.get(job_id, {}).get("status") in {"queued", "running"}:
                    event.set()

    def has_active(self) -> bool:
        with self._lock:
            return any(
                job["status"] in {"queued", "running"}
                for job in self._jobs.values()
            )

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
    cancel_event = JOBS.cancel_event(job_id)
    work_directory = JOB_DIR / job_id
    download_directory = work_directory / "download"

    try:
        full_path = payload.get("fullPath") or ""
        torrent_hint = payload.get("torrent") or ""
        roms_root = Path(
            payload.get("romsRoot")
            or payload.get("destination")
            or default_destination()
        ).expanduser()
        system_folder_override = payload.get("systemFolderOverride") or ""
        allow_root_fallback = bool(payload.get("allowRomsRootFallback", False))
        extract = bool(payload.get("extract", True))
        if not full_path:
            raise RuntimeError("No ROM path was provided")
        if not payload.get("legalConfirm"):
            raise RuntimeError(
                "Confirm that you have the right to download this file before starting"
            )
        if cancel_event.is_set():
            raise RuntimeError("Download cancelled")

        destination, emudeck_folder, emudeck_system = emudeck_destination(
            roms_root,
            full_path,
            system_folder_override,
            allow_root_fallback,
        )
        JOBS.log(job_id, f"EmuDeck route: {emudeck_system} -> {emudeck_folder}")

        if work_directory.exists():
            shutil.rmtree(work_directory)
        download_directory.mkdir(parents=True, exist_ok=True)

        JOBS.update(
            job_id,
            status="running",
            stage="Resolving torrent",
            progress=None,
            startedAt=now_ms(),
        )
        selection = resolve_torrent_selection(
            torrent_hint,
            full_path,
            work_directory,
            lambda message: JOBS.log(job_id, message),
        )
        JOBS.log(job_id, f"Torrent: {selection.torrent_url}")
        JOBS.log(
            job_id,
            f"Selected file #{selection.file.index + 1}: {selection.file.path}",
        )

        def on_progress(progress: DownloadProgress) -> None:
            percent = (
                int(progress.downloaded_bytes * 100 / progress.total_bytes)
                if progress.total_bytes
                else 0
            )
            JOBS.update(
                job_id,
                stage="Downloading selected file",
                progress=max(0, min(100, percent)),
                rateBytes=progress.rate_bytes_per_second,
                peers=progress.peers,
            )

        JOBS.update(job_id, stage="Downloading selected file", progress=0)
        downloaded = download_selected(
            selection,
            download_directory,
            on_progress,
            lambda message: JOBS.log(job_id, message),
            cancel_event,
        )

        JOBS.update(job_id, stage="Placing files", progress=None)
        placement = place_downloaded_file(downloaded, destination, extract)
        warnings = list(placement.warnings)
        for warning in warnings:
            JOBS.log(job_id, f"Warning: {warning}")
        JOBS.update(
            job_id,
            status="done",
            stage="Done with warning" if warnings else "Done",
            progress=100,
            outputs=[str(path) for path in placement.files],
            warnings=warnings,
            emudeckFolder=emudeck_folder,
            finishedAt=now_ms(),
            rateBytes=0,
            peers=0,
        )
        JOBS.log(job_id, f"Output: {destination}")
    except Exception as exc:
        cancelled = cancel_event.is_set()
        JOBS.update(
            job_id,
            status="cancelled" if cancelled else "error",
            stage="Cancelled" if cancelled else "Error",
            error=str(exc),
            progress=None,
            finishedAt=now_ms(),
            rateBytes=0,
            peers=0,
        )
        JOBS.log(job_id, str(exc))
