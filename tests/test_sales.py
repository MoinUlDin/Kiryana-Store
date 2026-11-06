import sqlite3
from decimal import Decimal

import pytest

from app.domain.cart import Cart
from app.domain.item import ItemInput
from app.domain.money import Money
from app.domain.pricing import ROUND_NONE, Discount
from app.domain.quantity import Quantity
from app.domain.sale import CheckoutInput, PaymentInput, SaleLineInput
from app.domain.user import ROLE_CASHIER, ROLE_OWNER, ROLE_SUPERADMIN, SYSTEM
from app.security.passwords import ValidationError
from app.services.sale_service import SaleService
from tests.helpers import make_services

R = Money.from_rupees
Q = Quantity.from_decimal
TODAY = "2026-11-05"


@pytest.fixture
def svc(tmp_path):
    s = make_services(tmp_path)
    admin = s.auth.create_user(SYSTEM, "admin", "Dev", ROLE_SUPERADMIN, "adminpass")
    s.owner = s.auth.create_user(admin, "owner", "Owner", ROLE_OWNER, "ownerpass")
    s.cashier = s.auth.create_user(s.owner, "ali", "Ali", ROLE_CASHIER, "alipass1")
    s.sales = SaleService(s.conn, s.audit, s.stock, s.sales_settings, today=lambda: TODAY)
    yield s
    s.conn.close()


def item(svc, code, name, unit="kg", sale=400, cost=300, stock=100, fraction=True):
    return svc.items.create(svc.owner, ItemInput(name_en=name, short_code=code, unit=unit, sale=R(sale), cost=R(cost),
                                                 allow_fraction=fraction), opening=Q(stock) if stock else None).item


def line(item_obj, qty, **kw):
    return SaleLineInput(qty=Q(qty), item_id=item_obj.id, **kw)


def pay(amount, method="cash"):
    return PaymentInput(method, R(amount))


def check(svc):
    assert svc.stock.check_invariants() == []


def test_simple_checkout_end_to_end(svc):
    rice, soap = item(svc, "RICE", "Rice", sale=400, cost=320), item(svc, "SOAP", "Soap", "piece", 60, 50, 20, False)
    order = svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, "2.5"), line(soap, 3)], [pay(1180)]))
    assert order.bill_no == 1 and order.business_date == TODAY and order.cashier_name == "Ali"
    assert order.subtotal == R(1180) and order.payable == R(1180) and order.status == "completed"
    assert [l.name_en for l in order.lines] == ["Rice", "Soap"]
    assert order.lines[0].qty == Q("2.5") and order.lines[0].total == R(1000) and order.lines[0].cost == R(320)   # cost snapshot
    assert [(p.method, p.amount) for p in order.payments] == [("cash", R(1180))]
    assert svc.items.get(rice.id).stock == Q("97.5") and svc.items.get(soap.id).stock == Q(17)
    assert [m.kind for m in svc.stock.movements(rice.id)][0] == "sale"
    check(svc)


def test_bill_numbers_are_sequential_and_gapless_even_after_a_failed_checkout(svc):
    rice = item(svc, "RICE", "Rice", stock=10)
    svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 1)], [pay(400)]))
    with pytest.raises(ValidationError):
        svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 50)], [pay(20000)]))    # more than in stock
    second = svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 1)], [pay(400)]))
    assert second.bill_no == 2                                                           # the failed attempt used no number
    assert [o.bill_no for o in svc.sales.list()] == [2, 1]
    assert svc.sales.get_by_bill_no(1).payable == R(400)


def test_selling_more_than_the_stock_is_refused_and_changes_nothing(svc):
    rice = item(svc, "RICE", "Rice", stock=5)
    with pytest.raises(ValidationError) as err:
        svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, "5.001")], [pay(2001)]))
    assert err.value.code == "error.sale_stock_short" and err.value.params["name"] == "Rice"
    assert err.value.params["available"] == "5" and err.value.params["item_id"] == rice.id
    assert svc.items.get(rice.id).stock == Q(5) and svc.sales.list() == []
    check(svc)


def test_zero_stock_items_cannot_be_sold(svc):
    empty = item(svc, "EMPTY", "Empty", stock=0)
    with pytest.raises(ValidationError) as err:
        svc.sales.checkout(svc.cashier, CheckoutInput([line(empty, 1)], [pay(400)]))
    assert err.value.code == "error.sale_stock_short" and err.value.params["available"] == "0"


def test_the_same_item_on_two_lines_counts_together_for_the_stock_check(svc):
    rice = item(svc, "RICE", "Rice", stock=5)
    with pytest.raises(ValidationError) as err:
        svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 3), line(rice, 3)], [pay(2400)]))
    assert err.value.code == "error.sale_stock_short"
    ok = svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 3), line(rice, 2)], [pay(2000)]))
    assert ok.payable == R(2000) and svc.items.get(rice.id).stock == Q(0)
    check(svc)


def test_a_late_failure_rolls_everything_back(svc):
    rice, soap = item(svc, "RICE", "Rice", stock=10), item(svc, "SOAP", "Soap", "piece", 60, 50, 1, False)
    svc.items.set_active(svc.owner, soap.id, False)               # the second line will fail after the first is prepared
    with pytest.raises(ValidationError):
        svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 2), line(soap, 1)], [pay(860)]))
    assert svc.items.get(rice.id).stock == Q(10) and svc.sales.list() == [] and svc.conn.in_transaction is False
    check(svc)


def test_amount_entry_charges_exactly_what_was_typed(svc):
    daal = item(svc, "DAAL", "Daal", sale=1000, stock=20)
    order = svc.sales.checkout(svc.cashier, CheckoutInput(
        [SaleLineInput(qty=Q(0), item_id=daal.id, mode="amount", amount=R(100))], [pay(100)]))
    assert order.lines[0].qty == Q("0.1") and order.lines[0].total == R(100) and order.lines[0].entry_mode == "amount"
    assert svc.items.get(daal.id).stock == Q("19.9")
    odd = item(svc, "ODD", "Odd", sale=330, stock=20)
    order = svc.sales.checkout(svc.cashier, CheckoutInput(
        [SaleLineInput(qty=Q(0), item_id=odd.id, mode="amount", amount=R(50))], [pay(50)]))
    assert order.lines[0].qty == Quantity(152) and order.payable == R(50)         # 151.515 g -> 152 g, bill still Rs 50
    check(svc)


def test_amount_entry_rules(svc):
    piece = item(svc, "EGG", "Egg", "piece", 30, 25, 50, False)
    for bad in (dict(item_id=piece.id, mode="amount", amount=R(60)),):           # amount entry only for fractional items
        with pytest.raises(ValidationError) as err:
            svc.sales.checkout(svc.cashier, CheckoutInput([SaleLineInput(qty=Q(0), **bad)], [pay(60)]))
        assert err.value.code == "error.fraction_not_allowed"
    kg = item(svc, "KG", "Kg item", stock=10)
    with pytest.raises(ValidationError):
        svc.sales.checkout(svc.cashier, CheckoutInput([SaleLineInput(qty=Q(0), item_id=kg.id, mode="amount")], []))
    with pytest.raises(ValidationError) as tiny:
        svc.sales.checkout(svc.cashier, CheckoutInput(
            [SaleLineInput(qty=Q(0), item_id=kg.id, mode="amount", amount=Money(1))], [pay("0.01")]))   # Rs 0.01 buys 0 g
    assert tiny.value.code == "error.quantity_invalid"


def test_discounts_split_across_lines_and_stored_exactly(svc):
    rice, soap = item(svc, "RICE", "Rice", sale=1000, stock=50), item(svc, "SOAP", "Soap", "piece", 500, 300, 50, False)
    order = svc.sales.checkout(svc.cashier, CheckoutInput(
        [line(rice, 1, discount=Discount.of_percent("10")), line(soap, 1)], [pay(1250)],
        bill_discount=Discount.of_amount(R(150))))
    assert order.subtotal == R(1500) and order.item_discount == R(100) and order.bill_discount == R(150)
    assert order.payable == R(1250)
    assert sum(l.total.paisa for l in order.lines) == order.payable.paisa                    # lines add up to the bill
    assert sum(l.bill_share.paisa for l in order.lines) == R(150).paisa
    for l in order.lines:
        assert l.total == l.gross - l.discount - l.bill_share
    check(svc)


def test_rounding_to_the_rupee_and_the_setting_to_turn_it_off(svc):
    tea = item(svc, "TEA", "Tea", "piece", "10.40", 8, 100, False)
    order = svc.sales.checkout(svc.cashier, CheckoutInput([line(tea, 1)], [pay(10)]))        # Rs 10.40 -> Rs 10
    assert order.payable == R(10) and order.rounding == R("-0.40")
    svc.sales_settings.set_rounding(ROUND_NONE)
    exact = svc.sales.checkout(svc.cashier, CheckoutInput([line(tea, 1)], [pay("10.40")]))
    assert exact.payable == R("10.40") and exact.rounding == Money(0)


def test_split_payments_and_payment_rules(svc):
    rice = item(svc, "RICE", "Rice", sale=400, stock=50)
    order = svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 5)], [pay(1000), pay(500, "card"), pay(500, "wallet")]))
    assert [(p.method, p.amount) for p in order.payments] == [("cash", R(1000)), ("card", R(500)), ("wallet", R(500))]
    def code(payments):
        with pytest.raises(ValidationError) as err:
            svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 5)], payments))
        return err.value.code
    assert code([pay(1999)]) == "error.payment_mismatch"
    assert code([pay(2001)]) == "error.payment_mismatch"
    assert code([]) == "error.payment_mismatch"
    assert code([pay(2000, "cheque")]) == "error.payment_invalid"
    assert code([pay(2000, "udhar")]) == "error.payment_invalid"        # credit sales arrive with customers in Phase 6
    assert code([pay(2100), PaymentInput("cash", R(-100))]) == "error.payment_invalid"
    assert len(svc.sales.list()) == 1 and svc.items.get(rice.id).stock == Q(45)


def test_a_free_bill_needs_no_payment(svc):
    rice = item(svc, "RICE", "Rice", stock=10)
    order = svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 1)], [], bill_discount=Discount.of_percent("100")))
    assert order.payable == Money(0) and order.payments == ()


def test_misc_items_have_no_stock_and_are_audited(svc):
    bag = SaleLineInput(qty=Q(2), misc_name="  Plastic bag ", misc_price=R(5))
    order = svc.sales.checkout(svc.cashier, CheckoutInput([bag], [pay(10)]))
    l = order.lines[0]
    assert l.is_misc and l.item_id is None and l.name_en == "Plastic bag" and l.total == R(10) and l.cost == Money(0)
    entry = svc.audit.search("sale.misc_item")[0]
    assert "Plastic bag" in entry["new_json"] and entry["username"] == "ali"
    for bad in (SaleLineInput(qty=Q(1), misc_name=" ", misc_price=R(5)), SaleLineInput(qty=Q(1), misc_name="x"),
                SaleLineInput(qty=Q(0), misc_name="x", misc_price=R(5))):
        with pytest.raises(ValidationError):
            svc.sales.checkout(svc.cashier, CheckoutInput([bad], [pay(5)]))


def test_inactive_items_and_fraction_rules_and_empty_cart(svc):
    egg = item(svc, "EGG", "Egg", "piece", 30, 25, 50, False)
    with pytest.raises(ValidationError) as frac:
        svc.sales.checkout(svc.cashier, CheckoutInput([line(egg, "1.5")], [pay(45)]))
    assert frac.value.code == "error.fraction_not_allowed"
    with pytest.raises(ValidationError) as empty:
        svc.sales.checkout(svc.cashier, CheckoutInput([], []))
    assert empty.value.code == "error.cart_empty"
    svc.items.set_active(svc.owner, egg.id, False)
    with pytest.raises(ValidationError) as off:
        svc.sales.checkout(svc.cashier, CheckoutInput([line(egg, 1)], [pay(30)]))
    assert off.value.code == "error.item_inactive"


def test_prices_come_from_the_database_not_from_the_screen(svc):
    rice = item(svc, "RICE", "Rice", sale=400, stock=10)
    svc.items.update(svc.owner, rice.id, ItemInput(name_en="Rice", short_code="RICE", unit="kg", sale=R(450),
                                                   cost=R(300), allow_fraction=True))
    with pytest.raises(ValidationError):
        svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 1)], [pay(400)]))        # a stale Rs 400 payment no longer matches
    assert svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 1)], [pay(450)])).payable == R(450)


def test_checkout_is_audited(svc):
    rice = item(svc, "RICE", "Rice", stock=10)
    svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 1)], [pay(400)]))
    entry = svc.audit.search("sale.checkout")[0]
    assert '"bill_no": 1' in entry["new_json"] and "40000" in entry["new_json"] and entry["username"] == "ali"


def test_the_database_itself_rejects_a_bill_that_does_not_add_up(svc):
    svc.conn.execute("INSERT INTO orders(bill_no, business_date, cashier_id, subtotal_paisa, payable_paisa) VALUES (1, ?, ?, 100, 100)",
                     (TODAY, svc.cashier.id))
    with pytest.raises(sqlite3.IntegrityError):
        svc.conn.execute("INSERT INTO orders(bill_no, business_date, cashier_id, subtotal_paisa, payable_paisa) VALUES (2, ?, ?, 100, 99)",
                         (TODAY, svc.cashier.id))
    with pytest.raises(sqlite3.IntegrityError):
        svc.conn.execute("INSERT INTO order_lines(order_id, item_id, is_misc, name_snapshot, unit_snapshot, qty_milli, unit_price_paisa, gross_paisa, line_total_paisa) "
                         "VALUES (1, NULL, 0, 'x', 'kg', 1, 1, 1, 1)")                       # a catalog line must name an item


def test_items_that_were_sold_can_never_be_deleted(svc):
    rice = item(svc, "RICE", "Rice", stock=10)
    svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 1)], [pay(400)]))
    assert not svc.items.can_delete(rice.id)
    with pytest.raises(ValidationError):
        svc.items.delete(svc.owner, rice.id)


def test_expiry_batches_are_sold_earliest_first(svc):
    from app.domain.purchase import PurchaseInput, PurchaseLineInput
    from app.services.purchase_service import PurchaseService
    rice = item(svc, "RICE", "Rice", stock=0)
    PurchaseService(svc.conn, svc.audit, svc.stock, today=lambda: TODAY).create(svc.owner, PurchaseInput([
        PurchaseLineInput(rice.id, Q(10), R(300), expiry_date="2027-06-01"),
        PurchaseLineInput(rice.id, Q(10), R(310), expiry_date="2026-12-01")]))
    svc.sales.checkout(svc.cashier, CheckoutInput([line(rice, 12)], [pay(4800)]))
    left = {r["expiry_date"]: r["qty_left_milli"] for r in svc.conn.execute("SELECT * FROM item_batches")}
    assert left == {"2026-12-01": 0, "2027-06-01": 8000}
    check(svc)


# ---------------- hold / resume ----------------
def test_hold_resume_and_discard(svc):
    rice, soap = item(svc, "RICE", "Rice", stock=20), item(svc, "SOAP", "Soap", "piece", 60, 50, 20, False)
    cart = Cart()
    cart.add_item(rice, Q(2))
    cart.add_item(soap, Q(3))
    cart.add_misc("Bag", R(5), Q(1))
    cart.bill_discount = Discount.of_amount(R(10))
    held_id = svc.held.hold(svc.cashier, cart, "Bill at 10:30")
    listed = svc.held.list()
    assert [(h["id"], h["label"], h["line_count"], h["cashier_name"]) for h in listed] == [(held_id, "Bill at 10:30", 3, "Ali")]
    assert svc.items.get(rice.id).stock == Q(20)                                      # holding reserves nothing
    resumed, dropped = svc.held.resume(svc.owner, held_id)                            # another user can pick it up
    assert dropped == [] and len(resumed.lines) == 3 and resumed.bill_discount == Discount.of_amount(R(10))
    assert svc.held.list() == []
    with pytest.raises(ValueError):
        svc.held.resume(svc.cashier, held_id)                                         # gone once resumed
    second = svc.held.hold(svc.cashier, cart, "again")
    svc.held.discard(svc.cashier, second)
    assert svc.held.list() == []
    actions = {r["action"] for r in svc.audit.search("bill.")}
    assert {"bill.hold", "bill.resume", "bill.discard"} <= actions


def test_hold_refuses_an_empty_cart_and_resume_reports_removed_items(svc):
    with pytest.raises(ValidationError):
        svc.held.hold(svc.cashier, Cart(), "empty")
    egg = item(svc, "EGG", "Egg", "piece", 30, 25, 50, False)
    cart = Cart()
    cart.add_item(egg, Q(2))
    held_id = svc.held.hold(svc.cashier, cart, "x")
    svc.items.set_active(svc.owner, egg.id, False)                                    # deactivated while the bill was held
    resumed, dropped = svc.held.resume(svc.cashier, held_id)
    assert dropped == ["Egg"] and resumed.is_empty


def test_held_bills_survive_a_restart(tmp_path):
    from app.db.connection import connect
    from app.services.container import build_services
    from app.db.migrator import migrate
    first = make_services(tmp_path)
    admin = first.auth.create_user(SYSTEM, "admin", "Dev", ROLE_SUPERADMIN, "adminpass")
    egg = first.items.create(admin, ItemInput(name_en="Egg", short_code="EGG", unit="piece", sale=R(30), allow_fraction=False), opening=Q(10)).item
    cart = Cart()
    cart.add_item(egg, Q(2))
    first.held.hold(admin, cart, "kept")
    first.conn.close()
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    again = build_services(conn)
    assert [h["label"] for h in again.held.list()] == ["kept"]
    conn.close()


# ---------------- settings ----------------
def test_sales_settings(svc):
    s = svc.sales_settings
    assert s.rounding() == "rupee" and s.discount_limit_percent() == Decimal(10)
    s.set_discount_limit_percent("15")
    assert s.discount_limit_percent() == Decimal(15)
    for bad in ("-1", "101", "abc"):
        with pytest.raises(Exception):
            s.set_discount_limit_percent(bad)
    with pytest.raises(ValueError):
        s.set_rounding("banker")
    svc.settings.set("sales.cashier_discount_limit_pct", "garbage")
    assert s.discount_limit_percent() == Decimal(10)                                  # a damaged setting falls back to the default
