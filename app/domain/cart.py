"""The shopping cart: pure Python, no Qt, no database. The sale screen drives it; held bills store it as JSON."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from app.domain.item import Item
from app.domain.money import Money
from app.domain.pricing import ROUND_RUPEE, Discount, Totals, compute_totals, discount_amount, line_gross
from app.security.passwords import ValidationError
from app.domain.quantity import Quantity


@dataclass
class CartLine:
    name_en: str
    name_ur: str | None
    unit: str
    unit_price: Money
    qty: Quantity
    item_id: int | None = None          # None = a one-off (Misc) item
    mode: str = "qty"                   # 'qty' or 'amount' ("Rs 100 of daal")
    amount: Money | None = None
    discount: Discount | None = None

    @property
    def is_misc(self) -> bool:
        return self.item_id is None

    @property
    def gross(self) -> Money:
        return line_gross(self.unit_price, self.qty, self.mode, self.amount)

    def display_name(self, lang: str) -> str:
        return self.name_ur if (lang == "ur" and self.name_ur) else self.name_en


def _discount_to_dict(discount: Discount | None) -> dict | None:
    if discount is None:
        return None
    return {"percent": str(discount.percent)} if discount.percent is not None else {"amount": discount.amount.paisa}


def _discount_from_dict(data: dict | None) -> Discount | None:
    if not data:
        return None
    return Discount(percent=Decimal(data["percent"])) if "percent" in data else Discount(amount=Money(data["amount"]))


@dataclass
class Cart:
    lines: list[CartLine] = field(default_factory=list)
    bill_discount: Discount | None = None

    @property
    def is_empty(self) -> bool:
        return not self.lines

    def clear(self) -> None:
        self.lines.clear()
        self.bill_discount = None

    def item_qty(self, item_id: int) -> Quantity:
        return Quantity(sum(line.qty.milli for line in self.lines if line.item_id == item_id))

    # ---- adding ------------------------------------------------------------------
    def add_item(self, item: Item, qty: Quantity, mode: str = "qty", amount: Money | None = None) -> int:
        """Add a catalog item. Scanning the same item again adds to its existing quantity line.
        Returns the index of the line that was added to."""
        if mode == "qty":
            for index, line in enumerate(self.lines):
                if line.item_id == item.id and line.mode == "qty":
                    line.qty = line.qty + qty
                    return index
        self.lines.append(CartLine(item.name_en, item.name_ur, item.unit, item.sale, qty, item.id, mode, amount))
        return len(self.lines) - 1

    def add_misc(self, name: str, unit_price: Money, qty: Quantity) -> int:
        self.lines.append(CartLine(name.strip(), None, "piece", unit_price, qty))
        return len(self.lines) - 1

    # ---- changing ----------------------------------------------------------------
    def remove(self, index: int) -> None:
        del self.lines[index]

    def set_quantity(self, index: int, qty: Quantity, mode: str = "qty", amount: Money | None = None) -> None:
        line = self.lines[index]
        line.qty, line.mode, line.amount = qty, mode, (amount if mode == "amount" else None)

    def set_line_discount(self, index: int, discount: Discount | None) -> None:
        self.lines[index].discount = discount

    def prune_invalid_discounts(self) -> bool:
        """After a quantity change a fixed discount can exceed what its line (or the bill) is now worth.
        Drop such discounts instead of letting the bill become invalid. True if anything was dropped."""
        dropped = False
        for line in self.lines:
            try:
                discount_amount(line.gross, line.discount)
            except ValidationError:
                line.discount, dropped = None, True
        if self.bill_discount is not None:
            try:
                self.totals()
            except ValidationError:
                self.bill_discount, dropped = None, True
        return dropped

    # ---- totals ------------------------------------------------------------------
    def totals(self, rounding: str = ROUND_RUPEE) -> Totals:
        return compute_totals([line.gross for line in self.lines], [line.discount for line in self.lines],
                              self.bill_discount, rounding)

    # ---- holding a bill ----------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "bill_discount": _discount_to_dict(self.bill_discount),
            "lines": [
                {"item_id": l.item_id, "name_en": l.name_en, "name_ur": l.name_ur, "unit": l.unit,
                 "unit_price": l.unit_price.paisa, "qty": l.qty.milli, "mode": l.mode,
                 "amount": l.amount.paisa if l.amount is not None else None, "discount": _discount_to_dict(l.discount)}
                for l in self.lines
            ],
        }

    @classmethod
    def from_dict(cls, data: dict, lookup: Callable[[int], Item | None]) -> tuple["Cart", list[str]]:
        """Rebuild a held cart. Catalog lines are re-priced from the current item data; items that were
        deleted or deactivated since are dropped, and their names are returned so the cashier is told."""
        cart = cls(bill_discount=_discount_from_dict(data.get("bill_discount")))
        dropped: list[str] = []
        for raw in data.get("lines", []):
            discount = _discount_from_dict(raw.get("discount"))
            amount = Money(raw["amount"]) if raw.get("amount") is not None else None
            if raw["item_id"] is None:   # Misc item keeps what was typed
                line = CartLine(raw["name_en"], None, raw["unit"], Money(raw["unit_price"]), Quantity(raw["qty"]),
                                None, raw["mode"], amount, discount)
            else:
                item = lookup(raw["item_id"])
                if item is None or not item.is_active:
                    dropped.append(raw["name_en"])
                    continue
                qty = Quantity(raw["qty"])
                if raw["mode"] == "amount" and amount is not None and item.sale.paisa > 0:
                    qty = Quantity.for_amount(amount, item.sale)   # the price may have changed since
                line = CartLine(item.name_en, item.name_ur, item.unit, item.sale, qty, item.id, raw["mode"], amount, discount)
            cart.lines.append(line)
        return cart, dropped
