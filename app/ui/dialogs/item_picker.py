from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout

from app.domain.item import Item
from app.services.container import Services
from app.ui.i18n.manager import I18n


class ItemPickerDialog(QDialog):
    """Find one item by typing a name or code, or by scanning a barcode (the scanner types the
    code and presses Enter, so an exact code match is chosen immediately)."""

    def __init__(self, i18n: I18n, services: Services, parent=None, initial_text: str = "") -> None:
        super().__init__(parent)
        self.i18n = i18n
        self._services = services
        self.chosen: Item | None = None
        self._results: list[Item] = []
        tr = i18n.tr
        self.setWindowTitle(tr("picker.title"))
        self.setMinimumSize(460, 420)

        layout = QVBoxLayout(self)
        self._search = QLineEdit()
        self._search.setPlaceholderText(tr("picker.search"))
        self._search.textChanged.connect(self._refresh)
        self._search.returnPressed.connect(self._on_enter)
        layout.addWidget(self._search)
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _i: self._choose_current())
        layout.addWidget(self._list, 1)
        self._none = QLabel(tr("picker.none"))
        self._none.setObjectName("StatusNote")
        layout.addWidget(self._none)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton(tr("dialog.cancel"))
        cancel.clicked.connect(self.reject)
        ok = QPushButton(tr("prompt.ok"))
        ok.setObjectName("PrimaryButton")
        ok.clicked.connect(self._choose_current)
        row.addWidget(cancel)
        row.addWidget(ok)
        layout.addLayout(row)
        self._search.setText(initial_text)
        self._refresh()
        self._search.setFocus()

    def _refresh(self) -> None:
        text = self._search.text()
        self._results = self._services.items.search(text, limit=100) if text.strip() else []
        self._list.clear()
        for item in self._results:
            label = f"{item.short_code}   {item.display_name(self.i18n.lang)}"
            entry = QListWidgetItem(label)
            entry.setData(Qt.ItemDataRole.UserRole, item.id)
            self._list.addItem(entry)
        if self._results:
            self._list.setCurrentRow(0)
        self._none.setVisible(bool(text.strip()) and not self._results)

    def _on_enter(self) -> None:
        exact = self._services.items.find_by_code(self._search.text())
        if exact is not None and exact.is_active:
            self.chosen = exact
            self.accept()
        else:
            self._choose_current()

    def _choose_current(self) -> None:
        row = self._list.currentRow()
        if 0 <= row < len(self._results):
            self.chosen = self._results[row]
            self.accept()
