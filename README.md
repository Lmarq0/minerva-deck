# MiNERVA Deck

Search the [MiNERVA](https://minerva-archive.org) archive, pick one file from its torrent, and download it straight into your EmuDeck library. Built for Steam Deck Desktop Mode, with controller navigation.

> MiNERVA Deck does not provide any content. Only download material you are legally permitted to use.

## Install

Download the `.AppImage` from the [latest release](https://github.com/Lmarq0/minerva-deck/releases/latest), then:

```bash
chmod +x MiNERVA-Deck-*-steamdeck-x86_64.AppImage
./MiNERVA-Deck-*-steamdeck-x86_64.AppImage
```

Everything it needs (torrent engine, archive extraction, UI) is bundled.

## Usage

- **Search** works offline. On first launch the app downloads a catalog of every file in MiNERVA's torrents (about 41 MB) and checks for a newer one weekly. Results are grouped per game, with regions and revisions as versions; verified No-Intro and Redump dumps are marked.
- **Destination:** in Settings, choose your EmuDeck ROMs folder (e.g. `/run/media/deck/<SD_CARD>/Emulation/roms`). Each game goes into its system's folder, shown before you download. For systems EmuDeck doesn't know, pick a folder with *Change*, or turn on *Save unrecognized systems in the ROMs folder itself*.
- **Downloads** run one at a time. Only the selected file is downloaded, it is never seeded, and archives (ZIP, 7z, RAR, TAR) are extracted automatically.
- **Controls:** d-pad to move, A to select, B to go back, Y to search, L1/R1 to switch systems.

Box art comes from [libretro-thumbnails](https://github.com/libretro-thumbnails/libretro-thumbnails) and is cached locally.

Settings, history, and caches live in `~/.local/share/minerva-deck`. If the app fails to start, check `startup.log` there.

## Development

Requires Python 3.12 and Node.js 22.

```bash
python -m venv .venv && ./.venv/bin/pip install -e .
./.venv/bin/python minerva_deck.py            # run the app
./.venv/bin/python -m unittest discover -s tests
node --test tests/*.test.mjs
```

The UI is plain HTML/JS in `public/`, shown in a Qt WebEngine window and served by a token-protected local server in `minerva_app/`.

### Building the AppImage

On Ubuntu 22.04 (for a conservative glibc baseline), install the packages listed in `.github/workflows/release.yml`, then run `./build-deck.sh`. Output goes to `dist/`.

Pushing a `v*` tag builds the AppImage and publishes a GitHub release. The search catalog is rebuilt every Monday by the Catalog workflow (or run it manually) and published to the `catalog` release. Windows builds are no longer published; `build-windows.ps1` still works for local builds.
