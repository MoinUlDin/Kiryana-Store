from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
)

from app.domain.user import User
from app.services.named_list_service import NamedListService
from app.ui.errors import error_text
from app.ui.i18n.manager import I18n


class ManageListDialog(QDialog):
    """Add, rename and delete categories or brands."""

    def __init__(self, i18n: I18n, service: NamedListService, user: User, title_key: str, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self._service = service
        self._user = user
        tr = i18n.tr
        self.setWindowTitle(tr(title_key))
        self.setMinimumSize(460, 420)

        layout = QVBoxLayout(self)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_select)
        layout.addWidget(self._list, 1)
        form = QFormLayout()
        self._name_en = QLineEdit()
        self._name_ur = QLineEdit()
        form.addRow(tr("lists.name_en"), self._name_en)
        form.addRow(tr("lists.name_ur"), self._name_ur)
        layout.addLayout(form)
        self._error = QLabel()
        self._error.setObjectName("ErrorLabel")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._error)

        row = QHBoxLayout()
        self._add = QPushButton(tr("lists.add"))
        self._add.setObjectName("PrimaryButton")
        self._rename = QPushButton(tr("lists.rename"))
        self._delete = QPushButton(tr("lists.delete"))
        close = QPushButton(tr("lists.close"))
        self._add.clicked.connect(self._on_add)
        self._rename.clicked.connect(self._on_rename)
        self._delete.clicked.connect(self._on_delete)
        close.clicked.connect(self.accept)
        for button in (self._add, self._rename, self._delete):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
        self._entries = []
        self._reload()

    def _reload(self, select_id: int | None = None) -> None:
        self._entries = self._service.list()
        self._list.blockSignals(True)
        self._list.clear()
        for entry in self._entries:
            item = QListWidgetItem(entry.display(self.i18n.lang))
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self._list.addItem(item)
            if entry.id == select_id:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        self._on_select()

    def _selected(self):
        row = self._list.currentRow()
        return self._entries[row] if 0 <= row < len(self._entries) else None

    def _on_select(self, _row: int = -1) -> None:
        entry = self._selected()
        self._name_en.setText(entry.name_en if entry else "")
        self._name_ur.setText(entry.name_ur or "" if entry else "")
        self._rename.setEnabled(entry is not None)
        self._delete.setEnabled(entry is not None)

    def _run(self, action) -> None:
        try:
            result = action()
        except (ValueError, PermissionError) as exc:
            self._error.setText(error_text(self.i18n, exc))
            self._error.show()
            return
        self._error.hide()
        self._reload(result)

    def _on_add(self) -> None:
        def go():
            entry = self._service.add(self._user, self._name_en.text(), self._name_ur.text())
            return entry.id
        self._run(go)

    def _on_rename(self) -> None:
        entry = self._selected()
        if entry:
            def go():
                self._service.rename(self._user, entry.id, self._name_en.text(), self._name_ur.text())
                return entry.id
            self._run(go)

    def _on_delete(self) -> None:
        entry = self._selected()
        if entry:
            def go():
                self._service.delete(self._user, entry.id)
                return None
            self._run(go)
