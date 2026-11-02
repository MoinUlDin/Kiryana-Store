from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QToolButton


class RibbonButton(QToolButton):
    """Large (icon above text) or small (icon beside text) button bound to a QAction."""

    def __init__(self, action: QAction, large: bool, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RibbonButton")
        self.setDefaultAction(action)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.set_large(large)

    @property
    def large(self) -> bool:
        return self._large

    def set_large(self, large: bool) -> None:
        self._large = large
        if large:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            self.setIconSize(QSize(32, 32))
        else:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.setIconSize(QSize(16, 16))
