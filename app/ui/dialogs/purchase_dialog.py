from __future__ import annotations

from datetime import date
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidgetItem, QVBoxLayout,
)

from app.domain.item import Item
from app.domain.money import Money
from app.domain.parsing import parse_money
from app.domain.purchase import PAY_METHODS, PurchaseInput, PurchaseLineInput, resolve_line_costs
from app.security.passwords import ValidationError
from app.services.container import Services
from app.ui.dialogs.item_picker import ItemPickerDialog
from app.ui.dialogs.purchase_line_dialog import PurchaseLineDialog, to_qdate
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page


class PurchaseDialog(QDialog):
    """Enter a supplier invoice: header, lines, payment. submit(PurchaseInput) -> None on success or an error text."""

    def __init__(self, i18n: I18n, services: Services, today: date, guard: Callable[[str, str], bool],
                 submit: Callable[[PurchaseInput], str | None], parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self._services = services
        self._today = today
        self._guard = guard
        self._submit = submit
        self._lines: list[tuple[Item, PurchaseLineInput]] = []
        tr = i18n.tr
        self.setWindowTitle(tr("purchase.dialog.title"))
        self.setMinimumSize(820, 640)

        layout = QVBoxLayout(self)
        header = QFormLayout()
        self._supplier = QComboBox()
        self._supplier.addItem("-", None)
        for supplier in services.suppliers.list():
            self._supplier.addItem(supplier.name, supplier.id)
        self._invoice = QLineEdit()
        self._date = QDateEdit(to_qdate(today))
        self._date.setCalendarPopup(True)
        self._date.setMaximumDate(to_qdate(today))
        header.addRow(tr("purchase.supplier"), self._supplier)
        header.addRow(tr("purchase.invoice"), self._invoice)
        header.addRow(tr("purchase.date"), self._date)
        layout.addLayout(header)

        bar = QHBoxLayout()
        add = QPushButton(tr("purchase.add_line"))
        add.setObjectName("PrimaryButton")
        add.clicked.connect(self._add_line)
        edit = QPushButton(tr("purchase.edit_line"))
        edit.clicked.connect(self._edit_line)
        remove = QPushButton(tr("purchase.remove_line"))
        remove.clicked.connect(self._remove_line)
        for button in (add, edit, remove):
            bar.addWidget(button)
        bar.addStretch(1)
        layout.addLayout(bar)

        self._table = Page.make_table(6)
        self._table.setHorizontalHeaderLabels([
            tr("purchase.col.item"), tr("purchase.col.qty"), tr("purchase.col.unit_cost"),
            tr("purchase.col.line_total"), tr("purchase.col.expiry"), tr("purchase.col.new_sale"),
        ])
        self._table.doubleClicked.connect(lambda _i: self._edit_line())
        layout.addWidget(self._table, 1)

        self._total = QLabel()
        self._total.setObjectName("PageTitle")
        layout.addWidget(self._total)

        pay = QFormLayout()
        paid_row = QHBoxLayout()
        self._paid = QLineEdit()
        self._pay_method = QComboBox()
        for method in PAY_METHODS:
            self._pay_method.addItem(tr(f"pay.{method}"), method)
        full = QPushButton(tr("purchase.pay_full"))
        full.clicked.connect(self._pay_full)
        paid_row.addWidget(self._paid, 1)
        paid_row.addWidget(self._pay_method)
        paid_row.addWidget(full)
        pay.addRow(tr("purchase.paid"), paid_row)
        self._due = QLabel()
        self._due.setObjectName("StatusNote")
        pay.addRow(self._due)
        self._note = QLineEdit()
        pay.addRow(tr("purchase.note"), self._note)
        layout.addLayout(pay)
        self._paid.textChanged.connect(self._update_totals)

        self._error = QLabel()
        self._error.setObjectName("ErrorLabel")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._error)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton(tr("dialog.cancel"))
        cancel.clicked.connect(self.reject)
        save = QPushButton(tr("dialog.save"))
        save.setObjectName("PrimaryButton")
        save.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(save)
        layout.addLayout(row)
        self._update_totals()

    # ---- lines -----------------------------------------------------------------
    def _show_error(self, text: str | None) -> None:
        self._error.setVisible(bool(text))
        self._error.setText(text or "")

    def _add_line(self) -> None:
        picker = ItemPickerDialog(self.i18n, self._services, self)
        if picker.exec() and picker.chosen is not None:
            self._edit_dialog(picker.chosen, None, None)

    def _edit_line(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._lines):
            item, line = self._lines[row]
            self._edit_dialog(item, line, row)

    def _edit_dialog(self, item: Item, initial: PurchaseLineInput | None, row: int | None) -> None:
        fresh = self._services.items.get(item.id) or item   # current prices
        dialog = PurchaseLineDialog(self.i18n, fresh, self._today, initial, self)
        if not dialog.exec() or dialog.line is None:
            return
        line = dialog.line
        if line.new_sale is not None and line.new_sale != fresh.sale:
            if not self._guard("price.sale", self.i18n.tr("purchase.col.new_sale")):
                self._show_error(self.i18n.tr("error.not_allowed"))
                return
        self._show_error(None)
        if row is None:
            self._lines.append((fresh, line))
        else:
            self._lines[row] = (fresh, line)
        self._refresh_table()

    def _remove_line(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._lines):
            del self._lines[row]
            self._refresh_table()

    def _refresh_table(self) -> None:
        tr = self.i18n.tr
        self._table.setRowCount(len(self._lines))
        for row, (item, line) in enumerate(self._lines):
            unit_cost, total = resolve_line_costs(line)
            values = [item.display_name(self.i18n.lang), f"{line.qty.format()} {tr('unit.' + item.unit)}",
                      unit_cost.format(), total.format(), line.expiry_date or "-",
                      line.new_sale.format() if line.new_sale is not None else "-"]
            for col, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if col in (1, 2, 3):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                self._table.setItem(row, col, cell)
        self._table.resizeColumnsToContents()
        self._update_totals()

    # ---- money -----------------------------------------------------------------
    def _total_money(self) -> Money:
        return Money(sum(resolve_line_costs(line)[1].paisa for _item, line in self._lines))

    def _update_totals(self) -> None:
        total = self._total_money()
        self._total.setText(self.i18n.tr("purchase.total", total=total.format()))
        try:
            due = total - parse_money(self._paid.text(), allow_empty=True)
            self._due.setText(self.i18n.tr("purchase.due", due=due.format()))
        except ValidationError:
            self._due.setText("")

    def _pay_full(self) -> None:
        self._paid.setText(self._total_money().format().replace(",", ""))

    # ---- save ------------------------------------------------------------------
    def _save(self) -> None:
        try:
            paid = parse_money(self._paid.text(), allow_empty=True)
        except ValidationError as exc:
            self._show_error(self.i18n.tr(exc.code, **exc.params))
            return
        data = PurchaseInput(
            lines=[line for _item, line in self._lines], supplier_id=self._supplier.currentData(),
            invoice_no=self._invoice.text(), purchase_date=self._date.date().toPyDate().isoformat(),
            paid=paid, paid_method=self._pay_method.currentData() if paid.paisa > 0 else None,
            note=self._note.text(),
        )
        error = self._submit(data)
        if error:
            self._show_error(error)
        else:
            self.accept()
