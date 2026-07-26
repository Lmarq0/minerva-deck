# MiNERVA Deck

MiNERVA Deck is a native desktop application for finding a title in the MiNERVA catalog, selecting one file from its torrent, and routing the completed download to a normal folder or an EmuDeck library.

The application is distributed as:

- one portable Windows 10/11 x64 `.exe`;
- one Steam Deck Desktop Mode x86-64 `.AppImage`.

Both packages include the application runtime, torrent engine, archive support, and embedded web interface. They do not require Python, a separately installed browser, an external torrent client, or an external archive utility.

> MiNERVA Deck does not provide copyrighted content. Only download material you are legally permitted to use.

## Download and Run

Release files are created in `dist/` and attached to tagged GitHub releases:

```text
MiNERVA-Deck-{version}-windows-x64.exe
MiNERVA-Deck-{version}-steamdeck-x86_64.AppImage
SHA256SUMS.txt
```

### Windows

Download the `.exe` and open it. It is portable and does not need an installer.

Initial releases are unsigned, so Windows SmartScreen may display a warning. Verify the SHA-256 checksum before running a downloaded build:

```powershell
Get-FileHash .\MiNERVA-Deck-1.0.0-windows-x64.exe -Algorithm SHA256
```

### Steam Deck

Switch to Desktop Mode, download the AppImage, make it executable, and open it:

```bash
chmod +x MiNERVA-Deck-1.0.0-steamdeck-x86_64.AppImage
./MiNERVA-Deck-1.0.0-steamdeck-x86_64.AppImage
```

The release targets Steam Deck Desktop Mode. There is no separate gaming-session launcher.

To verify all files from a release:

```bash
sha256sum -c SHA256SUMS.txt
```

## What It Does

- Searches the cached MiNERVA catalog through a disk-backed SQLite full-text index.
- Loads torrent metadata and lets you select exactly one file.
- Downloads only the selected file and stops immediately after verification.
- Provides a Downloads center with selected-file progress, transfer rate, peer count, saved paths, logs, errors, warnings, and filters.
- Preserves the last 100 completed, failed, and cancelled download records across restarts.
- Extracts ZIP, TAR variants, 7z, RAR, and RAR5 archives when possible.
- Routes recognized systems to EmuDeck folders on internal storage or an SD card.
- Preserves keyboard and controller navigation.
- Remembers window geometry and the selected destination.
- Prevents a second launch from starting another backend; it focuses the existing window instead.

The first search downloads and indexes the public catalog. This can take a little longer because the catalog contains roughly three million records. Later searches use the local index and are normally near-instant.

## Download Destination

Choose an EmuDeck root such as:

```text
/run/media/deck/<SD_CARD_NAME>/Emulation
```

MiNERVA Deck maps supported systems into that root's `roms` directory. If no mapping is available, or if you do not want EmuDeck routing, choose:

**Download on the main folder (not recommended using Emudeck)**

That option is intentionally always available and preserves the original destination behavior.

## Downloads and Extraction

MiNERVA Deck downloads one item at a time.

The in-process torrent engine validates the selected file index and normalized path against the torrent metadata. Every other file receives priority zero. DHT, PEX, trackers, and web seeds are supported, and the torrent is removed from the session as soon as the selected file is verified. The app does not continue seeding.

A download is reported as stalled after ten minutes without byte progress. Active large downloads do not have a fixed total timeout. Closing the window during a download asks for confirmation and then shuts down the torrent session and local server cleanly.

Extraction is also performed in-process. Before writing a member, MiNERVA Deck rejects:

- absolute paths and directory traversal;
- symbolic links and hard links;
- devices and other special files;
- writes that would overwrite an existing destination file.

Regular files are streamed to disk, and available space is checked when archive sizes are known. If an encrypted or unsupported RAR cannot be extracted, the completed archive is kept in the chosen destination and the job finishes with a visible warning.

## Application Data

Catalog data, the search index, settings, WebEngine storage, and session state are stored outside the source or release directory:

- Windows: `%LOCALAPPDATA%\MinervaDeck`
- Linux: `$XDG_DATA_HOME/minerva-deck`, or `~/.local/share/minerva-deck`

Existing catalog caches, download history, and the `minerva.destination` interface preference are reused across upgrades. If the app closes before a download finishes, that job is retained as an interrupted record rather than silently disappearing.

Packaged desktop builds display a startup screen while their native components are loading. If startup cannot finish, MiNERVA Deck shows the error instead of exiting silently and writes diagnostic details to `startup.log` in this application-data directory.

## Architecture

The interface remains HTML, CSS, and JavaScript, but it is displayed inside a PySide6 Qt WebEngine window instead of the user's browser. Qt WebEngine may create its own bundled helper process; it does not launch or depend on an installed browser.

At startup, MiNERVA Deck:

1. creates a loopback `ThreadingHTTPServer` on an OS-selected port;
2. generates a random session token required by every `/api/*` request;
3. waits for the status endpoint to become ready;
4. opens the local interface inside the controlled desktop window.

Navigation away from the local application is blocked. On shutdown, the downloader, torrent session, HTTP server, and Qt application are stopped without leaving an application process behind.

The main modules are:

```text
minerva_deck.py                 Nuitka build entry point
minerva_app/cli.py              Command-line modes and self-test
minerva_app/desktop.py          Qt window, single-instance handling, lifecycle
minerva_app/server.py           Loopback HTTP server and authenticated API
minerva_app/catalog.py          Catalog download and SQLite FTS index
minerva_app/torrents.py         Torrent metadata and file selection
minerva_app/downloader.py       Selective in-process torrent download
minerva_app/jobs.py             Single-item job queue and progress state
minerva_app/storage.py          Safe extraction and destination routing
minerva_app/resources.py        Source and frozen-build resource resolution
public/                         HTML, CSS, and JavaScript interface
```

## Build Release Packages

Dependency versions are pinned in `pyproject.toml`, `packaging/vcpkg.json`, and the vcpkg baseline. Native build products are generated locally and are not committed to the repository.

### Windows build

Build on Windows 10/11 x64 with:

- Python 3.12;
- Git;
- Node.js 22;
- Visual Studio 2022 Build Tools with the Desktop development with C++ workload and a Windows SDK;
- network access for the pinned Python and native dependencies.

Then run:

```powershell
.\build-windows.ps1
```

The script creates an isolated build environment, bootstraps vcpkg, builds the native libraries, runs the test suite, creates the windowed one-file executable, and runs its packaged self-test.

Output:

```text
dist/MiNERVA-Deck-{version}-windows-x64.exe
```

The optional signing stage remains disabled until a code-signing certificate is configured.

### Steam Deck AppImage build

Build on Ubuntu 22.04 x86-64 to keep a conservative glibc baseline. Python 3.12 and Node.js 22 are required. Install the native build and Qt runtime prerequisites:

```bash
sudo apt-get update
sudo apt-get install -y \
  appstream build-essential cmake curl git ninja-build patchelf pkg-config \
  libasound2 libegl1 libgl1 libnspr4 libnss3 libx11-xcb1 libxcomposite1 \
  libxdamage1 libxkbcommon-x11-0 libxkbfile1 libxrandr2 libxtst6 \
  zip unzip zlib1g-dev
```

Then run:

```bash
chmod +x build-deck.sh
./build-deck.sh
```

The script creates a standalone Nuitka build, bundles Qt WebEngine and the native libraries, assembles an AppDir, creates the AppImage, and runs the packaged self-test.

Output:

```text
dist/MiNERVA-Deck-{version}-steamdeck-x86_64.AppImage
```

Each build also writes a `.sha256` file beside its artifact. The release workflow independently generates the combined `SHA256SUMS.txt` attached to a tagged release.

## Tests

Run the complete source suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check public\static\app.js
.\.venv\Scripts\python.exe -m minerva_app --self-test
```

On Linux, use `./.venv/bin/python` and `/` path separators.

The test suite covers selective torrent priorities, path verification, cancellation, errors, archive safety, authenticated loopback requests, ephemeral ports, resource resolution, and desktop imports. GitHub Actions runs the suite on Windows and Ubuntu and builds both release packages for version tags.

Third-party licenses for Python, Qt/Chromium, the torrent engine, libarchive, and their wrappers are available from the application's About dialog and in `packaging/THIRD_PARTY_NOTICES.md`.
