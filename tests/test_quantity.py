import pytest

from app.domain.money import Money
from app.domain.quantity import Quantity


def test_parse_and_format():
    assert Quantity.from_decimal("2.5").milli == 2500
    assert Quantity.from_decimal(5).milli == 5000
    assert Quantity.from_decimal("0.020").milli == 20
    assert Quantity.from_decimal("2.5").format() == "2.5"
    assert Quantity.from_decimal(5).format() == "5"
    assert Quantity(100).format() == "0.1"
    assert Quantity(-1500).format() == "-1.5"


def test_rejects_floats_and_extra_decimals():
    with pytest.raises(TypeError):
        Quantity.from_decimal(2.5)
    with pytest.raises(ValueError):
        Quantity.from_decimal("0.0001")
    with pytest.raises(ValueError):
        Quantity.from_decimal("abc")


def test_arithmetic():
    assert Quantity(2500) + Quantity(500) == Quantity(3000)
    assert Quantity(2500) - Quantity(500) == Quantity(2000)
    assert Quantity(5000).is_whole and not Quantity(2500).is_whole


def test_price_for_quantity():
    price_per_kg = Money.from_rupees(1000)
    assert price_per_kg.for_quantity(Quantity.from_decimal("2.5")) == Money.from_rupees(2500)
    assert price_per_kg.for_quantity(Quantity(20)) == Money.from_rupees(20)  # 20 g


def test_amount_entry_exact_case():
    # Rs 100 of daal at Rs 1000/kg -> 0.100 kg
    qty = Quantity.for_amount(Money.from_rupees(100), Money.from_rupees(1000))
    assert qty == Quantity(100)


def test_amount_entry_uneven_case_rounds_quantity_only():
    # Rs 50 at Rs 330/kg = 151.515 g -> rounded to 152 g
    amount, price = Money.from_rupees(50), Money.from_rupees(330)
    qty = Quantity.for_amount(amount, price)
    assert qty == Quantity(152)
    # The caller keeps `amount` as the line total (Rs 50.00); recomputing would
    # give Rs 50.16, which is why the line stores entry_mode='amount'.
    assert price.for_quantity(qty) == Money(5016)


def test_amount_entry_guards():
    with pytest.raises(ValueError):
        Quantity.for_amount(Money(100), Money(0))
    with pytest.raises(ValueError):
        Quantity.for_amount(Money(-1), Money(100))
