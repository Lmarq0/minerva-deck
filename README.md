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

- **Search** works offline. On first launch the app downloads a catalog of every file in MiNERVA's torrents (about 35 MB) and checks for a newer one weekly.
- **Destination:** pick your EmuDeck root (e.g. `/run/media/deck/<SD_CARD>/Emulation`) and games are routed to the right `roms/<system>` folder. Without EmuDeck, choose *Download on the main folder*.
- **Downloads** run one at a time. Only the selected file is downloaded, it is never seeded, and archives (ZIP, 7z, RAR, TAR) are extracted automatically.

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
