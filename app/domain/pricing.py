"""Bill arithmetic, shared by the sale screen (live totals) and the checkout service (the real thing)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from app.domain.money import Money
from app.domain.quantity import Quantity
from app.security.passwords import ValidationError

ROUND_RUPEE = "rupee"
ROUND_NONE = "none"


@dataclass(frozen=True)
class Discount:
    """Either a percentage (0 to 100) or a fixed amount."""
    percent: Decimal | None = None
    amount: Money | None = None

    @staticmethod
    def of_percent(value: Decimal | str | int) -> "Discount":
        pct = Decimal(value)
        if not pct.is_finite() or pct < 0 or pct > 100 or pct != pct.quantize(Decimal("0.01")):
            raise ValidationError("error.discount_invalid")
        return Discount(percent=pct)

    @staticmethod
    def of_amount(money: Money) -> "Discount":
        if money.paisa < 0:
            raise ValidationError("error.discount_invalid")
        return Discount(amount=money)

    def __post_init__(self) -> None:
        if (self.percent is None) == (self.amount is None):
            raise ValueError("a discount is either a percent or an amount")


def line_gross(unit_price: Money, qty: Quantity, mode: str, amount: Money | None) -> Money:
    """What the line costs before any discount. In 'amount' mode the typed amount is kept exactly."""
    if mode == "amount":
        if amount is None:
            raise ValueError("amount mode needs an amount")
        return amount
    return unit_price.for_quantity(qty)


def discount_amount(base: Money, discount: Discount | None) -> Money:
    """The money value of a discount on `base`. Never more than `base`."""
    if discount is None:
        return Money(0)
    value = base.percent(discount.percent) if discount.percent is not None else discount.amount
    if value.paisa < 0 or value > base:
        raise ValidationError("error.discount_invalid")
    return value


def allocate(total: int, weights: Sequence[int]) -> list[int]:
    """Split `total` paisa across lines in proportion to `weights`, to the paisa, largest remainder first.
    The shares always add up to `total` exactly."""
    count = len(weights)
    weight_sum = sum(weights)
    if count == 0:
        return []
    if weight_sum == 0:
        if total != 0:
            raise ValueError("cannot allocate a non-zero total over zero weights")
        return [0] * count
    shares = [total * w // weight_sum for w in weights]
    remainders = [total * w % weight_sum for w in weights]
    leftover = total - sum(shares)
    for index in sorted(range(count), key=lambda i: (-remainders[i], i))[:leftover]:
        shares[index] += 1
    return shares


@dataclass(frozen=True)
class LineAmounts:
    gross: Money
    discount: Money      # the line's own discount
    bill_share: Money    # its share of the bill discount
    net: Money           # what the customer pays for the line (before bill-level rounding)


@dataclass(frozen=True)
class Totals:
    lines: tuple[LineAmounts, ...]
    subtotal: Money
    item_discount: Money
    bill_discount: Money
    rounding: Money
    payable: Money

    @property
    def total_discount(self) -> Money:
        return self.item_discount + self.bill_discount

    @property
    def discount_percent(self) -> Decimal:
        """Total discount as a percentage of the subtotal (used for the cashier's discount limit)."""
        if self.subtotal.paisa == 0:
            return Decimal(0)
        return Decimal(self.total_discount.paisa) * 100 / Decimal(self.subtotal.paisa)


def compute_totals(grosses: Sequence[Money], line_discounts: Sequence[Discount | None],
                   bill_discount: Discount | None, rounding: str = ROUND_RUPEE) -> Totals:
    if len(grosses) != len(line_discounts):
        raise ValueError("one discount slot per line")
    own = [discount_amount(g, d) for g, d in zip(grosses, line_discounts)]
    after_items = [g - d for g, d in zip(grosses, own)]
    subtotal = Money(sum(g.paisa for g in grosses))
    item_discount = Money(sum(d.paisa for d in own))
    base = Money(sum(a.paisa for a in after_items))
    bill_total = discount_amount(base, bill_discount)
    shares = allocate(bill_total.paisa, [a.paisa for a in after_items])
    lines = tuple(
        LineAmounts(g, d, Money(s), a - Money(s)) for g, d, a, s in zip(grosses, own, after_items, shares)
    )
    before_rounding = base - bill_total
    payable = before_rounding.round_to_rupee() if rounding == ROUND_RUPEE else before_rounding
    return Totals(lines, subtotal, item_discount, bill_total, payable - before_rounding, payable)
