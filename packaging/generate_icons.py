"""Render the repository SVG icon into the PNG build asset."""

from pathlib import Path

from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


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
    app = QGuiApplication([])
    render_png(ROOT / "assets" / "minerva-deck.png", 512)
    app.quit()


if __name__ == "__main__":
    main()
