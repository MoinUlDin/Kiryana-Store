import random
from decimal import Decimal

import pytest

from app.domain.cart import Cart
from app.domain.item import Item
from app.domain.money import Money
from app.domain.pricing import (
    ROUND_NONE, ROUND_RUPEE, Discount, allocate, compute_totals, discount_amount, line_gross,
)
from app.domain.quantity import Quantity
from app.security.passwords import ValidationError

R = Money.from_rupees
Q = Quantity.from_decimal


def make_item(item_id=1, name="Rice", unit="kg", sale=400, active=True, fraction=True, name_ur=None):
    return Item(item_id, name, name_ur, f"C{item_id}", None, None, None, unit, fraction, R(0), R(sale), None,
                Q(100), Q(0), active)


# ---------------- discounts ----------------
def test_discount_validation():
    assert Discount.of_percent("10").percent == Decimal("10")
    assert Discount.of_amount(R(5)).amount == R(5)
    for bad in ("-1", "100.01", "abc", "1.005"):
        with pytest.raises((ValidationError, Exception)):
            Discount.of_percent(bad)
    with pytest.raises(ValidationError):
        Discount.of_amount(Money(-1))
    with pytest.raises(ValueError):
        Discount()                                  # neither
    with pytest.raises(ValueError):
        Discount(percent=Decimal(1), amount=R(1))   # both


def test_discount_amounts():
    assert discount_amount(R(200), Discount.of_percent("10")) == R(20)
    assert discount_amount(R(200), Discount.of_amount(R(35))) == R(35)
    assert discount_amount(R(200), None) == Money(0)
    assert discount_amount(Money(5), Discount.of_percent("10")) == Money(1)      # 0.5 paisa rounds half up
    with pytest.raises(ValidationError):
        discount_amount(R(10), Discount.of_amount(R(11)))                         # more than the line is worth


# ---------------- gross ----------------
def test_line_gross_modes():
    assert line_gross(R(1000), Q("2.5"), "qty", None) == R(2500)
    assert line_gross(R(1000), Q("0.1"), "amount", R(100)) == R(100)
    assert line_gross(R(330), Quantity(152), "amount", R(50)) == R(50)           # typed amount is kept, not recomputed
    assert line_gross(R(330), Quantity(152), "qty", None) == Money(5016)


# ---------------- allocation ----------------
def test_allocate_exact_and_largest_remainder():
    assert allocate(100, [1, 1, 1]) == [34, 33, 33]
    assert allocate(10, [3, 3, 4]) == [3, 3, 4]
    assert allocate(0, [5, 5]) == [0, 0]
    assert allocate(0, [0, 0]) == [0, 0] and allocate(5, []) == []
    with pytest.raises(ValueError):
        allocate(7, [0, 0])


def test_allocate_always_sums_to_total():
    rnd = random.Random(1)
    for _ in range(500):
        weights = [rnd.randint(0, 100000) for _ in range(rnd.randint(1, 12))]
        if sum(weights) == 0:
            continue
        total = rnd.randint(0, sum(weights))
        shares = allocate(total, weights)
        assert sum(shares) == total and all(s >= 0 for s in shares)


def test_allocate_never_exceeds_the_line_when_total_fits():
    rnd = random.Random(2)
    for _ in range(500):
        weights = [rnd.randint(1, 50000) for _ in range(rnd.randint(1, 10))]
        total = rnd.randint(0, sum(weights))
        shares = allocate(total, weights)
        assert all(share <= weight for share, weight in zip(shares, weights))


# ---------------- totals ----------------
def test_simple_totals_with_rupee_rounding():
    t = compute_totals([R("120.40"), R("79.30")], [None, None], None, ROUND_RUPEE)
    assert t.subtotal == R("199.70") and t.payable == R(200) and t.rounding == R("0.30")
    t = compute_totals([R("120.40"), R("79.10")], [None, None], None, ROUND_RUPEE)
    assert t.subtotal == R("199.50") and t.payable == R(200) and t.rounding == R("0.50")   # a half rounds up
    t = compute_totals([R("120.40"), R("79.00")], [None, None], None, ROUND_RUPEE)
    assert t.subtotal == R("199.40") and t.payable == R(199) and t.rounding == R("-0.40")  # rounding can go down too
    assert t.payable == t.subtotal + t.rounding - t.total_discount


def test_rounding_off():
    t = compute_totals([R("10.50")], [None], None, ROUND_NONE)
    assert t.payable == R("10.50") and t.rounding == Money(0)


def test_item_and_bill_discounts():
    grosses = [R(1000), R(500)]
    t = compute_totals(grosses, [Discount.of_percent("10"), None], Discount.of_amount(R(150)), ROUND_NONE)
    assert t.item_discount == R(100) and t.bill_discount == R(150)
    assert t.subtotal == R(1500) and t.payable == R(1250)
    assert [l.discount for l in t.lines] == [R(100), Money(0)]
    assert sum(l.bill_share.paisa for l in t.lines) == R(150).paisa           # shares add up exactly
    assert sum(l.net.paisa for l in t.lines) == t.payable.paisa               # and so do the line totals
    assert t.total_discount == R(250) and t.discount_percent.quantize(Decimal("0.01")) == Decimal("16.67")


def test_bill_discount_percent_is_taken_after_item_discounts():
    t = compute_totals([R(1000)], [Discount.of_amount(R(200))], Discount.of_percent("10"), ROUND_NONE)
    assert t.bill_discount == R(80) and t.payable == R(720)


def test_invalid_discounts_in_totals():
    with pytest.raises(ValidationError):
        compute_totals([R(100)], [Discount.of_amount(R(101))], None)
    with pytest.raises(ValidationError):
        compute_totals([R(100)], [None], Discount.of_amount(R(101)))


def test_hundred_percent_discount_gives_a_zero_bill():
    t = compute_totals([R("33.33"), R("10")], [None, None], Discount.of_percent("100"), ROUND_RUPEE)
    assert t.payable == Money(0) and sum(l.net.paisa for l in t.lines) == 0


def test_empty_cart_totals():
    t = compute_totals([], [], None)
    assert t.payable == Money(0) and t.lines == () and t.discount_percent == Decimal(0)


def test_totals_invariants_hold_for_random_carts():
    rnd = random.Random(3)
    for _ in range(300):
        n = rnd.randint(1, 8)
        grosses = [Money(rnd.randint(0, 500000)) for _ in range(n)]
        discounts = [rnd.choice([None, Discount.of_percent(str(rnd.randint(0, 100))),
                                 Discount.of_amount(Money(rnd.randint(0, g.paisa)))]) for g in grosses]
        bill = rnd.choice([None, Discount.of_percent(str(rnd.randint(0, 100)))])
        mode = rnd.choice([ROUND_RUPEE, ROUND_NONE])
        t = compute_totals(grosses, discounts, bill, mode)
        assert t.payable.paisa == t.subtotal.paisa - t.item_discount.paisa - t.bill_discount.paisa + t.rounding.paisa
        assert sum(l.net.paisa for l in t.lines) == t.subtotal.paisa - t.item_discount.paisa - t.bill_discount.paisa
        assert all(l.net.paisa >= 0 for l in t.lines)
        if mode == ROUND_RUPEE:
            assert t.payable.paisa % 100 == 0 and abs(t.rounding.paisa) <= 50


# ---------------- cart ----------------
def test_scanning_the_same_item_adds_to_its_line():
    cart, soap = Cart(), make_item(2, "Soap", unit="piece", sale=60, fraction=False)
    cart.add_item(soap, Q(1))
    cart.add_item(soap, Q(1))
    cart.add_item(make_item(3, "Tea", unit="piece", sale=10, fraction=False), Q(1))
    assert len(cart.lines) == 2 and cart.lines[0].qty == Q(2) and cart.item_qty(2) == Q(2)
    assert cart.totals().payable == R(130)


def test_amount_lines_do_not_merge_and_keep_their_amount():
    cart, daal = Cart(), make_item(1, "Daal", sale=1000)
    cart.add_item(daal, Q("0.1"), "amount", R(100))
    cart.add_item(daal, Q("0.2"), "amount", R(200))
    cart.add_item(daal, Q(1))
    assert len(cart.lines) == 3 and cart.totals(ROUND_NONE).payable == R(1300)
    assert cart.item_qty(1) == Q("1.3")


def test_edit_remove_and_discounts():
    cart = Cart()
    cart.add_item(make_item(1, sale=400), Q(2))
    cart.add_misc("Plastic bag", R(5), Q(3))
    assert cart.lines[1].is_misc and cart.totals(ROUND_NONE).payable == R(815)
    cart.set_line_discount(0, Discount.of_percent("10"))
    cart.bill_discount = Discount.of_amount(R(15))
    assert cart.totals(ROUND_NONE).payable == R(720)     # (800 - 10% + 15) - 15
    cart.set_quantity(0, Q(1))
    assert cart.totals(ROUND_NONE).payable == R(360)     # (400 - 10% + 15) - 15
    cart.remove(1)
    assert len(cart.lines) == 1
    cart.set_quantity(0, Q("0.5"), "amount", R(100))     # editing into amount mode
    assert cart.lines[0].mode == "amount" and cart.lines[0].gross == R(100)
    cart.set_quantity(0, Q(2))                           # and back to plain quantity: the amount is forgotten
    assert cart.lines[0].mode == "qty" and cart.lines[0].amount is None
    cart.clear()
    assert cart.is_empty and cart.bill_discount is None


def test_hold_and_resume_round_trip_with_price_changes_and_dropped_items():
    cart = Cart()
    rice, daal, gone = make_item(1, "Rice", sale=400), make_item(2, "Daal", sale=1000), make_item(3, "Old")
    cart.add_item(rice, Q(2))
    cart.add_item(daal, Q("0.1"), "amount", R(100))
    cart.add_item(gone, Q(1))
    cart.add_misc("Bag", R(5), Q(2))
    cart.set_line_discount(0, Discount.of_percent("5"))
    cart.bill_discount = Discount.of_amount(R(10))
    import json
    data = json.loads(json.dumps(cart.to_dict()))                       # really goes through JSON
    new_rice = make_item(1, "Rice", sale=420)
    new_daal = make_item(2, "Daal", sale=1250)                          # prices changed while the bill was held
    items = {1: new_rice, 2: new_daal, 3: make_item(3, "Old", active=False)}
    resumed, dropped = Cart.from_dict(data, items.get)
    assert dropped == ["Old"] and len(resumed.lines) == 3
    assert resumed.lines[0].unit_price == R(420) and resumed.lines[0].discount == Discount.of_percent("5")
    assert resumed.lines[1].gross == R(100) and resumed.lines[1].qty == Quantity(80)    # Rs 100 now buys 80 g
    assert resumed.lines[2].is_misc and resumed.lines[2].unit_price == R(5)
    assert resumed.bill_discount == Discount.of_amount(R(10))
    gone, _ = Cart.from_dict(data, lambda _i: None)
    assert [l.is_misc for l in gone.lines] == [True]                    # only the Misc line survives when nothing exists


def test_discounts_that_no_longer_fit_are_dropped_not_left_to_break_the_bill():
    cart = Cart()
    cart.add_item(make_item(1, sale=400), Q(2))
    cart.add_misc("Bag", R(5), Q(2))
    cart.set_line_discount(0, Discount.of_amount(R(500)))        # fine on Rs 800
    cart.set_line_discount(1, Discount.of_percent("50"))
    cart.bill_discount = Discount.of_amount(R(300))
    assert cart.prune_invalid_discounts() is False
    cart.set_quantity(0, Q(1))                                    # the line is now worth only Rs 400
    assert cart.prune_invalid_discounts() is True
    assert cart.lines[0].discount is None and cart.lines[1].discount == Discount.of_percent("50")
    cart.totals()                                                 # and the bill computes again
    cart.bill_discount = Discount.of_amount(R(5000))
    assert cart.prune_invalid_discounts() is True and cart.bill_discount is None
