"""Command-line startup for desktop, server-only, and packaged self-test modes."""

from __future__ import annotations

import argparse
import json
import os

from .config import APP_NAME, DATA_DIR, DEFAULT_PORT, PUBLIC_ROOT, ensure_dirs
from .downloader import torrent_engine_status
from .server import create_server
from .storage import archive_engine_status


def run_server(host: str, port: int) -> int:
    ensure_dirs()
    server = create_server(host, port, desktop_runtime=False)
    actual_port = server.server_address[1]
    print(f"{APP_NAME} server running at http://{host}:{actual_port}")
    print(f"Data directory: {DATA_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()
    return 0


def run_self_test() -> int:
    checks = {
        "frontend": (PUBLIC_ROOT / "index.html").is_file()
        and (PUBLIC_ROOT / "static" / "app.js").is_file(),
        "torrentDownload": torrent_engine_status()["ready"],
        "archiveExtraction": archive_engine_status()["ready"],
    }
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    except (ImportError, OSError):
        checks["desktop"] = False
    else:
        checks["desktop"] = True
    print(json.dumps(checks, indent=2))
    return 0 if all(checks.values()) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the MiNERVA Deck desktop app")
    parser.add_argument("--server-only", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", DEFAULT_PORT)),
    )
    parser.add_argument("--devtools", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()
    if args.server_only:
        return run_server(args.host, args.port)

    from .desktop import run_desktop

    return run_desktop(devtools=args.devtools)
