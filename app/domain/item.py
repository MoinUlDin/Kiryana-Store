from __future__ import annotations

from dataclasses import dataclass

from app.domain.money import Money
from app.domain.quantity import Quantity

UNITS = ("piece", "kg", "litre")
SMALL_UNIT = {"kg": "g", "litre": "ml"}  # typed in the shop, stored as thousandths of the base unit


@dataclass(frozen=True)
class ItemInput:
    """What the item form collects. Validation happens in ItemService."""
    name_en: str
    short_code: str
    unit: str
    sale: Money
    cost: Money = Money(0)
    name_ur: str | None = None
    barcode: str | None = None
    category_id: int | None = None
    brand_id: int | None = None
    allow_fraction: bool = False
    tax_bp: int | None = None
    low_stock: Quantity = Quantity(0)


@dataclass(frozen=True)
class Item:
    id: int
    name_en: str
    name_ur: str | None
    short_code: str
    barcode: str | None
    category_id: int | None
    brand_id: int | None
    unit: str
    allow_fraction: bool
    cost: Money
    sale: Money
    tax_bp: int | None
    stock: Quantity
    low_stock: Quantity
    is_active: bool

    def display_name(self, lang: str) -> str:
        if lang == "ur" and self.name_ur:
            return self.name_ur
        return self.name_en

    @property
    def cost_above_sale(self) -> bool:
        return self.cost > self.sale

    @property
    def is_low(self) -> bool:
        return self.low_stock.milli > 0 and self.stock.milli <= self.low_stock.milli
