"""Turn what a shopkeeper types into exact values. Pure Python, unit-tested.
Accepts Western, Arabic-Indic and Eastern Arabic-Indic digits, spaces and thousands commas."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.domain.money import Money
from app.domain.quantity import Quantity
from app.domain.text import normalize_search
from app.security.passwords import ValidationError


_PLAIN_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def _number_text(text: str) -> str:
    """Normalised digits only. Anything else ('1e3', 'NaN', '0x10') is returned unchanged
    and fails the plain-number check in the caller, so odd notations never sneak in."""
    return normalize_search(text).replace(",", "").replace("\u066b", ".").replace(" ", "")


def _is_plain_number(cleaned: str) -> bool:
    return bool(_PLAIN_NUMBER.match(cleaned))


def parse_money(text: str, *, allow_empty: bool = False) -> Money:
    cleaned = _number_text(text)
    if not cleaned:
        if allow_empty:
            return Money(0)
        raise ValidationError("error.price_invalid")
    if not _is_plain_number(cleaned):
        raise ValidationError("error.price_invalid")
    try:
        money = Money.from_rupees(cleaned)
    except (ValueError, TypeError) as exc:
        raise ValidationError("error.price_invalid") from exc
    if money.paisa < 0:
        raise ValidationError("error.price_invalid")
    return money


def parse_quantity(text: str, *, small_unit: bool = False, allow_empty: bool = False) -> Quantity:
    """small_unit=True: the number is whole grams / millilitres (for kg / litre items)."""
    cleaned = _number_text(text)
    if not cleaned:
        if allow_empty:
            return Quantity(0)
        raise ValidationError("error.quantity_invalid")
    if not _is_plain_number(cleaned):
        raise ValidationError("error.quantity_invalid")
    try:
        qty = Quantity.from_small_unit(cleaned) if small_unit else Quantity.from_decimal(cleaned)
    except (ValueError, TypeError) as exc:
        raise ValidationError("error.quantity_invalid") from exc
    if qty.milli < 0:
        raise ValidationError("error.quantity_invalid")
    return qty


def parse_tax_percent(text: str) -> int | None:
    """'15' -> 1500 basis points, '2.5' -> 250, '' -> None."""
    cleaned = _number_text(text)
    if not cleaned:
        return None
    if not _is_plain_number(cleaned):
        raise ValidationError("error.tax_invalid")
    try:
        basis_points = Decimal(cleaned) * 100
    except InvalidOperation as exc:
        raise ValidationError("error.tax_invalid") from exc
    if not basis_points.is_finite() or basis_points != basis_points.to_integral_value() or not 0 <= basis_points <= 10000:
        raise ValidationError("error.tax_invalid")
    return int(basis_points)


def format_tax_percent(basis_points: int | None) -> str:
    if basis_points is None:
        return ""
    whole, frac = divmod(basis_points, 100)
    return f"{whole}" + (f".{frac:02d}".rstrip("0") if frac else "")
