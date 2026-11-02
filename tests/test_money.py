from decimal import Decimal

import pytest

from app.domain.money import Money, div_round_half_up


def test_from_rupees_variants():
    assert Money.from_rupees("12.50").paisa == 1250
    assert Money.from_rupees(10).paisa == 1000
    assert Money.from_rupees(Decimal("0.05")).paisa == 5


def test_floats_are_rejected():
    with pytest.raises(TypeError):
        Money.from_rupees(12.5)
    with pytest.raises(TypeError):
        Money(1.5)  # type: ignore[arg-type]


def test_too_many_decimals_rejected():
    with pytest.raises(ValueError):
        Money.from_rupees("1.005")


def test_garbage_rejected():
    for bad in ("abc", "", "NaN", "Infinity"):
        with pytest.raises(ValueError):
            Money.from_rupees(bad)


def test_arithmetic_and_ordering():
    a, b = Money(500), Money(250)
    assert a + b == Money(750)
    assert a - b == Money(250)
    assert -a == Money(-500)
    assert b * 3 == Money(750) and 3 * b == Money(750)
    assert b < a


def test_half_up_rounding_helper():
    assert div_round_half_up(5, 10) == 1
    assert div_round_half_up(4, 10) == 0
    assert div_round_half_up(-5, 10) == -1
    assert div_round_half_up(15, -10) == -2


def test_percent_rounds_half_up():
    assert Money.from_rupees("100").percent(10) == Money.from_rupees("10")
    assert Money(1050).percent("10") == Money(105)
    assert Money(5).percent("10") == Money(1)        # 0.5 paisa rounds up
    assert Money(1000).percent("2.5") == Money(25)
    with pytest.raises(TypeError):
        Money(1000).percent(2.5)  # type: ignore[arg-type]


def test_round_to_rupee():
    assert Money(1049).round_to_rupee() == Money(1000)
    assert Money(1050).round_to_rupee() == Money(1100)


def test_format():
    assert Money(123456).format() == "1,234.56"
    assert Money(5).format() == "0.05"
    assert Money(-250).format() == "-2.50"
    assert str(Money(100000000)) == "1,000,000.00"
