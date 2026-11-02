from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QToolButton, QVBoxLayout, QWidget

from app.ui.ribbon.button import RibbonButton
from app.ui.ribbon.layout_logic import COLLAPSED, COMPACT, FULL

SMALL_PER_COLUMN = 3


class RibbonGroup(QFrame):
    """A titled cluster of buttons. It can show itself in three modes (FULL, COMPACT,
    COLLAPSED) so the ribbon can squeeze into narrow windows."""

    activated = pyqtSignal()  # any button in the group was clicked

    def __init__(self, key: str, title_key: str, priority: int, parent=None) -> None:
        super().__init__(parent)
        self.key = key
        self.title_key = title_key
        self.priority = priority
        self.mode = FULL
        self.widths = [0, 0, 0]
        self._items: list[tuple[QAction, bool]] = []
        self._buttons: list[RibbonButton] = []
        self._collapsed_button: QToolButton | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 2)
        outer.setSpacing(2)
        self._body = QHBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(2)
        outer.addLayout(self._body, 1)
        self._title = QLabel()
        self._title.setObjectName("RibbonGroupTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._title)

    # ---- building -----------------------------------------------------
    def add_action(self, action: QAction, large: bool) -> None:
        button = RibbonButton(action, large, self)
        button.clicked.connect(self.activated)
        button.hide()
        self._items.append((action, large))
        self._buttons.append(button)

    def retranslate(self, tr: Callable[[str], str]) -> None:
        self._title.setText(tr(self.title_key))
        if self._collapsed_button is not None:
            self._collapsed_button.setText(tr(self.title_key))
        self.measure()

    # ---- modes --------------------------------------------------------
    def measure(self) -> None:
        """Record the width of each mode, then restore the current mode."""
        current = self.mode
        # Widths depend on the stylesheet and font, so make sure everything is styled first.
        self.ensurePolished()
        for child in [*self._buttons, self._title]:
            child.ensurePolished()
        for mode in (FULL, COMPACT, COLLAPSED):
            self.set_mode(mode, force=True)
            self.widths[mode] = self.sizeHint().width()
        self.set_mode(current, force=True)

    def set_mode(self, mode: int, force: bool = False) -> None:
        if mode == self.mode and not force:
            return
        self.mode = mode
        self._rebuild()

    def _ensure_collapsed_button(self) -> QToolButton:
        if self._collapsed_button is None:
            button = QToolButton(self)
            button.setObjectName("RibbonButton")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            menu = QMenu(button)
            for action, _large in self._items:
                menu.addAction(action)
            menu.triggered.connect(lambda _a: self.activated.emit())
            button.setMenu(menu)
            button.setText(self._title.text())
            if self._items:
                button.setIcon(self._items[0][0].icon())
            button.setIconSize(QSize(32, 32))
            button.hide()
            self._collapsed_button = button
        return self._collapsed_button

    def _rebuild(self) -> None:
        collapsed = self._ensure_collapsed_button() if self._items else None
        # Detach every widget we own so clearing the layout cannot delete them.
        for widget in [*self._buttons, *([collapsed] if collapsed else [])]:
            widget.setParent(self)
            widget.hide()
        owned = {*self._buttons, *([collapsed] if collapsed else [])}
        while self._body.count():
            item = self._body.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            if widget in owned:
                widget.hide()  # keep it: we re-add it below if this mode needs it
            else:
                widget.deleteLater()  # a column container from the previous mode

        if self.mode == COLLAPSED:
            if collapsed is not None:
                self._body.addWidget(collapsed)
                collapsed.setVisible(True)
            return

        columns: list[QWidget] = []
        pending: list[RibbonButton] = []

        def flush_small() -> None:
            if pending:
                columns.append(self._make_column(list(pending), stretch=True))
                pending.clear()

        for button, (_action, large) in zip(self._buttons, self._items):
            if self.mode == FULL and large:
                flush_small()
                button.set_large(True)
                columns.append(self._make_column([button], stretch=False))
            else:
                button.set_large(False)
                pending.append(button)
                if len(pending) == SMALL_PER_COLUMN:
                    flush_small()
        flush_small()
        for column in columns:
            self._body.addWidget(column)

    def _make_column(self, buttons: list[RibbonButton], stretch: bool) -> QWidget:
        column = QWidget(self)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        for button in buttons:
            layout.addWidget(button)
            button.setVisible(True)
        if stretch:
            layout.addStretch(1)
        return column
