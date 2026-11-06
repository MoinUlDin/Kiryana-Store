from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QLineEdit, QRadioButton

from app.domain.money import Money
from app.domain.parsing import parse_money
from app.domain.quantity import Quantity
from app.security.passwords import ValidationError
from app.ui.dialogs.user_dialogs import _FormDialog
from app.ui.i18n.manager import I18n
from app.ui.quantity_edit import QuantityEdit


class QuantityAmountDialog(_FormDialog):
    """How much of an item? Either a quantity (2.5 kg, 250 g) or an amount of money ('Rs 100 of daal').
    After accept(): .qty, .mode ('qty' or 'amount') and .amount."""

    def __init__(self, i18n: I18n, name: str, unit: str, price: Money, *, allow_fraction: bool, allow_amount: bool,
                 stock: Quantity | None = None, initial_qty: Quantity | None = None,
                 initial_mode: str = "qty", initial_amount: Money | None = None, parent=None):
        tr = i18n.tr
        super().__init__(i18n, f"{tr('qty.title')}: {name}", parent)
        self._price = price
        self._allow_fraction = allow_fraction
        self.qty: Quantity | None = None
        self.mode = "qty"
        self.amount: Money | None = None

        info = f"{tr('qty.price_info', price=price.format(), unit=tr('unit.' + unit))}"
        if stock is not None:
            info += "   |   " + tr("qty.stock", qty=stock.format(), unit=tr("unit." + unit))
        label = QLabel(info)
        label.setObjectName("StatusNote")
        self.form.addRow(label)

        self._by_qty = QRadioButton(tr("qty.by_quantity"))
        self._by_amount = QRadioButton(tr("qty.by_amount"))
        self._qty = QuantityEdit(i18n, unit)
        self._amount = QLineEdit()
        self._preview = QLabel()
        self._preview.setObjectName("StatusNote")
        self.form.addRow(self._by_qty, self._qty)
        if allow_amount:
            self.form.addRow(self._by_amount, self._amount)
        self.form.addRow(self._preview)
        self._unit = unit

        if initial_mode == "amount" and allow_amount:
            self._by_amount.setChecked(True)
            if initial_amount is not None:
                self._amount.setText(initial_amount.format().replace(",", ""))
        else:
            self._by_qty.setChecked(True)
            if initial_qty is not None:
                self._qty.set_quantity(initial_qty)
        self._by_qty.toggled.connect(self._sync)
        for widget in (self._qty.edit, self._amount):
            widget.textChanged.connect(self._sync)
        self._qty.picker.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self, *_args) -> None:
        by_qty = self._by_qty.isChecked()
        self._qty.setEnabled(by_qty)
        self._amount.setEnabled(not by_qty)
        (self._qty.edit if by_qty else self._amount).setFocus()
        try:
            qty, amount = self._values()
            self._preview.setText(self.i18n.tr("qty.preview", qty=qty.format(), unit=self.i18n.tr(f"unit.{self._unit}"),
                                               amount=amount.format()))
        except ValidationError:
            self._preview.setText("")

    def _values(self) -> tuple[Quantity, Money]:
        if self._by_qty.isChecked():
            qty = self._qty.quantity()
            return qty, self._price.for_quantity(qty)
        amount = parse_money(self._amount.text())
        if amount.paisa <= 0 or self._price.paisa <= 0:
            raise ValidationError("error.price_invalid")
        return Quantity.for_amount(amount, self._price), amount

    def _save(self) -> None:
        try:
            qty, amount = self._values()
            if qty.milli <= 0:
                raise ValidationError("error.quantity_invalid")
            if not self._allow_fraction and not qty.is_whole:
                raise ValidationError("error.fraction_not_allowed")
        except ValidationError as exc:
            self.show_error(self.i18n.tr(exc.code, **exc.params))
            return
        self.qty, self.mode = qty, ("qty" if self._by_qty.isChecked() else "amount")
        self.amount = amount if self.mode == "amount" else None
        self.accept()
