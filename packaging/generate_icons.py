"""Render the repository SVG icon into PNG and ICO build assets."""

import argparse
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QImage, QPainter


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "assets" / "minerva-deck.svg"


def render_png(target: Path, size: int) -> None:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    QSvgRenderer(str(SOURCE)).render(painter)
    painter.end()
    if not image.save(str(target), "PNG"):
        raise RuntimeError(f"Could not create {target}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--png-only", action="store_true")
    args = parser.parse_args()
    app = QGuiApplication([])
    png = ROOT / "assets" / "minerva-deck.png"
    ico = ROOT / "assets" / "minerva-deck.ico"
    render_png(png, 512)
    if not args.png_only:
        icon = QIcon(str(SOURCE))
        if not icon.pixmap(QSize(256, 256)).save(str(ico), "ICO"):
            raise RuntimeError("Qt could not create the Windows ICO asset")
    app.quit()


if __name__ == "__main__":
    main()
