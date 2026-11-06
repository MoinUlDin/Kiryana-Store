"""Quantity: an integer in thousandths of the item's base unit.

2.5 kg -> 2500, 20 g -> 20 (milli-kg), 5 pieces -> 5000.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Union

from app.domain.money import Money, div_round_half_up

Number = Union[int, str, Decimal]


@dataclass(frozen=True, slots=True, order=True)
class Quantity:
    milli: int

    def __post_init__(self) -> None:
        if isinstance(self.milli, bool) or not isinstance(self.milli, int):
            raise TypeError("Quantity.milli must be an int")

    @classmethod
    def zero(cls) -> "Quantity":
        return cls(0)

    @classmethod
    def from_decimal(cls, value: Number) -> "Quantity":
        """Parse a user-entered quantity such as '2.5'. Max 3 decimal places."""
        if isinstance(value, (bool, float)):
            raise TypeError("floats are not allowed for quantities; pass str, int or Decimal")
        try:
            amount = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"not a valid quantity: {value!r}") from exc
        if not amount.is_finite():
            raise ValueError(f"not a valid quantity: {value!r}")
        scaled = amount * 1000
        if scaled != scaled.to_integral_value():
            raise ValueError("quantity has more than 3 decimal places")
        return cls(int(scaled))

    @classmethod
    def from_small_unit(cls, value: Number) -> "Quantity":
        """Whole grams (for kg items) or whole millilitres (for litre items): 250 g -> Quantity(250)."""
        if isinstance(value, (bool, float)):
            raise TypeError("floats are not allowed for quantities; pass str, int or Decimal")
        try:
            amount = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"not a valid quantity: {value!r}") from exc
        if not amount.is_finite() or amount != amount.to_integral_value():
            raise ValueError("grams and millilitres must be whole numbers")
        return cls(int(amount))

    @classmethod
    def for_amount(cls, amount: Money, unit_price: Money) -> "Quantity":
        """How much can `amount` buy at `unit_price` per base unit?

        Rs 100 of daal at Rs 1000/kg -> 0.100 kg. The caller keeps the typed
        amount as the line total; only the quantity is derived (and rounded).
        """
        if unit_price.paisa <= 0:
            raise ValueError("unit price must be positive")
        if amount.paisa < 0:
            raise ValueError("amount cannot be negative")
        return cls(div_round_half_up(amount.paisa * 1000, unit_price.paisa))

    def __add__(self, other: "Quantity") -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        return Quantity(self.milli + other.milli)

    def __sub__(self, other: "Quantity") -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        return Quantity(self.milli - other.milli)

    def __neg__(self) -> "Quantity":
        return Quantity(-self.milli)

    @property
    def is_whole(self) -> bool:
        return self.milli % 1000 == 0

    def format(self) -> str:
        sign = "-" if self.milli < 0 else ""
        whole, frac = divmod(abs(self.milli), 1000)
        text = f"{whole}"
        if frac:
            text += "." + f"{frac:03d}".rstrip("0")
        return sign + text

    def __str__(self) -> str:
        return self.format()
