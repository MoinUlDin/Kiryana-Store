from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QWidget

from app.ui.glyphs import glyph_icon
from app.ui.i18n.manager import I18n
from app.ui.ribbon_spec import ACTIONS, ActionDef


class ActionRegistry(QObject):
    """One QAction per command. Buttons, menus and shortcuts all share it, so a
    permission check or a translation change happens in exactly one place."""

    triggered = pyqtSignal(str)  # emits the action id

    def __init__(self, i18n: I18n, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._i18n = i18n
        self._defs: dict[str, ActionDef] = {}
        self._actions: dict[str, QAction] = {}
        for definition in ACTIONS:
            self._register(definition)
        self.retranslate()

    def _register(self, definition: ActionDef) -> None:
        action = QAction(self)
        action.setIcon(glyph_icon(definition.glyph))
        if definition.shortcut:
            action.setShortcut(QKeySequence(definition.shortcut))
        action.triggered.connect(lambda _checked=False, aid=definition.id: self.triggered.emit(aid))
        self._defs[definition.id] = definition
        self._actions[definition.id] = action

    def get(self, action_id: str) -> QAction:
        return self._actions[action_id]

    def perm_for(self, action_id: str) -> str | None:
        return self._defs[action_id].perm

    def attach(self, widget: QWidget) -> None:
        """Shortcuts only fire if the action belongs to a visible widget; the main window
        owns them all so they work no matter which ribbon tab is showing."""
        for action in self._actions.values():
            widget.addAction(action)

    def retranslate(self) -> None:
        for action_id, action in self._actions.items():
            text = self._i18n.tr(f"act.{action_id}")
            action.setText(text)
            shortcut = self._defs[action_id].shortcut
            tip = f"{text} ({QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.NativeText)})" if shortcut else text
            action.setToolTip(tip)

    def refresh_permissions(self, is_allowed: Callable[[str], bool] | None) -> None:
        """Phase 1 plugs the permission service in here. Until then everything is allowed."""
        for action_id, action in self._actions.items():
            perm = self._defs[action_id].perm
            action.setVisible(True if (perm is None or is_allowed is None) else is_allowed(perm))
