$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$port = if ($env:PORT) { $env:PORT } else { "8765" }

if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 .\minerva_deck.py --host 127.0.0.1 --port $port
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    python3 .\minerva_deck.py --host 127.0.0.1 --port $port
} else {
    python .\minerva_deck.py --host 127.0.0.1 --port $port
}
