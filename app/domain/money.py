"""Money: an integer number of paisa. Floats are never accepted."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:  # avoid a circular import at runtime
    from app.domain.quantity import Quantity

Number = Union[int, str, Decimal]


def div_round_half_up(numerator: int, denominator: int) -> int:
    """Integer division rounding halves away from zero (0.5 -> 1, -0.5 -> -1)."""
    if denominator == 0:
        raise ZeroDivisionError("division by zero")
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    sign = -1 if numerator < 0 else 1
    quotient, remainder = divmod(abs(numerator), denominator)
    if 2 * remainder >= denominator:
        quotient += 1
    return sign * quotient


@dataclass(frozen=True, slots=True, order=True)
class Money:
    paisa: int

    def __post_init__(self) -> None:
        if isinstance(self.paisa, bool) or not isinstance(self.paisa, int):
            raise TypeError("Money.paisa must be an int")

    # ---- construction -------------------------------------------------
    @classmethod
    def zero(cls) -> "Money":
        return cls(0)

    @classmethod
    def from_rupees(cls, value: Number) -> "Money":
        if isinstance(value, (bool, float)):
            raise TypeError("floats are not allowed for money; pass str, int or Decimal")
        try:
            amount = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"not a valid amount: {value!r}") from exc
        if not amount.is_finite():
            raise ValueError(f"not a valid amount: {value!r}")
        scaled = amount * 100
        if scaled != scaled.to_integral_value():
            raise ValueError("amount has more than 2 decimal places")
        return cls(int(scaled))

    # ---- arithmetic ---------------------------------------------------
    def __add__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.paisa + other.paisa)

    def __sub__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.paisa - other.paisa)

    def __neg__(self) -> "Money":
        return Money(-self.paisa)

    def __mul__(self, factor: int) -> "Money":
        if isinstance(factor, bool) or not isinstance(factor, int):
            return NotImplemented
        return Money(self.paisa * factor)

    __rmul__ = __mul__

    def percent(self, pct: Number) -> "Money":
        """pct percent of this amount, rounded half-up to the paisa."""
        if isinstance(pct, (bool, float)):
            raise TypeError("percent must be int, str or Decimal")
        ratio = Fraction(Decimal(pct))
        return Money(div_round_half_up(self.paisa * ratio.numerator, 100 * ratio.denominator))

    def for_quantity(self, qty: "Quantity") -> "Money":
        """Treat self as a price per base unit and price `qty` of it."""
        return Money(div_round_half_up(self.paisa * qty.milli, 1000))

    def round_to_rupee(self) -> "Money":
        return Money(div_round_half_up(self.paisa, 100) * 100)

    # ---- display ------------------------------------------------------
    def format(self) -> str:
        sign = "-" if self.paisa < 0 else ""
        rupees, paisa = divmod(abs(self.paisa), 100)
        return f"{sign}{rupees:,}.{paisa:02d}"

    def __str__(self) -> str:
        return self.format()
