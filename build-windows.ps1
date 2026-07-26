$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Assert-NativeCommand([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

$venv = Join-Path $PSScriptRoot ".venv-build"
$vcpkg = Join-Path $PSScriptRoot "build\vcpkg"
$installed = Join-Path $PSScriptRoot "build\vcpkg_installed"
$native = Join-Path $PSScriptRoot "build\native"
$licenses = Join-Path $PSScriptRoot "build\licenses"
$version = (Select-String -Path "pyproject.toml" -Pattern '^version = "(.+)"$').Matches.Groups[1].Value
$artifact = "MiNERVA-Deck-$version-windows-x64.exe"

if (-not (Test-Path -LiteralPath $venv)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.12 -m venv $venv
    } else {
        python -m venv $venv
    }
}
$buildPython = Join-Path $venv "Scripts\python.exe"
& $buildPython -m pip install --upgrade pip
Assert-NativeCommand "pip upgrade"
& $buildPython -m pip install -e ".[build]"
Assert-NativeCommand "dependency installation"
& $buildPython packaging\generate_icons.py
Assert-NativeCommand "icon generation"

if (-not (Test-Path -LiteralPath (Join-Path $vcpkg ".git"))) {
    git clone https://github.com/microsoft/vcpkg.git $vcpkg
}
git -C $vcpkg fetch --depth 1 origin 40f3c709db80acf154ac4b17a1f83c564ebd022e
Assert-NativeCommand "vcpkg baseline fetch"
git -C $vcpkg checkout --detach 40f3c709db80acf154ac4b17a1f83c564ebd022e
Assert-NativeCommand "vcpkg baseline checkout"
& (Join-Path $vcpkg "bootstrap-vcpkg.bat") -disableMetrics
Assert-NativeCommand "vcpkg bootstrap"
& (Join-Path $vcpkg "vcpkg.exe") install `
    --x-manifest-root=packaging `
    --x-install-root=$installed `
    --triplet=x64-windows
Assert-NativeCommand "native dependency build"

New-Item -ItemType Directory -Path $native -Force | Out-Null
Copy-Item -Path (Join-Path $installed "x64-windows\bin\*.dll") -Destination $native -Force
$archiveDll = Get-ChildItem -LiteralPath $native -Filter "archive.dll" | Select-Object -First 1
if (-not $archiveDll) { throw "vcpkg did not produce archive.dll" }
$env:LIBARCHIVE = $archiveDll.FullName
& $buildPython packaging\collect_licenses.py --output $licenses --vcpkg-root $installed
Assert-NativeCommand "license collection"

& $buildPython -m unittest discover -s tests -v
Assert-NativeCommand "test suite"
node --check public\static\app.js
Assert-NativeCommand "JavaScript syntax check"

$includeLicenses = "--include-data-dir=$licenses=licenses"
& $buildPython -m nuitka `
    --mode=onefile `
    --assume-yes-for-downloads `
    --enable-plugin=pyside6 `
    --user-package-configuration-file=packaging\nuitka-package.config.yml `
    --windows-console-mode=disable `
    --output-dir=dist `
    "--output-filename=$artifact" `
    --windows-icon-from-ico=packaging\assets\minerva-deck.ico `
    "--windows-product-name=MiNERVA Deck" `
    "--windows-file-description=MiNERVA Deck desktop application" `
    "--windows-company-name=MiNERVA" `
    "--windows-file-version=$version.0" `
    "--windows-product-version=$version.0" `
    --include-data-dir=public=public `
    --include-data-dir=packaging=packaging `
    $includeLicenses `
    minerva_deck.py
Assert-NativeCommand "Nuitka packaging"

& (Join-Path $PSScriptRoot "dist\$artifact") --self-test
Assert-NativeCommand "packaged self-test"
$artifactPath = Join-Path $PSScriptRoot "dist\$artifact"
$artifactHash = Get-FileHash -Algorithm SHA256 $artifactPath
$checksumLine = "$($artifactHash.Hash.ToLowerInvariant())  $artifact`n"
[System.IO.File]::WriteAllText(
    "$artifactPath.sha256",
    $checksumLine,
    [System.Text.Encoding]::ASCII
)
$artifactHash

# Signing hook intentionally disabled until WINDOWS_SIGNING_CERTIFICATE and
# WINDOWS_SIGNING_PASSWORD secrets are configured in the release environment.
