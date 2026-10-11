import configparser
import gzip
import hashlib
import json
import lzma
import ssl
import tempfile
import threading
import time
import tomllib
import unittest
import xml.etree.ElementTree as ElementTree
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import unquote
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from minerva_app import (
    catalog,
    config,
    desktop,
    downloader,
    jobs,
    routes,
    server,
    storage,
    torrents,
    utils,
)


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTest(unittest.TestCase):
    def test_release_versions_are_consistent(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        version = project["project"]["version"]
        self.assertEqual(config.APP_VERSION, version)

        vcpkg = json.loads((ROOT / "packaging" / "vcpkg.json").read_text("utf-8"))
        self.assertEqual(vcpkg["version-string"], version)

        appdata = ElementTree.parse(
            ROOT / "packaging" / "io.github.Lmarq0.minerva-deck.appdata.xml"
        )
        releases = appdata.getroot().find("releases")
        self.assertIsNotNone(releases)
        assert releases is not None
        self.assertEqual(releases[0].attrib["version"], version)

        windows_spec = configparser.ConfigParser()
        windows_spec.read(
            ROOT / "packaging" / "windows.pysidedeploy.spec",
            encoding="utf-8",
        )
        extra_args = windows_spec["nuitka"]["extra_args"]
        self.assertIn(f"--windows-file-version={version}.0", extra_args)
        self.assertIn(f"--windows-product-version={version}.0", extra_args)

    def test_build_dependency_pins_are_consistent(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        zstandard = next(
            dependency
            for dependency in project["project"]["optional-dependencies"]["build"]
            if dependency.startswith("zstandard==")
        )

        for spec_name in ("windows.pysidedeploy.spec", "deck.pysidedeploy.spec"):
            spec = configparser.ConfigParser()
            spec.read(ROOT / "packaging" / spec_name, encoding="utf-8")
            packages = spec["python"]["packages"].split(",")
            self.assertIn(zstandard, packages)


class CatalogHelpersTest(unittest.TestCase):
    def test_compound_extension_and_format_groups(self) -> None:
        self.assertEqual(catalog.catalog_extension("Game.tar.gz"), "tar.gz")
        self.assertEqual(catalog.catalog_format_group("tar.gz"), "archive")
        self.assertEqual(catalog.catalog_format_group("chd"), "disc")
        self.assertEqual(catalog.catalog_format_group("gba"), "rom")

    def test_auxiliary_files_are_not_games(self) -> None:
        path = "./MAME/EXTRAs/all_non-zipped_content/covers_SL/gba/metroid.png"
        self.assertEqual(catalog.catalog_kind(path, "png"), "auxiliary")
        self.assertEqual(
            catalog.catalog_kind(
                "./No-Intro/Nintendo - Nintendo Music (Tracks)/Metroid Theme (World).zip",
                "zip",
            ),
            "auxiliary",
        )
        self.assertEqual(
            catalog.catalog_kind("./Redump/Audio CD/Game Soundtrack (Japan).zip", "zip"),
            "auxiliary",
        )
        self.assertEqual(
            catalog.catalog_kind("./Hardware Target Game Database/SPC Music/Game.zip", "zip"),
            "auxiliary",
        )
        self.assertEqual(catalog.catalog_kind("./No-Intro/GBA/Metroid.gba", "gba"), "game")

    def test_region_detection(self) -> None:
        self.assertEqual(catalog.region_for_title("Metroid Fusion (USA).gba"), "USA")
        self.assertEqual(catalog.region_for_title("Metroid Fusion [Europe].gba"), "Europe")
        self.assertEqual(catalog.region_for_title("Metroid Fusion.gba"), "")


CATALOG_FIXTURE = [
    (
        "Minerva_Myrient - No-Intro - Nintendo - Super Nintendo Entertainment System.torrent",
        [
            (0, "No-Intro/Nintendo - Super Nintendo Entertainment System/Super Mario World (USA).sfc", 524288),
            (1, "No-Intro/Nintendo - Super Nintendo Entertainment System/.pad/12345", 100),
        ],
    ),
    (
        "Minerva_Myrient - MAME - EXTRAs.torrent",
        [(0, "MAME/EXTRAs/covers/Super Mario World (USA).png", 2048)],
    ),
    (
        "Minerva_Myrient - No-Intro - Nintendo - Game Boy Advance.torrent",
        [(0, "No-Intro/Nintendo - Game Boy Advance/Metroid Fusion (USA).gba", 8388608)]
        + [
            (number + 1, f"No-Intro/Nintendo - Game Boy Advance/Fixture Game {number:03d} (USA).gba", 1024)
            for number in range(30)
        ],
    ),
]


def write_catalog_release(folder: Path) -> tuple:
    """Build a catalog plus the compressed file and manifest the app downloads."""
    database = folder / "built.sqlite3"
    stats = catalog.build_catalog(database, CATALOG_FIXTURE)
    compressed = lzma.compress(database.read_bytes())
    manifest = {
        "schema": config.CATALOG_SCHEMA_VERSION,
        "file": "minerva-catalog-test.sqlite3.xz",
        "size": len(compressed),
        "sha256": hashlib.sha256(compressed).hexdigest(),
        **stats,
    }
    return manifest, compressed


def catalog_download_mocks(manifest: dict, compressed: bytes):
    response = mock.MagicMock()
    response.__enter__.return_value.read.side_effect = [compressed, b""]
    return (
        mock.patch.object(catalog, "fetch_bytes", return_value=json.dumps(manifest).encode()),
        mock.patch.object(catalog, "urlopen", return_value=response),
    )


class SearchIndexTest(unittest.TestCase):
    def test_built_catalog_searches_offline_with_torrent_details(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            index = catalog.SearchIndex()
            index._database_file = Path(folder) / "catalog.sqlite3"
            stats = catalog.build_catalog(index._database_file, CATALOG_FIXTURE)
            self.assertEqual(stats["entries"], 33)
            self.assertEqual(stats["torrents"], 3)

            with mock.patch.object(catalog, "urlopen", side_effect=AssertionError("offline")), \
                    mock.patch.object(catalog, "fetch_bytes", side_effect=AssertionError("offline")):
                result = index.search("super mario world")
                assert result is not None
                self.assertEqual(result["total"], 1)
                item = result["results"][0]
                self.assertEqual(item["fileName"], "Super Mario World (USA).sfc")
                self.assertEqual(item["platform"], "Nintendo Super Nintendo")
                self.assertEqual(item["fileIndex"], 1)
                self.assertEqual(item["sizeBytes"], 524288)
                self.assertEqual(
                    item["torrentUrl"],
                    "https://cdn.minerva-archive.org/Minerva_Myrient%20-%20No-Intro%20-%20"
                    "Nintendo%20-%20Super%20Nintendo%20Entertainment%20System.torrent",
                )
                self.assertEqual(index.search("super mario world", games_only=False)["total"], 2)
                self.assertEqual(index.search("metroid", format_group="rom")["total"], 1)
                self.assertEqual(index.search("metroid", format_group="disc")["total"], 0)
                limited = index.search("fixture game", limit=5)
                self.assertEqual(len(limited["results"]), 5)
                self.assertTrue(limited["more"])

    def test_missing_catalog_is_downloaded_and_verified(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manifest, compressed = write_catalog_release(Path(folder))
            index = catalog.SearchIndex()
            index._database_file = Path(folder) / "catalog.sqlite3"
            fetch_manifest, fetch_data = catalog_download_mocks(manifest, compressed)
            with fetch_manifest, fetch_data, mock.patch.object(catalog.threading, "Thread") as worker:
                self.assertIsNone(index.search("metroid fusion"))
                worker.assert_called_once()
                index._download_catalog()
            self.assertTrue(index.status()["ready"])
            self.assertEqual(index.status()["count"], 33)
            self.assertEqual(index.search("metroid fusion")["total"], 1)
            self.assertFalse(index._database_file.with_name("catalog.sqlite3.download").exists())

    def test_corrupt_catalog_download_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manifest, compressed = write_catalog_release(Path(folder))
            manifest["sha256"] = "0" * 64
            index = catalog.SearchIndex()
            index._database_file = Path(folder) / "catalog.sqlite3"
            fetch_manifest, fetch_data = catalog_download_mocks(manifest, compressed)
            with fetch_manifest, fetch_data:
                index._loading = True
                index._download_catalog()
            status = index.status()
            self.assertFalse(status["ready"])
            self.assertIn("corrupted", status["error"])
            self.assertFalse(index._database_file.exists())

    def test_failed_download_does_not_retry_on_every_poll(self) -> None:
        index = catalog.SearchIndex()
        index._checked = True
        index._error = "catalog download failed"
        index._failed_at = time.monotonic()
        with mock.patch.object(catalog.threading, "Thread") as worker:
            self.assertFalse(index.ensure_started())
            self.assertFalse(index.ensure_started())
            worker.assert_not_called()
            index._failed_at -= catalog.CATALOG_RETRY_SECONDS
            self.assertFalse(index.ensure_started())
            worker.assert_called_once()

    def test_stale_catalog_refreshes_once_in_background(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            index = catalog.SearchIndex()
            index._database_file = Path(folder) / "catalog.sqlite3"
            catalog.build_catalog(index._database_file, CATALOG_FIXTURE)
            index.status()
            index._built_at -= catalog.CATALOG_MAX_AGE_MS
            with mock.patch.object(catalog.threading, "Thread") as worker:
                self.assertTrue(index.ensure_started())
                self.assertTrue(index.ensure_started())
                worker.assert_called_once()

    def test_failed_refresh_keeps_existing_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            index = catalog.SearchIndex()
            index._database_file = Path(folder) / "catalog.sqlite3"
            catalog.build_catalog(index._database_file, CATALOG_FIXTURE)
            index.status()
            with mock.patch.object(catalog, "fetch_bytes", side_effect=OSError("offline")):
                index._loading = True
                index._download_catalog()
            status = index.status()
            self.assertTrue(status["ready"])
            self.assertIsNone(status["error"])
            self.assertEqual(index.search("metroid fusion")["total"], 1)

    def test_torrent_candidates_use_cdn_root(self) -> None:
        urls = torrents.candidate_torrent_urls(
            "", "No-Intro/Nintendo - Game Boy Advance/Fixture (USA).zip"
        )
        self.assertEqual(
            urls[0],
            "https://cdn.minerva-archive.org/"
            "Minerva_Myrient%20-%20No-Intro%20-%20Nintendo%20-%20Game%20Boy%20Advance.torrent",
        )
        self.assertFalse(any("/torrents/" in url for url in urls))


class CertificateTest(unittest.TestCase):
    def missing_defaults(self):
        return ssl.DefaultVerifyPaths(None, None, "SSL_CERT_FILE", "/usr/lib/ssl/cert.pem",
                                      "SSL_CERT_DIR", "/usr/lib/ssl/certs")

    def test_host_bundle_is_used_when_built_in_paths_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / "ca-certificates.crt"
            bundle.write_text("certs")
            with mock.patch.dict(utils.os.environ, {}, clear=True), \
                    mock.patch.object(utils.sys, "platform", "linux"), \
                    mock.patch.object(utils.ssl, "get_default_verify_paths", self.missing_defaults), \
                    mock.patch.object(utils, "CA_BUNDLE_CANDIDATES", ("/missing.crt", str(bundle))):
                utils.configure_ca_certificates()
                self.assertEqual(utils.os.environ.get("SSL_CERT_FILE"), str(bundle))

    def test_working_defaults_and_user_settings_are_left_alone(self) -> None:
        with mock.patch.dict(utils.os.environ, {}, clear=True), \
                mock.patch.object(utils.sys, "platform", "linux"):
            utils.configure_ca_certificates()  # this machine's defaults work
            self.assertNotIn("SSL_CERT_FILE", utils.os.environ)
        with mock.patch.dict(utils.os.environ, {"SSL_CERT_FILE": "/custom.pem"}, clear=True), \
                mock.patch.object(utils.sys, "platform", "linux"), \
                mock.patch.object(utils.ssl, "get_default_verify_paths", self.missing_defaults):
            utils.configure_ca_certificates()
            self.assertEqual(utils.os.environ["SSL_CERT_FILE"], "/custom.pem")


class PathSafetyTest(unittest.TestCase):
    def test_subfolder_validation(self) -> None:
        self.assertEqual(routes.validate_emudeck_subfolder("wiiu/roms"), "wiiu/roms")
        with self.assertRaises(RuntimeError):
            routes.validate_emudeck_subfolder("../outside")

    def test_archive_member_cannot_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(RuntimeError):
                storage.safe_extract_path(Path(temp_dir), "../outside.rom")
            with self.assertRaises(RuntimeError):
                storage.safe_extract_path(Path(temp_dir), "C:\\outside.rom")


class TorrentSelectionTest(unittest.TestCase):
    def test_parsed_file_indexes_are_zero_based(self) -> None:
        def encode(value):
            if isinstance(value, bytes):
                return str(len(value)).encode() + b":" + value
            if isinstance(value, int):
                return b"i" + str(value).encode() + b"e"
            if isinstance(value, list):
                return b"l" + b"".join(encode(item) for item in value) + b"e"
            if isinstance(value, dict):
                return (
                    b"d"
                    + b"".join(
                        encode(key) + encode(value[key])
                        for key in sorted(value)
                    )
                    + b"e"
                )
            raise TypeError(value)

        payload = encode(
            {
                b"info": {
                    b"files": [
                        {b"length": 3, b"path": [b"a.bin"]},
                        {b"length": 4, b"path": [b"b.bin"]},
                    ],
                    b"name": b"root",
                }
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "fixture.torrent"
            path.write_bytes(payload)
            root, files = torrents.parse_torrent(path)
        self.assertEqual(root, "root")
        self.assertEqual([item.index for item in files], [0, 1])
        self.assertEqual([item.path for item in files], ["a.bin", "b.bin"])

    def test_only_selected_file_receives_priority(self) -> None:
        self.assertEqual(
            downloader.selected_file_priorities(4, 2),
            [0, 0, 4, 0],
        )
        with self.assertRaises(RuntimeError):
            downloader.selected_file_priorities(2, 2)

    def test_selection_path_is_validated_against_engine_metadata(self) -> None:
        class FakeFiles:
            def num_files(self):
                return 2

            def file_path(self, index):
                return ["root/one.bin", "root/two.bin"][index]

            def file_size(self, index):
                return [3, 4][index]

        class FakeTorrentInfo:
            def files(self):
                return FakeFiles()

        selection = torrents.TorrentSelection(
            root_name="root",
            file=torrents.TorrentFile(index=1, path="two.bin", length=4),
            torrent_url="https://example.invalid/fixture.torrent",
            torrent_path=Path("fixture.torrent"),
        )
        downloader.validate_selection(FakeTorrentInfo(), selection)
        selection.file.path = "different.bin"
        with self.assertRaises(RuntimeError):
            downloader.validate_selection(FakeTorrentInfo(), selection)

    @unittest.skipUnless(
        downloader.torrent_engine_status()["ready"],
        "libtorrent runtime is not installed",
    )
    def test_selective_download_from_local_web_seed(self) -> None:
        import libtorrent as lt

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            (source / "unwanted.bin").write_bytes(b"not selected")
            wanted = b"selected-content" * 2048
            (source / "wanted.bin").write_bytes(wanted)

            class RangeHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    path = root / unquote(self.path).lstrip("/")
                    data = path.read_bytes()
                    start, end = 0, len(data) - 1
                    byte_range = self.headers.get("Range", "")
                    if byte_range.startswith("bytes="):
                        left, right = byte_range[6:].split("-", 1)
                        start = int(left or 0)
                        end = int(right or end)
                        self.send_response(206)
                        self.send_header(
                            "Content-Range",
                            f"bytes {start}-{end}/{len(data)}",
                        )
                    else:
                        self.send_response(200)
                    body = data[start : end + 1]
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, format, *args):
                    return

            web_seed = ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
            web_seed_thread = threading.Thread(
                target=web_seed.serve_forever,
                daemon=True,
            )
            web_seed_thread.start()
            try:
                files = lt.file_storage()
                lt.add_files(files, str(source))
                creator = lt.create_torrent(files)
                creator.add_url_seed(
                    f"http://127.0.0.1:{web_seed.server_address[1]}/"
                )
                lt.set_piece_hashes(creator, str(source.parent))
                torrent_path = root / "fixture.torrent"
                torrent_path.write_bytes(lt.bencode(creator.generate()))

                root_name, parsed_files = torrents.parse_torrent(torrent_path)
                selected = next(
                    item for item in parsed_files if item.path == "wanted.bin"
                )
                selection = torrents.TorrentSelection(
                    root_name=root_name,
                    file=selected,
                    torrent_url="local-web-seed",
                    torrent_path=torrent_path,
                )
                progress = []
                output = downloader.download_selected(
                    selection,
                    root / "download",
                    progress.append,
                    lambda message: None,
                    threading.Event(),
                )
                self.assertEqual(output.read_bytes(), wanted)
                self.assertEqual(progress[-1].downloaded_bytes, len(wanted))
                self.assertFalse((root / "download" / "source" / "unwanted.bin").exists())

                cancelled = threading.Event()
                cancelled.set()
                with self.assertRaises(downloader.DownloadCancelled):
                    downloader.download_selected(
                        selection,
                        root / "cancelled-download",
                        lambda value: None,
                        lambda message: None,
                        cancelled,
                    )
            finally:
                web_seed.shutdown()
                web_seed.server_close()
                web_seed_thread.join(timeout=2)


class ServerSecurityTest(unittest.TestCase):
    def test_ephemeral_server_requires_session_token(self) -> None:
        token = "fixture-token"
        httpd = server.create_server(
            "127.0.0.1",
            0,
            desktop_runtime=True,
            session_token=token,
        )
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        self.assertGreater(httpd.server_address[1], 0)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            with self.assertRaises(HTTPError) as error:
                urlopen(f"{base}/api/status", timeout=2)
            self.assertEqual(error.exception.code, 403)

            request = Request(
                f"{base}/api/status",
                headers={"X-Minerva-Session": token},
            )
            with urlopen(request, timeout=2) as response:
                payload = json.load(response)
            self.assertTrue(payload["runtime"]["desktop"])
            self.assertIn("torrentDownload", payload["capabilities"])

            with urlopen(base, timeout=2) as response:
                html = response.read().decode("utf-8")
            self.assertIn(token, html)
            self.assertIn(
                "Download on the main folder (not recommended using Emudeck)",
                html,
            )
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=2)

    def test_status_response_works_without_a_console_stream(self) -> None:
        token = "windowed-build-token"
        httpd = server.create_server(
            "127.0.0.1",
            0,
            desktop_runtime=True,
            session_token=token,
        )
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        request = Request(
            f"http://127.0.0.1:{httpd.server_address[1]}/api/status",
            headers={"X-Minerva-Session": token},
        )
        try:
            with mock.patch.object(server.sys, "stdout", None):
                with urlopen(request, timeout=2) as response:
                    payload = json.load(response)
            self.assertTrue(payload["runtime"]["desktop"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=2)


class JobHistoryTest(unittest.TestCase):
    def test_completed_jobs_persist_across_store_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "history.json"
            first_store = jobs.JobStore(history_path)
            job_id = first_store.create(
                {
                    "fileName": "Fixture Game.zip",
                    "fullPath": "./Fixture/Fixture Game.zip",
                }
            )
            first_store.update(
                job_id,
                status="done",
                stage="Done",
                progress=100,
                outputs=["C:/Games/Fixture Game.rom"],
                finishedAt=123456,
            )

            restored = jobs.JobStore(history_path).get(job_id)
            self.assertIsNotNone(restored)
            assert restored is not None
            self.assertEqual(restored["status"], "done")
            self.assertEqual(restored["progress"], 100)
            self.assertEqual(restored["outputs"], ["C:/Games/Fixture Game.rom"])

    def test_unfinished_persisted_job_becomes_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "history.json"
            first_store = jobs.JobStore(history_path)
            job_id = first_store.create({"fileName": "Interrupted Game.7z"})
            first_store.update(
                job_id,
                status="running",
                stage="Downloading selected file",
                progress=42,
            )

            restored = jobs.JobStore(history_path).get(job_id)
            self.assertIsNotNone(restored)
            assert restored is not None
            self.assertEqual(restored["status"], "error")
            self.assertEqual(restored["stage"], "Interrupted")
            self.assertIn("closed before", restored["error"])


class FrontendStructureTest(unittest.TestCase):
    def test_downloads_center_avoids_webengine_dialog_top_layer(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        html = (project_root / "public" / "index.html").read_text("utf-8")
        javascript = (project_root / "public" / "static" / "app.js").read_text("utf-8")

        self.assertIn('id="downloadsDialog"', html)
        self.assertIn('class="downloads-overlay"', html)
        self.assertNotIn('<dialog id="downloadsDialog"', html)
        self.assertNotIn("downloadsDialog.showModal()", javascript)
        self.assertNotIn("downloadsDialog.open", javascript)


class DesktopStartupTest(unittest.TestCase):
    def test_readiness_wait_allows_a_slow_first_status_response(self) -> None:
        token = "slow-start-token"

        class SlowStatusHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get("X-Minerva-Session") != token:
                    self.send_response(403)
                    self.end_headers()
                    return
                time.sleep(0.75)
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format, *args):
                return

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), SlowStatusHandler)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            desktop._wait_until_ready(
                f"http://127.0.0.1:{httpd.server_address[1]}",
                token,
                timeout=2,
            )
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=2)

    def test_desktop_failure_is_logged_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            failure = RuntimeError("fixture startup failure")
            with (
                mock.patch.object(desktop, "DATA_DIR", Path(temp_dir)),
                mock.patch.object(desktop, "_run_desktop", side_effect=failure),
                mock.patch.object(desktop, "_show_startup_failure") as show_error,
            ):
                self.assertEqual(desktop.run_desktop(), 1)

            log_path = Path(temp_dir) / desktop.STARTUP_LOG_NAME
            self.assertIn("fixture startup failure", log_path.read_text("utf-8"))
            show_error.assert_called_once_with(failure, log_path)


class ArchiveIntegrationTest(unittest.TestCase):
    def test_unsupported_rar_is_kept_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "game.rar"
            archive.write_bytes(b"fixture")
            destination = root / "roms"
            with mock.patch.object(
                storage,
                "extract_archive",
                side_effect=RuntimeError("unsupported RAR method"),
            ):
                result = storage.place_downloaded_file(
                    archive,
                    destination,
                    extract=True,
                )
            self.assertEqual(len(result.files), 1)
            self.assertEqual(result.files[0].read_bytes(), b"fixture")
            self.assertIn("kept as an archive", result.warnings[0])

    @unittest.skipUnless(
        storage.archive_engine_status()["ready"],
        "libarchive native runtime is not installed",
    )
    def test_libarchive_extracts_zip_tar_and_7z(self) -> None:
        import libarchive

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for format_name, suffix in (
                ("zip", ".zip"),
                ("gnutar", ".tar"),
                ("7zip", ".7z"),
            ):
                archive = root / f"fixture{suffix}"
                content = f"hello from {format_name}".encode()
                with libarchive.file_writer(str(archive), format_name) as writer:
                    writer.add_file_from_memory(
                        "nested/game.rom",
                        len(content),
                        content,
                    )
                target = root / f"extract-{format_name}"
                result = storage.extract_archive(archive, target)
                self.assertEqual(len(result.files), 1)
                self.assertEqual(result.files[0].read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
