"""HTTP API and static-file server for the local web interface."""

from __future__ import annotations

import json
import hmac
import mimetypes
import secrets
import shutil
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

from .browsing import browse_root_payload, browse_subfolder_payload
from .catalog import SEARCH_INDEX
from .config import (
    APP_NAME,
    APP_VERSION,
    DATA_DIR,
    MINERVA_BASE,
    PUBLIC_ROOT,
    USER_AGENT,
    default_destination,
)
from .downloader import torrent_engine_status
from .jobs import JOBS
from .routes import EMUDECK_ROUTE_RULES, emudeck_route_for_path
from .storage import archive_engine_status
from .torrents import metadata_for_path
from .utils import json_bytes, quote_path_for_url


class AppHandler(BaseHTTPRequestHandler):
    server_version = f"MinervaDeck/{APP_VERSION}"
    session_token = ""
    desktop_runtime = False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            return self.serve_index()
        if path.startswith("/static/"):
            return self.serve_file(PUBLIC_ROOT / path.lstrip("/"))
        if path.startswith("/api/") and not self.api_authorized():
            return self.send_json({"error": "Forbidden"}, status=403)
        if path == "/api/status":
            return self.send_json(status_payload(self.desktop_runtime))
        if path == "/api/search":
            query = parse_qs(parsed.query)
            try:
                result = SEARCH_INDEX.search(
                    query.get("q", [""])[0],
                    games_only=query.get("gamesOnly", ["true"])[0].lower() != "false",
                    format_group=query.get("format", [""])[0],
                )
                if result is None:
                    return self.send_json(
                        {
                            "results": [],
                            "total": 0,
                            "indexing": SEARCH_INDEX.status(),
                        },
                        status=202,
                    )
                return self.send_json(result)
            except Exception as exc:
                return self.send_json({"error": str(exc)}, status=500)
        if path == "/api/route":
            full_path = parse_qs(parsed.query).get("path", [""])[0]
            route = emudeck_route_for_path(full_path)
            if route:
                return self.send_json({"route": route})
            return self.send_json(
                {"route": None, "error": "No EmuDeck folder mapping found"},
                status=404,
            )
        if path == "/api/browse":
            query = parse_qs(parsed.query)
            try:
                if query.get("mode", ["root"])[0] == "subfolder":
                    return self.send_json(
                        browse_subfolder_payload(
                            query.get("root", [""])[0],
                            query.get("path", [""])[0],
                        )
                    )
                return self.send_json(
                    browse_root_payload(query.get("path", [""])[0])
                )
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
            job = JOBS.get(path.rsplit("/", 1)[-1])
            if not job:
                return self.send_json({"error": "Job not found"}, status=404)
            return self.send_json(job)
        if path.startswith("/proxy/"):
            return self.proxy_minerva(path[len("/proxy/") :])
        return self.send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/") and not self.api_authorized():
            return self.send_json({"error": "Forbidden"}, status=403)
        if path != "/api/download":
            return self.send_json({"error": "Not found"}, status=404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 128 * 1024:
                return self.send_json(
                    {"error": "Invalid request size"},
                    status=400,
                )
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                return self.send_json(
                    {"error": "Download request must be an object"},
                    status=400,
                )
            job_id = JOBS.create(payload)
            JOBS.ensure_worker()
            return self.send_json({"id": job_id, "status": "queued"}, status=201)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, status=500)

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/proxy/"):
            return self.proxy_minerva(
                parsed.path[len("/proxy/") :],
                head_only=True,
            )
        if parsed.path == "/" or parsed.path.startswith("/static/"):
            file_path = PUBLIC_ROOT / (
                "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
            )
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

    def api_authorized(self) -> bool:
        supplied = self.headers.get("X-Minerva-Session", "")
        return bool(self.session_token) and hmac.compare_digest(
            supplied,
            self.session_token,
        )

    def serve_index(self) -> None:
        index_path = PUBLIC_ROOT / "index.html"
        if not index_path.is_file():
            return self.send_json({"error": "Interface assets are missing"}, status=500)
        body = index_path.read_text(encoding="utf-8").replace(
            "__MINERVA_SESSION_TOKEN__",
            self.session_token,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def serve_file(self, file_path: Path) -> None:
        resolved = file_path.resolve()
        public_root = PUBLIC_ROOT.resolve()
        if public_root not in resolved.parents and resolved != public_root:
            return self.send_json({"error": "Forbidden"}, status=403)
        if not resolved.exists() or not resolved.is_file():
            return self.send_json({"error": "Not found"}, status=404)
        content_type = (
            mimetypes.guess_type(str(resolved))[0]
            or "application/octet-stream"
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(resolved.stat().st_size))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        with resolved.open("rb") as handle:
            shutil.copyfileobj(handle, self.wfile)

    def proxy_minerva(self, resource: str, head_only: bool = False) -> None:
        resource = unquote(resource).lstrip("/")
        allowed = {
            "assets/hashes.db",
            "assets/index.txt.gz",
            "js/sqlite.worker.js",
            "js/sql-wasm.wasm",
        }
        if resource not in allowed:
            return self.send_json(
                {"error": "Proxy resource not allowed"},
                status=403,
            )

        headers = {"User-Agent": USER_AGENT}
        range_header = self.headers.get("Range")
        if range_header:
            headers["Range"] = range_header
        request = Request(
            f"{MINERVA_BASE}/{quote_path_for_url(resource)}",
            method="HEAD" if head_only else "GET",
            headers=headers,
        )
        try:
            with urlopen(request, timeout=120) as response:
                self.send_response(response.status)
                for header in (
                    "Content-Type",
                    "Content-Length",
                    "Accept-Ranges",
                    "Content-Range",
                    "Last-Modified",
                ):
                    value = response.headers.get(header)
                    if value:
                        self.send_header(header, value)
                self.end_headers()
                if not head_only:
                    shutil.copyfileobj(response, self.wfile)
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
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        stream = sys.stdout
        if stream is None:
            return
        try:
            stream.write(
                "[%s] %s\n" % (self.log_date_time_string(), format % args)
            )
        except (AttributeError, OSError):
            # Windowed packaged builds intentionally have no attached console.
            return


def status_payload(desktop_runtime: bool = False) -> Dict[str, Any]:
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "dataDir": str(DATA_DIR),
        "defaultDestination": default_destination(),
        "capabilities": {
            "torrentDownload": torrent_engine_status(),
            "archiveExtraction": archive_engine_status(),
        },
        "runtime": {"desktop": desktop_runtime},
        "searchIndex": SEARCH_INDEX.status(),
        "emudeckRoutes": len(EMUDECK_ROUTE_RULES),
    }


def create_server(
    host: str = "127.0.0.1",
    port: int = 0,
    *,
    desktop_runtime: bool = False,
    session_token: str = "",
) -> ThreadingHTTPServer:
    token = session_token or secrets.token_urlsafe(32)

    class RuntimeHandler(AppHandler):
        pass

    RuntimeHandler.session_token = token
    RuntimeHandler.desktop_runtime = desktop_runtime
    server = ThreadingHTTPServer((host, port), RuntimeHandler)
    server.daemon_threads = True
    return server
