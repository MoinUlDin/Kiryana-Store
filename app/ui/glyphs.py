from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QTextOption

_ICON_FONT = "Segoe MDL2 Assets"  # ships with Windows 10 and 11


def glyph_icon(char: str, size: int = 32, color: str = "#1E4E80") -> QIcon:
    """Draw one icon-font character into a crisp icon (placeholder until we add SVG icons)."""
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(scale)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont(_ICON_FONT)
    font.setPixelSize(int(size * 0.8))
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(QRectF(0, 0, size, size), char, QTextOption(Qt.AlignmentFlag.AlignCenter))
    painter.end()
    return QIcon(pixmap)
