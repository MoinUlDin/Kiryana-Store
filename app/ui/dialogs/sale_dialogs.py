from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidgetItem, QVBoxLayout,
)

from app.domain.money import Money
from app.domain.parsing import parse_money
from app.domain.quantity import Quantity
from app.security.passwords import ValidationError
from app.services.container import Services
from app.domain.user import User
from app.ui.dialogs.confirm import confirm
from app.ui.dialogs.user_dialogs import _FormDialog
from app.ui.errors import error_text
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page
from app.ui.pages.users_page import local_time
from app.ui.quantity_edit import QuantityEdit


class MiscItemDialog(_FormDialog):
    """A one-off item that is not in the catalog. After accept(): .name, .price, .qty."""

    def __init__(self, i18n: I18n, parent=None) -> None:
        super().__init__(i18n, i18n.tr("misc.title"), parent)
        tr = i18n.tr
        self.name = ""
        self.price = Money(0)
        self.qty = Quantity(1000)
        self._name = QLineEdit()
        self._price = QLineEdit()
        self._qty = QLineEdit("1")
        self.form.addRow(tr("misc.name"), self._name)
        self.form.addRow(tr("misc.price"), self._price)
        self.form.addRow(tr("misc.qty"), self._qty)
        self._name.setFocus()

    def _save(self) -> None:
        from app.domain.parsing import parse_quantity
        try:
            name = self._name.text().strip()
            if not name:
                raise ValidationError("error.name_required")
            price = parse_money(self._price.text())
            qty = parse_quantity(self._qty.text())
            if qty.milli <= 0 or not qty.is_whole:
                raise ValidationError("error.quantity_invalid")
        except ValidationError as exc:
            self.show_error(self.i18n.tr(exc.code, **exc.params))
            return
        self.name, self.price, self.qty = name, price, qty
        self.accept()


class QuickFixDialog(_FormDialog):
    """The system says 0 but the item is on the shelf: enter the real count.
    submit(counted, note) -> None on success or an error text."""

    def __init__(self, i18n: I18n, name: str, unit: str, current: Quantity,
                 submit: Callable[[Quantity, str | None], str | None], parent=None) -> None:
        tr = i18n.tr
        super().__init__(i18n, tr("fix.title"), parent)
        self._submit = submit
        prompt = QLabel(tr("fix.prompt", name=name, qty=current.format(), unit=tr(f"unit.{unit}")))
        prompt.setWordWrap(True)
        self._qty = QuantityEdit(i18n, unit)
        self._note = QLineEdit()
        self.form.addRow(prompt)
        self.form.addRow(tr("adjust.qty_counted"), self._qty)
        self.form.addRow(tr("adjust.note"), self._note)
        self._qty.edit.setFocus()

    def _save(self) -> None:
        try:
            counted = self._qty.quantity(allow_empty=False)
        except ValidationError as exc:
            self.show_error(self.i18n.tr(exc.code, **exc.params))
            return
        error = self._submit(counted, self._note.text().strip() or None)
        if error:
            self.show_error(error)
        else:
            self.accept()


class StockShortDialog(QDialog):
    """Not enough stock. The only way forward is to fix the count (if allowed) or change the bill."""

    def __init__(self, i18n: I18n, name: str, available: str, needed: str, parent=None) -> None:
        super().__init__(parent)
        tr = i18n.tr
        self.fix_requested = False
        self.setWindowTitle(tr("short.title"))
        self.setModal(True)
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        text = QLabel(tr("short.text", name=name, available=available, needed=needed))
        text.setWordWrap(True)
        layout.addWidget(text)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton(tr("dialog.cancel"))
        cancel.clicked.connect(self.reject)
        fix = QPushButton(tr("short.fix"))
        fix.setObjectName("PrimaryButton")
        fix.clicked.connect(self._fix)
        row.addWidget(cancel)
        row.addWidget(fix)
        layout.addLayout(row)

    def _fix(self) -> None:
        self.fix_requested = True
        self.accept()


class HeldBillsDialog(QDialog):
    """Pick a held bill to resume, or discard one. After accept(): .chosen_id."""

    def __init__(self, i18n: I18n, services: Services, user: User, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self._services = services
        self._user = user
        self.chosen_id: int | None = None
        self._held: list[dict] = []
        tr = i18n.tr
        self.setWindowTitle(tr("held.title"))
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        self._table = Page.make_table(4)
        self._table.setHorizontalHeaderLabels([tr("held.col.label"), tr("held.col.time"), tr("held.col.by"),
                                               tr("held.col.lines")])
        self._table.doubleClicked.connect(lambda _i: self._resume())
        layout.addWidget(self._table, 1)
        self._none = QLabel(tr("held.none"))
        self._none.setObjectName("StatusNote")
        layout.addWidget(self._none)
        row = QHBoxLayout()
        self._discard = QPushButton(tr("held.discard"))
        self._discard.clicked.connect(self._on_discard)
        close = QPushButton(tr("lists.close"))
        close.clicked.connect(self.reject)
        self._resume_button = QPushButton(tr("held.resume"))
        self._resume_button.setObjectName("PrimaryButton")
        self._resume_button.setDefault(True)
        self._resume_button.clicked.connect(self._resume)
        row.addWidget(self._discard)
        row.addStretch(1)
        row.addWidget(close)
        row.addWidget(self._resume_button)
        layout.addLayout(row)
        self._reload()

    def _reload(self) -> None:
        self._held = self._services.held.list()
        self._table.setRowCount(len(self._held))
        for r, h in enumerate(self._held):
            values = [h["label"], local_time(h["created_at"], ""), h["cashier_name"] or "-", str(h["line_count"])]
            for c, text in enumerate(values):
                self._table.setItem(r, c, QTableWidgetItem(text))
        self._table.resizeColumnsToContents()
        if self._held:
            self._table.selectRow(0)
        self._none.setVisible(not self._held)
        self._resume_button.setEnabled(bool(self._held))
        self._discard.setEnabled(bool(self._held))

    def _selected_id(self) -> int | None:
        row = self._table.currentRow()
        return self._held[row]["id"] if 0 <= row < len(self._held) else None

    def _resume(self) -> None:
        held_id = self._selected_id()
        if held_id is not None:
            self.chosen_id = held_id
            self.accept()

    def _on_discard(self) -> None:
        held_id = self._selected_id()
        if held_id is None or not confirm(self.i18n, self, self.i18n.tr("held.title"), self.i18n.tr("held.discard_confirm")):
            return
        try:
            self._services.held.discard(self._user, held_id)
        except (ValueError, PermissionError) as exc:
            self._none.setText(error_text(self.i18n, exc))
            self._none.show()
            return
        self._reload()
