#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/minerva-deck"
mkdir -p "$LOG_DIR"
export PATH="$PWD/bin:$PWD/vendor/aria2/usr/bin:$PATH"
if [ -d "$PWD/vendor/aria2/usr/lib" ]; then
  export LD_LIBRARY_PATH="$PWD/vendor/aria2/usr/lib:${LD_LIBRARY_PATH:-}"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3 or set PYTHON_BIN."
  read -r -p "Press Enter to close..."
  exit 1
fi

status_ok() {
  local url="http://${HOST}:$1/api/status"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS "$url" >/dev/null 2>&1
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O /dev/null "$url" >/dev/null 2>&1
  else
    "$PYTHON_BIN" - "$url" <<'PY' >/dev/null 2>&1
import sys
from urllib.request import urlopen
with urlopen(sys.argv[1], timeout=2) as response:
    raise SystemExit(0 if response.status == 200 else 1)
PY
  fi
}

port_free() {
  "$PYTHON_BIN" - "$HOST" "$1" <<'PY' >/dev/null 2>&1
import socket
import sys
host, port = sys.argv[1], int(sys.argv[2])
sock = socket.socket()
try:
    sock.bind((host, port))
finally:
    sock.close()
PY
}

SERVER_PID=""
SERVER_STARTED=0

for candidate in $(seq "$PORT" "$((PORT + 20))"); do
  if status_ok "$candidate"; then
    PORT="$candidate"
    break
  fi
  if port_free "$candidate"; then
    PORT="$candidate"
    "$PYTHON_BIN" minerva_deck.py --host "$HOST" --port "$PORT" --no-browser \
      >"$LOG_DIR/server.log" 2>"$LOG_DIR/server.err.log" &
    SERVER_PID=$!
    SERVER_STARTED=1
    break
  fi
done

URL="http://${HOST}:${PORT}"

cleanup() {
  if [ "$SERVER_STARTED" = "1" ] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 80); do
  if status_ok "$PORT"; then
    break
  fi
  if [ "$SERVER_STARTED" = "1" ] && ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    wait "$SERVER_PID"
    exit $?
  fi
  sleep 0.25
done

if ! status_ok "$PORT"; then
  echo "MiNERVA Deck did not become ready on $URL"
  read -r -p "Press Enter to close..."
  exit 1
fi

launch_browser() {
  if command -v flatpak >/dev/null 2>&1 && flatpak info com.google.Chrome >/dev/null 2>&1; then
    flatpak run com.google.Chrome --kiosk --app="$URL" --no-first-run
    return
  fi

  if command -v flatpak >/dev/null 2>&1 && flatpak info org.chromium.Chromium >/dev/null 2>&1; then
    flatpak run org.chromium.Chromium --kiosk --app="$URL" --no-first-run
    return
  fi

  if command -v google-chrome >/dev/null 2>&1; then
    google-chrome --kiosk --app="$URL" --no-first-run
    return
  fi

  if command -v chromium >/dev/null 2>&1; then
    chromium --kiosk --app="$URL" --no-first-run
    return
  fi

  if command -v firefox >/dev/null 2>&1; then
    firefox --kiosk "$URL"
    return
  fi

  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL"
    if [ "$SERVER_STARTED" = "1" ]; then
      wait "$SERVER_PID"
    fi
    return
  fi

  echo "MiNERVA Deck is running at $URL"
  echo "No supported browser launcher was found."
  read -r -p "Press Enter to stop the server..."
}

launch_browser
