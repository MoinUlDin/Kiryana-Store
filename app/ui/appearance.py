from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from app.ui import theme
from app.ui.i18n.manager import I18n


def apply(app: QApplication, i18n: I18n) -> None:
    """Layout direction, font and stylesheet for the current language. Must run BEFORE any
    widget re-translates, because font and padding change how wide the widgets are."""
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if i18n.is_rtl else Qt.LayoutDirection.LeftToRight)
    theme.apply(app, i18n.lang)
