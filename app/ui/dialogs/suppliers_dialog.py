from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
)

from app.domain.user import User
from app.services.supplier_service import Supplier, SupplierService
from app.ui.errors import error_text
from app.ui.i18n.manager import I18n


class SuppliersDialog(QDialog):
    """Add, edit and deactivate suppliers (kept basic in v1; the supplier ledger comes in v2)."""

    def __init__(self, i18n: I18n, service: SupplierService, user: User, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self._service = service
        self._user = user
        tr = i18n.tr
        self.setWindowTitle(tr("suppliers.title"))
        self.setMinimumSize(500, 480)
        layout = QVBoxLayout(self)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_select)
        layout.addWidget(self._list, 1)
        form = QFormLayout()
        self._name = QLineEdit()
        self._phone = QLineEdit()
        self._address = QLineEdit()
        self._note = QLineEdit()
        form.addRow(tr("users.col.name"), self._name)
        form.addRow(tr("supplier.phone"), self._phone)
        form.addRow(tr("supplier.address"), self._address)
        form.addRow(tr("supplier.note"), self._note)
        layout.addLayout(form)
        self._error = QLabel()
        self._error.setObjectName("ErrorLabel")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._error)
        row = QHBoxLayout()
        self._add = QPushButton(tr("lists.add"))
        self._add.setObjectName("PrimaryButton")
        self._save = QPushButton(tr("dialog.save"))
        self._toggle = QPushButton(tr("items.deactivate"))
        close = QPushButton(tr("lists.close"))
        self._add.clicked.connect(self._on_add)
        self._save.clicked.connect(self._on_save)
        self._toggle.clicked.connect(self._on_toggle)
        close.clicked.connect(self.accept)
        for button in (self._add, self._save, self._toggle):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
        self._suppliers: list[Supplier] = []
        self._reload()

    def _reload(self, select_id: int | None = None) -> None:
        self._suppliers = self._service.list(include_inactive=True)
        self._list.blockSignals(True)
        self._list.clear()
        for supplier in self._suppliers:
            suffix = "" if supplier.is_active else "  (" + self.i18n.tr("users.status.disabled") + ")"
            item = QListWidgetItem(supplier.name + suffix)
            self._list.addItem(item)
            if supplier.id == select_id:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        self._on_select()

    def _selected(self) -> Supplier | None:
        row = self._list.currentRow()
        return self._suppliers[row] if 0 <= row < len(self._suppliers) else None

    def _on_select(self, _row: int = -1) -> None:
        s = self._selected()
        self._name.setText(s.name if s else "")
        self._phone.setText(s.phone or "" if s else "")
        self._address.setText(s.address or "" if s else "")
        self._note.setText(s.note or "" if s else "")
        self._save.setEnabled(s is not None)
        self._toggle.setEnabled(s is not None)
        tr = self.i18n.tr
        self._toggle.setText(tr("items.activate") if (s and not s.is_active) else tr("items.deactivate"))

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
        self._run(lambda: self._service.add(self._user, self._name.text(), self._phone.text(),
                                            self._address.text(), self._note.text()).id)

    def _on_save(self) -> None:
        s = self._selected()
        if s:
            self._run(lambda: self._service.update(self._user, s.id, self._name.text(), self._phone.text(),
                                                   self._address.text(), self._note.text()).id)

    def _on_toggle(self) -> None:
        s = self._selected()
        if s:
            def go():
                self._service.set_active(self._user, s.id, not s.is_active)
                return s.id
            self._run(go)
