from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from app.domain.item import Item
from app.domain.quantity import Quantity
from app.security.passwords import ValidationError
from app.services.stock_service import DECREASE_ONLY, Movement
from app.ui.dialogs.user_dialogs import _FormDialog
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page
from app.ui.pages.users_page import local_time
from app.ui.quantity_edit import QuantityEdit

KINDS = ("damage", "loss", "expiry", "count")


class AdjustDialog(_FormDialog):
    """submit(reason_kind, quantity, note) -> None on success, or an error message."""

    def __init__(self, i18n: I18n, item: Item, submit: Callable[[str, Quantity, str | None], str | None], parent=None):
        tr = i18n.tr
        super().__init__(i18n, f"{tr('adjust.title')}: {item.display_name(i18n.lang)}", parent)
        self._submit = submit
        self._reason = QComboBox()
        for kind in KINDS:
            self._reason.addItem(tr(f"adjust.{kind}"), kind)
        self._qty = QuantityEdit(i18n, item.unit)
        self._qty_label = QLabel()
        self._note = QLineEdit()
        current = QLabel(tr("adjust.current", qty=item.stock.format(), unit=tr(f"unit.{item.unit}")))
        self.form.addRow(current)
        self.form.addRow(tr("adjust.reason"), self._reason)
        self.form.addRow(self._qty_label, self._qty)
        self.form.addRow(tr("adjust.note"), self._note)
        self._reason.currentIndexChanged.connect(self._update_label)
        self._update_label()
        self._qty.edit.setFocus()

    def _update_label(self) -> None:
        key = "adjust.qty_remove" if self._reason.currentData() in DECREASE_ONLY else "adjust.qty_counted"
        self._qty_label.setText(self.i18n.tr(key))

    def _save(self) -> None:
        try:
            qty = self._qty.quantity(allow_empty=self._reason.currentData() == "count")
        except ValidationError as exc:
            self.show_error(self.i18n.tr(exc.code, **exc.params))
            return
        error = self._submit(self._reason.currentData(), qty, self._note.text().strip() or None)
        if error:
            self.show_error(error)
        else:
            self.accept()


class HistoryDialog(QDialog):
    def __init__(self, i18n: I18n, item: Item, movements: list[Movement], parent=None) -> None:
        super().__init__(parent)
        tr = i18n.tr
        self.setWindowTitle(f"{tr('history.title')}: {item.display_name(i18n.lang)}")
        self.resize(720, 420)
        layout = QVBoxLayout(self)
        table = Page.make_table(5, selectable=False)
        table.setHorizontalHeaderLabels([tr("audit.col.time"), tr("history.col.type"), tr("history.col.qty"),
                                         tr("audit.col.user"), tr("history.col.note")])
        table.setRowCount(len(movements))
        from PyQt6.QtWidgets import QTableWidgetItem
        for row, move in enumerate(movements):
            sign = "+" if move.qty.milli > 0 else ""
            values = [local_time(move.created_at, ""), tr(f"move.{move.kind}"), sign + move.qty.format(),
                      move.username or "-", move.reason or ""]
            for col, text in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(text))
        table.resizeColumnsToContents()
        layout.addWidget(table)
        close = QPushButton(tr("lists.close"))
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
