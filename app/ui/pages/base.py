from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QLabel, QTableWidget, QVBoxLayout, QWidget

from app.ui.i18n.manager import I18n


class Page(QWidget):
    """Common shape of a full-width screen: title, optional intro line, then content."""

    title_key = ""
    intro_key: str | None = None

    def __init__(self, i18n: I18n, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self.guard = lambda perm, action_name: True  # the main window replaces this with the real gate
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(24, 18, 24, 18)
        self.layout_.setSpacing(10)
        self._title = QLabel()
        self._title.setObjectName("PageTitle")
        self.layout_.addWidget(self._title)
        self._intro = QLabel()
        self._intro.setWordWrap(True)
        self._intro.setObjectName("StatusNote")
        self._intro.setVisible(self.intro_key is not None)
        self.layout_.addWidget(self._intro)
        self.note = QLabel()  # one-line feedback ("Saved.", errors)
        self.note.setObjectName("StatusNote")

    def retranslate(self) -> None:
        self._title.setText(self.i18n.tr(self.title_key))
        if self.intro_key:
            self._intro.setText(self.i18n.tr(self.intro_key))

    def refresh(self) -> None:
        """Reload data from the services."""

    def handle_action(self, action_id: str) -> None:
        """A ribbon action that targets this page (permission already checked)."""

    def say(self, text: str, error: bool = False) -> None:
        self.note.setObjectName("ErrorLabel" if error else "StatusNote")
        self.note.style().unpolish(self.note)
        self.note.style().polish(self.note)
        self.note.setText(text)

    @staticmethod
    def make_table(columns: int, selectable: bool = True) -> QTableWidget:
        table = QTableWidget(0, columns)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection if selectable else QAbstractItemView.SelectionMode.NoSelection
        )
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        return table
