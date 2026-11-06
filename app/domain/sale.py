from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.money import Money
from app.domain.pricing import Discount
from app.domain.quantity import Quantity

PAYMENT_METHODS = ("cash", "card", "wallet")   # 'udhar' joins in Phase 6 with customer records


@dataclass(frozen=True)
class SaleLineInput:
    """A catalog item (item_id) or a Misc item (misc_name + misc_price). The service looks prices up itself."""
    qty: Quantity
    item_id: int | None = None
    mode: str = "qty"                  # 'amount': `amount` is what the customer pays, quantity is derived
    amount: Money | None = None
    discount: Discount | None = None
    misc_name: str | None = None
    misc_price: Money | None = None


@dataclass(frozen=True)
class PaymentInput:
    method: str
    amount: Money


@dataclass(frozen=True)
class CheckoutInput:
    lines: list[SaleLineInput]
    payments: list[PaymentInput]
    bill_discount: Discount | None = None
    note: str | None = None


@dataclass(frozen=True)
class OrderLine:
    item_id: int | None
    name_en: str
    name_ur: str | None
    unit: str
    qty: Quantity
    unit_price: Money
    cost: Money
    entry_mode: str
    gross: Money
    discount: Money
    bill_share: Money
    total: Money
    is_misc: bool

    def display_name(self, lang: str) -> str:
        return self.name_ur if (lang == "ur" and self.name_ur) else self.name_en


@dataclass(frozen=True)
class Payment:
    method: str
    amount: Money


@dataclass(frozen=True)
class Order:
    id: int
    bill_no: int
    business_date: str
    created_at: str
    cashier_name: str | None
    subtotal: Money
    item_discount: Money
    bill_discount: Money
    rounding: Money
    payable: Money
    status: str
    note: str | None = None
    lines: tuple[OrderLine, ...] = field(default_factory=tuple)
    payments: tuple[Payment, ...] = field(default_factory=tuple)

    @property
    def total_discount(self) -> Money:
        return self.item_discount + self.bill_discount
