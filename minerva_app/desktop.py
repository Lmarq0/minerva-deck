"""Native PySide6 window and lifecycle for the embedded MiNERVA interface."""

from __future__ import annotations

import ctypes
import os
import secrets
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from .config import APP_NAME, DATA_DIR, WEB_PROFILE_DIR, ensure_dirs
from .downloader import torrent_engine_status
from .jobs import JOBS
from .resources import resource_root
from .server import create_server
from .storage import archive_engine_status


INSTANCE_NAME = "minerva-deck-desktop"
STARTUP_TIMEOUT_SECONDS = 60.0
STARTUP_REQUEST_TIMEOUT_SECONDS = 30.0
STARTUP_LOG_NAME = "startup.log"


def _wait_until_ready(
    url: str,
    token: str,
    timeout: float = STARTUP_TIMEOUT_SECONDS,
) -> None:
    deadline = time.monotonic() + timeout
    retry_delay = 0.1
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            request = Request(
                f"{url}/api/status",
                headers={"X-Minerva-Session": token},
            )
            with urlopen(
                request,
                timeout=max(
                    0.1,
                    min(STARTUP_REQUEST_TIMEOUT_SECONDS, remaining),
                ),
            ) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
            time.sleep(min(retry_delay, max(0.0, deadline - time.monotonic())))
            retry_delay = min(retry_delay * 1.75, 1.0)
    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(
        f"The internal MiNERVA service did not become ready within "
        f"{timeout:g} seconds{detail}"
    ) from last_error


def _warm_runtime_capabilities() -> None:
    """Load packaged native engines before readiness polling begins."""
    torrent_engine_status()
    archive_engine_status()


def _write_startup_failure(exc: Exception) -> Path:
    ensure_dirs()
    log_path = DATA_DIR / STARTUP_LOG_NAME
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    traceback_text = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    try:
        if log_path.exists() and log_path.stat().st_size > 1024 * 1024:
            log_path.write_text("", encoding="utf-8")
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] MiNERVA Deck startup failed\n")
            handle.write(traceback_text)
            handle.write("\n")
    except OSError:
        pass
    return log_path


def _show_startup_failure(exc: Exception, log_path: Path) -> None:
    message = (
        "MiNERVA Deck could not start.\n\n"
        f"{exc}\n\n"
        f"Diagnostic details were written to:\n{log_path}"
    )
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                message,
                f"{APP_NAME} - Startup error",
                0x00000010,
            )
            return
        except Exception:
            pass
    print(message, file=sys.stderr)


def run_desktop(*, devtools: bool = False) -> int:
    try:
        return _run_desktop(devtools=devtools)
    except Exception as exc:
        log_path = _write_startup_failure(exc)
        _show_startup_failure(exc, log_path)
        return 1


def _run_desktop(*, devtools: bool = False) -> int:
    try:
        from PySide6.QtCore import QSettings, Qt, QUrl
        from PySide6.QtGui import (
            QAction,
            QCloseEvent,
            QColor,
            QFont,
            QIcon,
            QPainter,
            QPixmap,
        )
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import (
            QApplication,
            QDialog,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QSplashScreen,
            QTextBrowser,
            QVBoxLayout,
        )
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "The desktop runtime is unavailable. Install the project dependencies "
            "or use an official packaged build."
        ) from exc

    class LocalOnlyPage(QWebEnginePage):
        def __init__(self, profile, allowed_port: int, parent=None) -> None:
            super().__init__(profile, parent)
            self.allowed_port = allowed_port

        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
            if url.scheme() in {"http", "https"}:
                return url.host() in {"127.0.0.1", "localhost"} and (
                    url.port() == self.allowed_port
                )
            return url.scheme() in {"about", "data"}

    class DesktopWindow(QMainWindow):
        def __init__(
            self,
            app_url: str,
            app_port: int,
            shutdown_callback: Callable[[], None],
        ) -> None:
            super().__init__()
            self._shutdown_callback = shutdown_callback
            self._settings = QSettings("MiNERVA", APP_NAME)
            self._devtools_view = None
            self.setWindowTitle(APP_NAME)
            self.setMinimumSize(900, 650)
            self.resize(1280, 800)

            icon_path = resource_root() / "packaging" / "assets" / "minerva-deck.svg"
            if icon_path.is_file():
                self.setWindowIcon(QIcon(str(icon_path)))

            WEB_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            profile = QWebEngineProfile("minerva-deck", self)
            profile.setPersistentStoragePath(str(WEB_PROFILE_DIR / "storage"))
            profile.setCachePath(str(WEB_PROFILE_DIR / "cache"))

            self.web_view = QWebEngineView(self)
            self.page = LocalOnlyPage(profile, app_port, self.web_view)
            self.web_view.setPage(self.page)
            self.setCentralWidget(self.web_view)

            about_action = QAction("About MiNERVA Deck", self)
            about_action.triggered.connect(self.show_about)
            help_menu = self.menuBar().addMenu("&Help")
            help_menu.addAction(about_action)
            notices_action = QAction("Third-party notices", self)
            notices_action.triggered.connect(self.show_notices)
            help_menu.addAction(notices_action)

            if devtools:
                devtools_action = QAction("Developer Tools", self)
                devtools_action.setShortcut("F12")
                devtools_action.triggered.connect(self.show_devtools)
                self.menuBar().addMenu("&Developer").addAction(devtools_action)

            geometry = self._settings.value("window/geometry")
            if geometry:
                self.restoreGeometry(geometry)
            if self._settings.value("window/maximized", False, type=bool):
                self.showMaximized()
            self.web_view.setUrl(QUrl(app_url))

        def show_about(self) -> None:
            notices_path = (
                resource_root() / "packaging" / "THIRD_PARTY_NOTICES.md"
            )
            notice = ""
            if notices_path.is_file():
                notice = "\n\nThird-party notices are included with this build."
            QMessageBox.about(
                self,
                f"About {APP_NAME}",
                f"{APP_NAME}\n\nA local desktop client for the MiNERVA archive."
                f"{notice}",
            )

        def show_notices(self) -> None:
            notices_path = (
                resource_root() / "packaging" / "THIRD_PARTY_NOTICES.md"
            )
            text = (
                notices_path.read_text(encoding="utf-8")
                if notices_path.is_file()
                else "Third-party notices were not found in this build."
            )
            licenses_root = resource_root() / "licenses"
            if licenses_root.is_dir():
                for license_path in sorted(licenses_root.glob("*.txt")):
                    text += (
                        f"\n\n---\n\n## {license_path.name}\n\n"
                        + license_path.read_text(encoding="utf-8", errors="replace")
                    )
            dialog = QDialog(self)
            dialog.setWindowTitle("Third-party notices")
            dialog.resize(760, 620)
            layout = QVBoxLayout(dialog)
            browser = QTextBrowser(dialog)
            browser.setOpenExternalLinks(False)
            browser.setMarkdown(text)
            layout.addWidget(browser)
            close_button = QPushButton("Close", dialog)
            close_button.clicked.connect(dialog.accept)
            layout.addWidget(close_button)
            dialog.exec()

        def show_devtools(self) -> None:
            if self._devtools_view is None:
                self._devtools_view = QWebEngineView()
                self.page.setDevToolsPage(self._devtools_view.page())
                self._devtools_view.resize(1000, 700)
                self._devtools_view.setWindowTitle(f"{APP_NAME} Developer Tools")
            self._devtools_view.show()
            self._devtools_view.raise_()

        def bring_to_front(self) -> None:
            if self.isMinimized():
                self.showNormal()
            self.show()
            self.raise_()
            self.activateWindow()

        def closeEvent(self, event: QCloseEvent) -> None:
            if JOBS.has_active():
                choice = QMessageBox.question(
                    self,
                    "Stop active download?",
                    "A download is still active. Close MiNERVA Deck and stop it?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if choice != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
            self._settings.setValue("window/geometry", self.saveGeometry())
            self._settings.setValue("window/maximized", self.isMaximized())
            JOBS.cancel_all()
            self._shutdown_callback()
            event.accept()

    ensure_dirs()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("MiNERVA")

    existing = QLocalSocket()
    existing.connectToServer(INSTANCE_NAME)
    if existing.waitForConnected(200):
        existing.write(b"raise")
        existing.waitForBytesWritten(200)
        return 0

    QLocalServer.removeServer(INSTANCE_NAME)
    instance_server = QLocalServer(app)
    if not instance_server.listen(INSTANCE_NAME):
        raise RuntimeError("Could not establish the MiNERVA single-instance service")

    splash_pixmap = QPixmap(520, 260)
    splash_pixmap.fill(QColor("#0b111d"))
    painter = QPainter(splash_pixmap)
    icon_path = resource_root() / "packaging" / "assets" / "minerva-deck.png"
    if icon_path.is_file():
        icon = QPixmap(str(icon_path)).scaled(
            88,
            88,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(42, 42, icon)
    painter.setPen(QColor("#f1f5f9"))
    title_font = QFont()
    title_font.setPixelSize(30)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.drawText(152, 87, APP_NAME)
    painter.setPen(QColor("#89f0cb"))
    subtitle_font = QFont()
    subtitle_font.setPixelSize(14)
    subtitle_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
    painter.setFont(subtitle_font)
    painter.drawText(154, 116, "DESKTOP ARCHIVE")
    painter.end()

    splash = QSplashScreen(
        splash_pixmap,
        Qt.WindowType.WindowStaysOnTopHint,
    )
    splash.showMessage(
        "Loading download and archive engines...",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        QColor("#cbd5e1"),
    )
    splash.show()
    app.processEvents()

    _warm_runtime_capabilities()
    splash.showMessage(
        "Starting the private local service...",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        QColor("#cbd5e1"),
    )
    app.processEvents()

    token = secrets.token_urlsafe(32)
    server = create_server(
        "127.0.0.1",
        0,
        desktop_runtime=True,
        session_token=token,
    )
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = int(server.server_address[1])
    url = f"http://127.0.0.1:{port}"

    def shutdown() -> None:
        server.shutdown()
        server.server_close()

    try:
        _wait_until_ready(url, token)
        splash.showMessage(
            "Opening your library...",
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            QColor("#cbd5e1"),
        )
        app.processEvents()
        window = DesktopWindow(url, port, shutdown)

        def activate_existing() -> None:
            socket = instance_server.nextPendingConnection()
            if socket:
                socket.waitForReadyRead(100)
                socket.readAll()
                socket.disconnectFromServer()
            window.bring_to_front()

        instance_server.newConnection.connect(activate_existing)
        window.show()
        splash.finish(window)
        return app.exec()
    finally:
        splash.close()
        JOBS.cancel_all()
        if server_thread.is_alive():
            server.shutdown()
        server.server_close()
        instance_server.close()
