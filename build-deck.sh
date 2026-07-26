#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3.12}"
VENV="$PWD/.venv-build-deck"
VCPKG="$PWD/build/deck-vcpkg"
INSTALLED="$PWD/build/deck-vcpkg_installed"
NATIVE="$PWD/build/deck-native"
LICENSES="$PWD/build/deck-licenses"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)"
ARTIFACT="MiNERVA-Deck-${VERSION}-steamdeck-x86_64.AppImage"

if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -e '.[build]'
QT_QPA_PLATFORM=offscreen "$VENV/bin/python" packaging/generate_icons.py --png-only

if [ ! -d "$VCPKG/.git" ]; then
  git clone https://github.com/microsoft/vcpkg.git "$VCPKG"
fi
git -C "$VCPKG" fetch --depth 1 origin 40f3c709db80acf154ac4b17a1f83c564ebd022e
git -C "$VCPKG" checkout --detach 40f3c709db80acf154ac4b17a1f83c564ebd022e
"$VCPKG/bootstrap-vcpkg.sh" -disableMetrics
"$VCPKG/vcpkg" install \
  --x-manifest-root="$PWD/packaging" \
  --x-install-root="$INSTALLED" \
  --overlay-triplets="$PWD/packaging/triplets" \
  --triplet=x64-linux-dynamic

mkdir -p "$NATIVE" "$PWD/dist"
cp -a "$INSTALLED/x64-linux-dynamic/lib/"*.so* "$NATIVE/"
export LIBARCHIVE="$(find "$NATIVE" -maxdepth 1 -name 'libarchive.so*' | head -n 1)"
"$VENV/bin/python" packaging/collect_licenses.py \
  --output "$LICENSES" \
  --vcpkg-root "$INSTALLED"

"$VENV/bin/python" -m unittest discover -s tests -v
node --check public/static/app.js
node --check public/static/controller.js
node --test tests/controller_navigation.test.mjs

rm -rf "$PWD/build/deck" "$PWD/build/AppDir"
"$VENV/bin/python" -m nuitka \
  --mode=standalone \
  --assume-yes-for-downloads \
  --enable-plugin=pyside6 \
  --user-package-configuration-file=packaging/nuitka-package.config.yml \
  --output-dir="$PWD/build/deck" \
  --output-filename=minerva-deck \
  --include-data-dir=public=public \
  --include-data-dir=packaging=packaging \
  --include-data-dir="$LICENSES"=licenses \
  minerva_deck.py

APPDIR="$PWD/build/AppDir"
mkdir -p \
  "$APPDIR/usr/bin" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/icons/hicolor/512x512/apps" \
  "$APPDIR/usr/share/metainfo"
DIST_DIR="$(find "$PWD/build/deck" -maxdepth 1 -type d -name '*.dist' | head -n 1)"
if [ -z "$DIST_DIR" ]; then
  echo "Nuitka did not produce a standalone distribution directory."
  exit 1
fi
cp -a "$DIST_DIR/." "$APPDIR/usr/bin/"
if [ -f "$APPDIR/usr/bin/minerva-deck.bin" ]; then
  mv "$APPDIR/usr/bin/minerva-deck.bin" "$APPDIR/usr/bin/minerva-deck"
fi
cp packaging/assets/minerva-deck.png \
  "$APPDIR/usr/share/icons/hicolor/512x512/apps/minerva-deck.png"
cp packaging/io.github.Lmarq0.minerva-deck.desktop \
  "$APPDIR/io.github.Lmarq0.minerva-deck.desktop"
cp packaging/io.github.Lmarq0.minerva-deck.desktop \
  "$APPDIR/usr/share/applications/io.github.Lmarq0.minerva-deck.desktop"
cp packaging/io.github.Lmarq0.minerva-deck.appdata.xml \
  "$APPDIR/usr/share/metainfo/io.github.Lmarq0.minerva-deck.appdata.xml"
cp packaging/assets/minerva-deck.png "$APPDIR/minerva-deck.png"
cp packaging/AppRun "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun" "$APPDIR/usr/bin/minerva-deck"

APPIMAGETOOL="$PWD/build/appimagetool-x86_64.AppImage"
APPIMAGETOOL_VERSION="1.9.1"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
if [ ! -x "$APPIMAGETOOL" ]; then
  curl -L --fail \
    "https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/appimagetool-x86_64.AppImage" \
    -o "$APPIMAGETOOL"
  chmod +x "$APPIMAGETOOL"
fi
echo "${APPIMAGETOOL_SHA256}  ${APPIMAGETOOL}" | sha256sum --check
ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run \
  "$APPDIR" "$PWD/dist/$ARTIFACT"
chmod +x "$PWD/dist/$ARTIFACT"
"$PWD/dist/$ARTIFACT" --appimage-extract-and-run --self-test
(
  cd "$PWD/dist"
  sha256sum "$ARTIFACT" | tee "$ARTIFACT.sha256"
)
