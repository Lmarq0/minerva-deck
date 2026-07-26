"""Map MiNERVA archive paths into EmuDeck system folders."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .utils import normalize_minerva_path, normalized_match_text


EMUDECK_ROUTE_RULES: List[Tuple[str, List[str], str]] = [
    ("Nintendo Wii U", ["nintendo", "wii u"], "wiiu/roms"),
    ("Nintendo Wii", ["nintendo", "wii"], "wii"),
    ("Nintendo GameCube", ["nintendo", "gamecube"], "gc"),
    ("Nintendo Switch", ["nintendo", "switch"], "switch"),
    ("Nintendo 3DS", ["nintendo", "3ds"], "n3ds"),
    ("Nintendo DSi", ["nintendo", "dsi"], "nds"),
    ("Nintendo DS", ["nintendo", "ds"], "nds"),
    ("Nintendo 64DD", ["nintendo", "64dd"], "n64dd"),
    ("Nintendo 64", ["nintendo", "64"], "n64"),
    ("Nintendo Game Boy Advance", ["nintendo", "game boy advance"], "gba"),
    ("Nintendo Game Boy Color", ["nintendo", "game boy color"], "gbc"),
    ("Nintendo Game Boy", ["nintendo", "game boy"], "gb"),
    ("Nintendo Virtual Boy", ["nintendo", "virtual boy"], "virtualboy"),
    ("Nintendo Pokemon Mini", ["nintendo", "pokemon mini"], "pokemini"),
    ("Nintendo Satellaview", ["nintendo", "satellaview"], "satellaview"),
    ("Nintendo Sufami Turbo", ["nintendo", "sufami"], "sufami"),
    ("Nintendo Super Famicom", ["nintendo", "super famicom"], "sfc"),
    ("Nintendo Super Nintendo", ["nintendo", "super nintendo"], "snes"),
    ("Nintendo SNES", ["nintendo", "snes"], "snes"),
    ("Nintendo Famicom Disk System", ["nintendo", "famicom disk"], "fds"),
    ("Nintendo Famicom", ["nintendo", "famicom"], "famicom"),
    ("Nintendo NES", ["nintendo", "entertainment system"], "nes"),
    ("Nintendo NES", ["nintendo", "nes"], "nes"),
    ("Nintendo Game and Watch", ["nintendo", "game and watch"], "gameandwatch"),
    ("Sega NAOMI 2", ["sega", "naomi 2"], "naomi2"),
    ("Sega NAOMI GD-ROM", ["sega", "naomi gd"], "naomigd"),
    ("Sega NAOMI", ["sega", "naomi"], "naomi"),
    ("Sega Atomiswave", ["atomiswave"], "atomiswave"),
    ("Sega Model 2", ["sega", "model 2"], "model2"),
    ("Sega Model 3", ["sega", "model 3"], "model3"),
    ("Sega Dreamcast", ["sega", "dreamcast"], "dreamcast"),
    ("Sega Saturn", ["sega", "saturn"], "saturn"),
    ("Sega CD", ["sega", "mega cd"], "megacd"),
    ("Sega CD", ["sega", "sega cd"], "segacd"),
    ("Sega 32X", ["sega", "32x"], "sega32x"),
    ("Sega Game Gear", ["sega", "game gear"], "gamegear"),
    ("Sega Genesis", ["sega", "genesis"], "genesis"),
    ("Sega Mega Drive", ["sega", "mega drive"], "megadrive"),
    ("Sega Master System", ["sega", "master system"], "mastersystem"),
    ("Sega SG-1000", ["sega", "sg 1000"], "sg-1000"),
    ("Sony PlayStation Portable", ["sony", "playstation portable"], "psp"),
    ("Sony PSP", ["sony", "psp"], "psp"),
    ("Sony PlayStation Vita", ["sony", "playstation vita"], "psvita/ux0"),
    ("Sony PlayStation 4", ["sony", "playstation 4"], "ps4"),
    ("Sony PlayStation 3", ["sony", "playstation 3"], "ps3"),
    ("Sony PlayStation 2", ["sony", "playstation 2"], "ps2"),
    ("Sony PlayStation", ["sony", "playstation"], "psx"),
    ("Microsoft Xbox 360 Live Arcade", ["xbox 360", "live arcade"], "xbox360/roms/xbla"),
    ("Microsoft Xbox 360", ["microsoft", "xbox 360"], "xbox360/roms"),
    ("Microsoft Xbox", ["microsoft", "xbox"], "xbox"),
    ("Microsoft MSX Turbo R", ["microsoft", "msx turbo"], "msxturbor"),
    ("Microsoft MSX2", ["microsoft", "msx2"], "msx2"),
    ("Microsoft MSX1", ["microsoft", "msx1"], "msx1"),
    ("Microsoft MSX", ["microsoft", "msx"], "msx"),
    ("NEC PC Engine CD", ["nec", "pc engine cd"], "pcenginecd"),
    ("NEC TurboGrafx-CD", ["nec", "turbografx cd"], "tg-cd"),
    ("NEC SuperGrafx", ["nec", "supergrafx"], "supergrafx"),
    ("NEC PC-9800", ["nec", "pc 9800"], "pc98"),
    ("NEC PC-9800", ["nec", "pc 98"], "pc98"),
    ("NEC PC-8800", ["nec", "pc 8800"], "pc88"),
    ("NEC PC-FX", ["nec", "pc fx"], "pcfx"),
    ("NEC PC Engine", ["nec", "pc engine"], "pcengine"),
    ("NEC TurboGrafx-16", ["nec", "turbografx 16"], "tg16"),
    ("SNK Neo Geo Pocket Color", ["snk", "neo geo pocket color"], "ngpc"),
    ("SNK Neo Geo Pocket", ["snk", "neo geo pocket"], "ngp"),
    ("SNK Neo Geo CD", ["snk", "neo geo cd"], "neogeocd"),
    ("SNK Neo Geo MVS", ["snk", "neo geo mvs"], "fbneo"),
    ("SNK Neo Geo", ["snk", "neo geo"], "neogeo"),
    ("Bandai WonderSwan Color", ["bandai", "wonderswan color"], "wonderswancolor"),
    ("Bandai WonderSwan", ["bandai", "wonderswan"], "wonderswan"),
    ("Bandai SuFami Turbo", ["bandai", "sufami"], "sufami"),
    ("Atari Jaguar CD", ["atari", "jaguar cd"], "atarijaguarcd"),
    ("Atari Jaguar", ["atari", "jaguar"], "atarijaguar"),
    ("Atari Lynx", ["atari", "lynx"], "atarilynx"),
    ("Atari 7800", ["atari", "7800"], "atari7800"),
    ("Atari 5200", ["atari", "5200"], "atari5200"),
    ("Atari 2600", ["atari", "2600"], "atari2600"),
    ("Atari 800", ["atari", "800"], "atari800"),
    ("Atari ST", ["atari", "st"], "atarist"),
    ("Panasonic 3DO", ["panasonic", "3do"], "3do"),
    ("Philips CD-i", ["philips", "cd i"], "cdimono1"),
    ("Philips Videopac", ["philips", "videopac"], "videopac"),
    ("Magnavox Odyssey2", ["magnavox", "odyssey2"], "odyssey2"),
    ("Mattel Intellivision", ["mattel", "intellivision"], "intellivision"),
    ("Commodore Amiga CD32", ["commodore", "amiga cd32"], "amigacd32"),
    ("Commodore Amiga 1200", ["commodore", "amiga 1200"], "amiga1200"),
    ("Commodore Amiga 600", ["commodore", "amiga 600"], "amiga600"),
    ("Commodore Amiga", ["commodore", "amiga"], "amiga"),
    ("Commodore 64", ["commodore", "64"], "c64"),
    ("Commodore 16", ["commodore", "16"], "c16"),
    ("Commodore VIC-20", ["commodore", "vic 20"], "vic20"),
    ("Amstrad CPC", ["amstrad", "cpc"], "amstradcpc"),
    ("Amstrad GX4000", ["amstrad", "gx4000"], "gx4000"),
    ("Apple IIgs", ["apple", "iigs"], "apple2gs"),
    ("Apple IIgs", ["apple", "ii gs"], "apple2gs"),
    ("Apple II", ["apple", "ii"], "apple2"),
    ("Apple Macintosh", ["apple", "macintosh"], "macintosh"),
    ("Fujitsu FM Towns", ["fujitsu", "fm towns"], "fmtowns"),
    ("Sharp X68000", ["sharp", "x68000"], "x68000"),
    ("Sharp X1", ["sharp", "x1"], "x1"),
    ("Sinclair ZX Spectrum", ["sinclair", "zx spectrum"], "zxspectrum"),
    ("Sinclair ZX81", ["sinclair", "zx81"], "zx81"),
    ("ColecoVision", ["coleco", "colecovision"], "colecovision"),
    ("Vectrex", ["vectrex"], "vectrex"),
    ("Watara Supervision", ["watara", "supervision"], "supervision"),
    ("Tiger Game.com", ["tiger", "game com"], "gamecom"),
    ("VTech V.Smile", ["vtech", "v smile"], "vsmile"),
    ("Doom", ["doom"], "doom"),
    ("Pico-8", ["pico 8"], "pico8"),
    ("ScummVM", ["scummvm"], "scummvm"),
    ("EasyRPG", ["easyrpg"], "easyrpg"),
    ("DOS", ["dos"], "dos"),
    ("MAME", ["mame"], "arcade"),
    ("FinalBurn Neo", ["finalburn neo"], "fbneo"),
    ("Final Burn Neo", ["final burn neo"], "fbneo"),
]


def emudeck_route_for_path(full_path: str) -> Optional[Dict[str, str]]:
    normalized = normalize_minerva_path(full_path)
    parts = normalized.split("/")
    searchable = normalized_match_text(" ".join(parts[:-1] if len(parts) > 1 else parts))
    for label, tokens, folder in EMUDECK_ROUTE_RULES:
        if all(normalized_match_text(token) in searchable for token in tokens):
            return {"system": label, "folder": folder, "path": normalized}
    return None


def validate_emudeck_subfolder(value: str) -> str:
    raw = (value or "").strip().replace("\\", "/")
    if re.match(r"^[A-Za-z]:", raw) or raw.startswith("/"):
        raise RuntimeError("EmuDeck system folder must be relative to the ROMs root")
    cleaned = raw.strip("/")
    if not cleaned:
        raise RuntimeError("No EmuDeck system folder was detected")
    parts = [part for part in cleaned.split("/") if part]
    if any(part in (".", "..") for part in parts):
        raise RuntimeError("EmuDeck system folder cannot contain '.' or '..'")
    if any(re.search(r'[<>:"|?*\x00-\x1f]', part) for part in parts):
        raise RuntimeError("EmuDeck system folder contains invalid path characters")
    return "/".join(parts)


def emudeck_destination(
    roms_root: Path,
    full_path: str,
    override: str = "",
    allow_root_fallback: bool = False,
) -> Tuple[Path, str, str]:
    if override.strip():
        folder = validate_emudeck_subfolder(override)
        system = "Manual override"
    else:
        route = emudeck_route_for_path(full_path)
        if not route:
            if allow_root_fallback:
                return roms_root.expanduser(), ".", "ROMs root fallback"
            raise RuntimeError("Could not map this MiNERVA system to an EmuDeck ROM folder")
        folder = validate_emudeck_subfolder(route["folder"])
        system = route["system"]
    target = roms_root.expanduser()
    for part in folder.split("/"):
        target = target / part
    return target, folder, system
