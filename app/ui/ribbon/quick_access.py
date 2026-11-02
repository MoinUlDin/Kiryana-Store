from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget


class QuickAccessBar(QWidget):
    """Thin strip above the tabs: favourite one-click actions on one side, app title on the other."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("QuickAccess")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 2, 6, 2)
        self._layout.setSpacing(2)
        self._title = QLabel()
        self._layout.addStretch(1)
        self._layout.addWidget(self._title)

    def add_action(self, action: QAction) -> None:
        button = QToolButton(self)
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setIconSize(QSize(16, 16))
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._layout.insertWidget(self._layout.count() - 2, button)

    def set_title(self, text: str) -> None:
        self._title.setText(text)
