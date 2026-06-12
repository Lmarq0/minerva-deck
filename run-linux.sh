#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"
export PATH="$PWD/bin:$PWD/vendor/aria2/usr/bin:$PATH"
if [ -d "$PWD/vendor/aria2/usr/lib" ]; then
  export LD_LIBRARY_PATH="$PWD/vendor/aria2/usr/lib:${LD_LIBRARY_PATH:-}"
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

open_url() {
  local url="http://${HOST}:$1"
  echo "Opening $url"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  fi
}

for candidate in $(seq "$PORT" "$((PORT + 20))"); do
  if status_ok "$candidate"; then
    echo "MiNERVA Deck is already running on port $candidate."
    open_url "$candidate"
    exit 0
  fi
  if port_free "$candidate"; then
    PORT="$candidate"
    break
  fi
done

"$PYTHON_BIN" minerva_deck.py --host "$HOST" --port "$PORT" --no-browser &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 80); do
  if status_ok "$PORT"; then
    open_url "$PORT"
    wait "$SERVER_PID"
    exit $?
  fi
  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    wait "$SERVER_PID"
    exit $?
  fi
  sleep 0.25
done

echo "Server did not become ready on port $PORT."
exit 1
