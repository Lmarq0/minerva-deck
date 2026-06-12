# MiNERVA Deck

Local web app for Steam Deck Desktop Mode that searches MiNERVA, selects one ROM entry from a grouped torrent, downloads only that torrent file entry, and optionally extracts the archive into your EmuDeck ROM library.

Use it only for files you have the legal right to download and use.

## Requirements

- Python 3
- `aria2c` for selective torrent downloads
- Optional `7z`, `7zz`, or `7za` for `.7z` and `.rar` extraction

`.zip` and common `.tar.*` archives are extracted with Python itself.

## Run On Steam Deck

From Desktop Mode, open Konsole in this folder:

```bash
chmod +x run-linux.sh
./run-linux.sh
```

Open `http://127.0.0.1:8765` if the browser does not open automatically.

## Run From Game Mode

Use the dedicated launcher:

```bash
chmod +x run-game-mode.sh
./run-game-mode.sh
```

To add it to Steam, switch to Desktop Mode, add `run-game-mode.sh` as a non-Steam game, then launch it from Game Mode. The script starts the local Python server, waits for it to respond, and opens the app in a fullscreen or kiosk browser when Chrome, Chromium, or Firefox is available.

Set **EmuDeck ROMs root** to the top-level folder, usually:

```bash
/run/media/deck/SDeck/Emulation/roms
```

The app defaults to `/run/media/deck/SDeck/Emulation/roms` on this Deck when that folder exists. Use **Browse** next to **EmuDeck ROMs root** to choose a different root folder.

The app detects the selected game's system and writes into the matching EmuDeck child folder, for example `gba`, `ps2`, `wiiu/roms`, or `switch`. If a system cannot be mapped, type the EmuDeck child folder in **System subfolder**, or use its **Browse** button to choose one from inside the selected ROMs root.

If you explicitly check **Download on the main folder (not recommended using Emudeck)**, unmapped ROMs can be placed directly in the top-level ROMs root. Leave this off for normal EmuDeck use.

## Controller Use

The web UI supports controller-style navigation:

- D-pad, left stick, or arrow keys move the focused control.
- A button or Enter activates the focused control.
- Checkboxes can be toggled with A or Enter.
- Text fields still use the Steam on-screen keyboard, usually Steam + X.

The app will show whether `aria2c` and `7z` are available. SteamOS package installs can be reset by OS updates, so install those tools using your preferred Deck package workflow.

## Run On Windows

```powershell
.\run-windows.ps1
```

## Notes

- The first search downloads MiNERVA's search index into the app cache.
- Metadata lookups are handled by the local server by resolving the grouped torrent and selected file index, so the browser no longer needs the MiNERVA SQLite/WASM metadata worker.
- Downloads are queued and processed one at a time.
- Downloads are staged under the app data directory, then moved or extracted into the detected EmuDeck system folder.
- Multi-file archive contents are placed in a subdirectory named after the selected archive.
