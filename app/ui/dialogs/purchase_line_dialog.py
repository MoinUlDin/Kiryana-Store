from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QCheckBox, QDateEdit, QLabel, QLineEdit, QRadioButton

from app.domain.item import Item
from app.domain.parsing import parse_money
from app.domain.purchase import PurchaseLineInput, resolve_line_costs
from app.security.passwords import ValidationError
from app.ui.dialogs.user_dialogs import _FormDialog
from app.ui.i18n.manager import I18n
from app.ui.quantity_edit import QuantityEdit


def to_qdate(day: date) -> QDate:
    return QDate(day.year, day.month, day.day)


class PurchaseLineDialog(_FormDialog):
    """One line of a purchase. After accept(), `.line` holds the PurchaseLineInput."""

    def __init__(self, i18n: I18n, item: Item, today: date, initial: PurchaseLineInput | None = None, parent=None):
        tr = i18n.tr
        super().__init__(i18n, f"{tr('purchase.line.title')}: {item.display_name(i18n.lang)}", parent)
        self.item = item
        self.line: PurchaseLineInput | None = None
        self._today = today

        self._qty = QuantityEdit(i18n, item.unit)
        self._mode_unit = QRadioButton(tr("purchase.line.mode_unit"))
        self._mode_total = QRadioButton(tr("purchase.line.mode_total"))
        self._cost = QLineEdit()
        self._has_expiry = QCheckBox(tr("purchase.line.has_expiry"))
        self._expiry = QDateEdit(to_qdate(today + timedelta(days=180)))
        self._expiry.setCalendarPopup(True)
        self._expiry.setMinimumDate(to_qdate(today))
        self._expiry.setEnabled(False)
        self._new_sale = QLineEdit()
        self._warn = QLabel()
        self._warn.setObjectName("ErrorLabel")
        self._warn.setWordWrap(True)
        self._warn.hide()

        info = QLabel(tr("purchase.line.current", sale=item.sale.format(), cost=item.cost.format()))
        info.setObjectName("StatusNote")
        self.form.addRow(info)
        self.form.addRow(tr("purchase.line.qty"), self._qty)
        self.form.addRow(self._mode_unit)
        self.form.addRow(self._mode_total)
        self.form.addRow(tr("purchase.line.cost"), self._cost)
        self.form.addRow(self._warn)
        self.form.addRow(self._has_expiry, self._expiry)
        self.form.addRow(tr("purchase.line.new_sale"), self._new_sale)

        if initial is not None:
            self._qty.set_quantity(initial.qty)
            if initial.unit_cost is not None:
                self._mode_unit.setChecked(True)
                self._cost.setText(initial.unit_cost.format().replace(",", ""))
            else:
                self._mode_total.setChecked(True)
                self._cost.setText(initial.line_total.format().replace(",", ""))
            if initial.expiry_date:
                self._has_expiry.setChecked(True)
                self._expiry.setEnabled(True)
                self._expiry.setDate(QDate.fromString(initial.expiry_date, "yyyy-MM-dd"))
            if initial.new_sale is not None:
                self._new_sale.setText(initial.new_sale.format().replace(",", ""))
        else:
            self._mode_total.setChecked(True)   # invoices usually show a line total

        self._has_expiry.toggled.connect(self._expiry.setEnabled)
        for widget in (self._cost, self._new_sale, self._qty.edit):
            widget.textChanged.connect(self._update_warning)
        self._mode_unit.toggled.connect(self._update_warning)
        self._qty.picker.currentIndexChanged.connect(self._update_warning)
        self._qty.edit.setFocus()

    def _build(self) -> PurchaseLineInput:
        qty = self._qty.quantity()
        cost = parse_money(self._cost.text())
        new_sale = parse_money(self._new_sale.text()) if self._new_sale.text().strip() else None
        expiry = None
        if self._has_expiry.isChecked():
            expiry = self._expiry.date().toPyDate().isoformat()
        if self._mode_unit.isChecked():
            return PurchaseLineInput(self.item.id, qty, unit_cost=cost, expiry_date=expiry, new_sale=new_sale)
        return PurchaseLineInput(self.item.id, qty, line_total=cost, expiry_date=expiry, new_sale=new_sale)

    def _update_warning(self, *_args) -> None:
        try:
            line = self._build()
            unit_cost, _total = resolve_line_costs(line)
        except (ValidationError, ValueError):
            self._warn.hide()
            return
        sale = line.new_sale if line.new_sale is not None else self.item.sale
        if unit_cost > sale:
            self._warn.setText(self.i18n.tr("purchase.line.warn", cost=unit_cost.format(), sale=sale.format()))
            self._warn.show()
        else:
            self._warn.hide()

    def _save(self) -> None:
        try:
            line = self._build()
            if line.qty.milli <= 0:
                raise ValidationError("error.quantity_invalid")
            if not self.item.allow_fraction and not line.qty.is_whole:
                raise ValidationError("error.fraction_not_allowed")
        except ValidationError as exc:
            self.show_error(self.i18n.tr(exc.code, **exc.params))
            return
        self.line = line
        self.accept()
