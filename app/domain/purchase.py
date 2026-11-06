from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.money import Money, div_round_half_up
from app.domain.quantity import Quantity

PAY_METHODS = ("cash", "card", "wallet")


@dataclass(frozen=True)
class PurchaseLineInput:
    """Give EITHER unit_cost (per kg / litre / piece) OR line_total (what the invoice says for the line)."""
    item_id: int
    qty: Quantity
    unit_cost: Money | None = None
    line_total: Money | None = None
    expiry_date: str | None = None     # YYYY-MM-DD
    new_sale: Money | None = None      # optionally update the sale price at the same time


@dataclass(frozen=True)
class PurchaseInput:
    lines: list[PurchaseLineInput]
    supplier_id: int | None = None
    invoice_no: str | None = None
    purchase_date: str | None = None   # defaults to today
    paid: Money = Money(0)
    paid_method: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class PurchaseWarning:
    kind: str          # 'cost_above_sale'
    item_id: int
    item_name: str
    avg_cost: Money
    sale: Money


@dataclass(frozen=True)
class PurchaseResult:
    purchase_id: int
    total: Money
    warnings: tuple[PurchaseWarning, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PurchaseLine:
    item_id: int
    item_name_en: str
    item_name_ur: str | None
    short_code: str
    unit: str
    qty: Quantity
    unit_cost: Money
    line_total: Money
    expiry_date: str | None
    avg_before: Money
    avg_after: Money


@dataclass(frozen=True)
class Purchase:
    id: int
    supplier_id: int | None
    supplier_name: str | None
    invoice_no: str | None
    purchase_date: str
    total: Money
    paid: Money
    paid_method: str | None
    note: str | None
    created_by_name: str | None
    created_at: str

    @property
    def due(self) -> Money:
        return self.total - self.paid


def resolve_line_costs(line: PurchaseLineInput) -> tuple[Money, Money]:
    """(unit_cost, line_total) for a line. A typed line total is kept exactly; only the unit cost is rounded."""
    if (line.unit_cost is None) == (line.line_total is None):
        raise ValueError("give exactly one of unit_cost or line_total")
    if line.qty.milli <= 0:
        raise ValueError("quantity must be positive")
    if line.unit_cost is not None:
        return line.unit_cost, line.unit_cost.for_quantity(line.qty)
    return Money(div_round_half_up(line.line_total.paisa * 1000, line.qty.milli)), line.line_total
