from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt6.QtWidgets import QLineEdit, QPushButton, QRadioButton

from app.domain.money import Money
from app.domain.parsing import parse_money
from app.domain.pricing import Discount
from app.domain.text import normalize_search
from app.security.passwords import ValidationError
from app.ui.dialogs.user_dialogs import _FormDialog
from app.ui.i18n.manager import I18n


class DiscountDialog(_FormDialog):
    """A percentage or an amount. After accept(): .discount (None means 'remove the discount')."""

    def __init__(self, i18n: I18n, title: str, base: Money, current: Discount | None = None, parent=None):
        super().__init__(i18n, title, parent)
        tr = i18n.tr
        self._base = base
        self.discount: Discount | None = None
        self._percent = QRadioButton(tr("discount.percent"))
        self._amount = QRadioButton(tr("discount.amount"))
        self._value = QLineEdit()
        self.form.addRow(self._percent)
        self.form.addRow(self._amount)
        self.form.addRow(tr("discount.value"), self._value)
        clear = QPushButton(tr("discount.clear"))
        clear.clicked.connect(self._clear)
        self.form.addRow(clear)
        if current is not None and current.amount is not None:
            self._amount.setChecked(True)
            self._value.setText(current.amount.format().replace(",", ""))
        else:
            self._percent.setChecked(True)
            if current is not None:
                self._value.setText(f"{current.percent.normalize():f}")
        self._value.setFocus()
        self._value.selectAll()

    def _clear(self) -> None:
        self.discount = None
        self.accept()

    def _save(self) -> None:
        try:
            if self._percent.isChecked():
                try:
                    cleaned = normalize_search(self._value.text()).replace(",", "").replace("%", "").strip()
                    discount = Discount.of_percent(Decimal(cleaned))
                except InvalidOperation as exc:
                    raise ValidationError("error.discount_invalid") from exc
            else:
                discount = Discount.of_amount(parse_money(self._value.text()))
                if discount.amount > self._base:
                    raise ValidationError("error.discount_invalid")
        except ValidationError as exc:
            code = "error.discount_invalid" if exc.code == "error.price_invalid" else exc.code
            self.show_error(self.i18n.tr(code, **exc.params))
            return
        self.discount = discount
        self.accept()
