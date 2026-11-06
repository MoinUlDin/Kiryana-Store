from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QWidget

from app.domain.item import SMALL_UNIT
from app.domain.parsing import parse_quantity
from app.domain.quantity import Quantity
from app.ui.i18n.manager import I18n


class QuantityEdit(QWidget):
    """A number box plus a unit picker: kg items offer kg or g, litre items offer litre or ml,
    piece items only pieces. quantity() always returns an exact Quantity in the base unit."""

    def __init__(self, i18n: I18n, unit: str = "piece", parent=None) -> None:
        super().__init__(parent)
        self._i18n = i18n
        self._unit = unit
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.picker = QComboBox()
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.picker)
        self.set_unit(unit)

    def set_unit(self, unit: str) -> None:
        self._unit = unit
        tr = self._i18n.tr
        self.picker.clear()
        self.picker.addItem(tr(f"unit.{unit}"), False)
        if unit in SMALL_UNIT:
            self.picker.addItem(tr(f"unit.{SMALL_UNIT[unit]}"), True)

    def quantity(self, allow_empty: bool = False) -> Quantity:
        return parse_quantity(self.edit.text(), small_unit=bool(self.picker.currentData()), allow_empty=allow_empty)

    def set_quantity(self, qty: Quantity) -> None:
        self.picker.setCurrentIndex(0)
        self.edit.setText(qty.format() if qty.milli else "")
