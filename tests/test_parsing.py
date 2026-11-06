import pytest

from app.domain.money import Money
from app.domain.parsing import format_tax_percent, parse_money, parse_quantity, parse_tax_percent
from app.domain.quantity import Quantity
from app.security.passwords import ValidationError


def test_money_variants():
    assert parse_money("1,250.50") == Money(125050)
    assert parse_money(" ٣٥٠ ") == Money(35000)            # Arabic-Indic digits
    assert parse_money("۱۲٫۵") == Money(1250)               # Eastern digits with Arabic decimal separator
    assert parse_money("", allow_empty=True) == Money(0)
    for bad in ("", "abc", "-5", "1.005", "1e3"):
        with pytest.raises(ValidationError) as err:
            parse_money(bad)
        assert err.value.code == "error.price_invalid"


def test_quantity_variants():
    assert parse_quantity("2.5") == Quantity(2500)
    assert parse_quantity("250", small_unit=True) == Quantity(250)       # 250 g
    assert parse_quantity("", allow_empty=True) == Quantity(0)
    for bad, small in (("", False), ("x", False), ("-1", False), ("0.0001", False), ("0.5", True), ("1e2", False), ("NaN", False)):
        with pytest.raises(ValidationError) as err:
            parse_quantity(bad, small_unit=small)
        assert err.value.code == "error.quantity_invalid"


def test_tax():
    assert parse_tax_percent("") is None
    assert parse_tax_percent("15") == 1500 and parse_tax_percent("2.5") == 250 and parse_tax_percent("0") == 0
    for bad in ("101", "-1", "x", "1.005", "1e1"):
        with pytest.raises(ValidationError):
            parse_tax_percent(bad)
    assert format_tax_percent(1500) == "15" and format_tax_percent(250) == "2.5" and format_tax_percent(None) == ""
    assert format_tax_percent(205) == "2.05"
