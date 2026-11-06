from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit

from app.domain.item import UNITS, Item, ItemInput
from app.domain.parsing import format_tax_percent, parse_money, parse_tax_percent
from app.domain.quantity import Quantity
from app.security.passwords import ValidationError
from app.services.container import Services
from app.ui.dialogs.user_dialogs import _FormDialog
from app.ui.i18n.manager import I18n
from app.ui.quantity_edit import QuantityEdit


def money_text(money) -> str:
    return "" if money.paisa == 0 else money.format().replace(",", "")


class ItemDialog(_FormDialog):
    """Add or edit an item. submit(data, opening_stock_or_None) -> None on success, or an error message."""

    def __init__(self, i18n: I18n, services: Services, item: Item | None, has_history: bool,
                 submit: Callable[[ItemInput, Quantity | None], str | None], parent=None):
        tr = i18n.tr
        super().__init__(i18n, tr("item.dialog.edit" if item else "item.dialog.add"), parent)
        self._submit = submit
        self._item = item
        self.setMinimumWidth(480)

        self._name_en = QLineEdit(item.name_en if item else "")
        self._name_ur = QLineEdit(item.name_ur or "" if item else "")
        self._code = QLineEdit(item.short_code if item else "")
        self._barcode = QLineEdit(item.barcode or "" if item else "")
        self._category = self._list_combo(services.categories.list(), item.category_id if item else None)
        self._brand = self._list_combo(services.brands.list(), item.brand_id if item else None)
        self._unit = QComboBox()
        for unit in UNITS:
            self._unit.addItem(tr(f"unit.{unit}"), unit)
        self._fraction = QCheckBox(tr("item.field.fraction"))
        self._cost = QLineEdit(money_text(item.cost) if item else "")
        self._sale = QLineEdit(money_text(item.sale) if item else "")
        self._tax = QLineEdit(format_tax_percent(item.tax_bp) if item else "")
        start_unit = item.unit if item else "kg"
        self._unit.setCurrentIndex(UNITS.index(start_unit))
        self._low = QuantityEdit(i18n, start_unit)
        if item:
            self._low.set_quantity(item.low_stock)
            self._fraction.setChecked(item.allow_fraction)
        else:
            self._fraction.setChecked(start_unit != "piece")
        self._opening = QuantityEdit(i18n, start_unit)
        self._warn = QLabel(tr("item.warn.cost_above_sale"))
        self._warn.setObjectName("ErrorLabel")
        self._warn.setWordWrap(True)
        self._warn.hide()
        self._unit_note = QLabel(tr("item.unit_changed_note"))
        self._unit_note.setObjectName("StatusNote")
        self._unit_note.setWordWrap(True)
        self._unit_note.hide()
        self._has_history = has_history

        form = self.form
        form.addRow(tr("item.field.name_en"), self._name_en)
        form.addRow(tr("item.field.name_ur"), self._name_ur)
        form.addRow(tr("item.field.short_code"), self._code)
        form.addRow(tr("item.field.barcode"), self._barcode)
        form.addRow(tr("items.col.category"), self._category)
        form.addRow(tr("item.field.brand"), self._brand)
        form.addRow(tr("item.field.unit"), self._unit)
        form.addRow(self._unit_note)
        form.addRow(self._fraction)
        form.addRow(tr("item.field.cost"), self._cost)
        form.addRow(tr("item.field.sale"), self._sale)
        form.addRow(self._warn)
        form.addRow(tr("item.field.tax"), self._tax)
        form.addRow(tr("item.field.low"), self._low)
        if item is None:
            form.addRow(tr("item.field.opening"), self._opening)

        self._unit.currentIndexChanged.connect(self._on_unit_changed)
        self._cost.textChanged.connect(self._update_warning)
        self._sale.textChanged.connect(self._update_warning)
        self._update_warning()
        self._name_en.setFocus()

    @staticmethod
    def _list_combo(entries, selected_id: int | None) -> QComboBox:
        combo = QComboBox()
        combo.addItem("-", None)
        for entry in entries:
            combo.addItem(entry.name_en, entry.id)
        index = combo.findData(selected_id)
        combo.setCurrentIndex(max(index, 0))
        return combo

    def _on_unit_changed(self) -> None:
        unit = self._unit.currentData()
        if self._item is not None:
            self._unit_note.setVisible(self._has_history and unit != self._item.unit)
        self._low.set_unit(unit)
        self._opening.set_unit(unit)
        if self._item is None:
            self._fraction.setChecked(unit != "piece")

    def _update_warning(self) -> None:
        try:
            cost = parse_money(self._cost.text(), allow_empty=True)
            sale = parse_money(self._sale.text())
            self._warn.setVisible(cost > sale)
        except ValidationError:
            self._warn.hide()

    def _save(self) -> None:
        tr = self.i18n.tr
        try:
            data = ItemInput(
                name_en=self._name_en.text(), name_ur=self._name_ur.text(), short_code=self._code.text(),
                barcode=self._barcode.text(), category_id=self._category.currentData(),
                brand_id=self._brand.currentData(), unit=self._unit.currentData(),
                allow_fraction=self._fraction.isChecked(), cost=parse_money(self._cost.text(), allow_empty=True),
                sale=parse_money(self._sale.text()), tax_bp=parse_tax_percent(self._tax.text()),
                low_stock=self._low.quantity(allow_empty=True),
            )
            opening = self._opening.quantity(allow_empty=True) if self._item is None else None
        except ValidationError as exc:
            self.show_error(tr(exc.code, **exc.params))
            return
        error = self._submit(data, opening)
        if error:
            self.show_error(error)
        else:
            self.accept()
