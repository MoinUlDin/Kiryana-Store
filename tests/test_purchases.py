import pytest

from app.domain.item import ItemInput
from app.domain.money import Money
from app.domain.purchase import PurchaseInput, PurchaseLineInput
from app.domain.quantity import Quantity
from app.domain.user import ROLE_OWNER, ROLE_SUPERADMIN, SYSTEM
from app.security.passwords import ValidationError
from app.services.purchase_service import PurchaseService, weighted_average_cost
from tests.helpers import make_services

R = Money.from_rupees
Q = Quantity.from_decimal
TODAY = "2026-11-05"


@pytest.fixture
def svc(tmp_path):
    s = make_services(tmp_path)
    admin = s.auth.create_user(SYSTEM, "admin", "Dev", ROLE_SUPERADMIN, "adminpass")
    s.owner = s.auth.create_user(admin, "owner", "Owner", ROLE_OWNER, "ownerpass")
    s.purchases = PurchaseService(s.conn, s.audit, s.stock, today=lambda: TODAY)   # fixed "today" for the tests
    s.supplier = s.suppliers.add(s.owner, "Ali Traders", "0300")
    yield s
    s.conn.close()


def item(svc, code="RICE", name="Rice", unit="kg", sale=400, cost=0, fraction=True):
    return svc.items.create(svc.owner, ItemInput(name_en=name, short_code=code, unit=unit, sale=R(sale),
                                                 cost=R(cost), allow_fraction=fraction)).item


def line(item_obj, qty, unit_cost=None, total=None, expiry=None, new_sale=None):
    return PurchaseLineInput(item_obj.id, Q(qty), R(unit_cost) if unit_cost is not None else None,
                             R(total) if total is not None else None, expiry, new_sale)


def healthy(svc):
    assert svc.stock.check_invariants() == []


def test_weighted_average_math():
    # 10 kg at Rs 300 + 5 kg at Rs 330 = (3000 + 1650) / 15 = Rs 310
    assert weighted_average_cost(Q(10), R(300), Q(5), R(330)) == R(310)
    assert weighted_average_cost(Q(0), R(999), Q(5), R(330)) == R(330)        # no stock: new cost wins
    assert weighted_average_cost(Q(1), Money(1), Q(1), Money(2)) == Money(2)  # 1.5 paisa rounds up (half-up)


def test_first_purchase_sets_cost_stock_batch_and_history(svc):
    rice = item(svc)
    result = svc.purchases.create(svc.owner, PurchaseInput([line(rice, 10, unit_cost=300)], svc.supplier.id, "INV-1"))
    assert result.total == R(3000) and result.warnings == ()
    after = svc.items.get(rice.id)
    assert after.stock == Q(10) and after.cost == R(300)
    assert [m.kind for m in svc.stock.movements(rice.id)] == ["purchase"]
    batch = svc.conn.execute("SELECT * FROM item_batches WHERE item_id = ?", (rice.id,)).fetchone()
    line_row = svc.conn.execute("SELECT * FROM purchase_lines").fetchone()
    assert batch["source"] == "purchase" and batch["purchase_line_id"] == line_row["id"] and line_row["batch_id"] == batch["id"]
    healthy(svc)


def test_second_purchase_averages_the_cost(svc):
    rice = item(svc)
    svc.purchases.create(svc.owner, PurchaseInput([line(rice, 10, unit_cost=300)]))
    svc.purchases.create(svc.owner, PurchaseInput([line(rice, 5, unit_cost=330)]))
    after = svc.items.get(rice.id)
    assert after.stock == Q(15) and after.cost == R(310)
    _purchase, lines = svc.purchases.get(2)
    assert lines[0].avg_before == R(300) and lines[0].avg_after == R(310)
    healthy(svc)


def test_cost_from_the_invoice_line_total(svc):
    rice = item(svc)
    svc.purchases.create(svc.owner, PurchaseInput([line(rice, "2.5", total=800)]))     # Rs 800 for 2.5 kg
    after = svc.items.get(rice.id)
    assert after.cost == R(320)
    uneven = item(svc, code="DAAL", name="Daal")
    result = svc.purchases.create(svc.owner, PurchaseInput([line(uneven, 3, total=1000)]))   # Rs 333.333.. per kg
    assert svc.items.get(uneven.id).cost == Money(33333)
    assert result.total == R(1000)                                                      # the invoice total stays exact


def test_totals_payment_and_due(svc):
    a, b = item(svc), item(svc, code="SUG", name="Sugar")
    result = svc.purchases.create(svc.owner, PurchaseInput(
        [line(a, 10, unit_cost=300), line(b, 4, unit_cost=150)], svc.supplier.id, "INV-2", paid=R(2000), paid_method="cash"))
    assert result.total == R(3600)
    purchase, lines = svc.purchases.get(result.purchase_id)
    assert purchase.paid == R(2000) and purchase.due == R(1600) and purchase.paid_method == "cash" and len(lines) == 2
    assert purchase.supplier_name == "Ali Traders" and purchase.created_by_name == "owner"


def test_payment_rules(svc):
    rice = item(svc)
    base = [line(rice, 1, unit_cost=300)]
    with pytest.raises(ValidationError) as e1:
        svc.purchases.create(svc.owner, PurchaseInput(base, paid=R(301), paid_method="cash"))
    assert e1.value.code == "error.paid_exceeds_total"
    with pytest.raises(ValidationError) as e2:
        svc.purchases.create(svc.owner, PurchaseInput(base, paid=R(100)))             # paid but no method
    assert e2.value.code == "error.pay_method_required"
    ok = svc.purchases.create(svc.owner, PurchaseInput(base, paid=R(0), paid_method="card"))   # method ignored when nothing paid
    assert svc.purchases.get(ok.purchase_id)[0].paid_method is None


def test_duplicate_invoice_is_refused_for_the_same_supplier_only(svc):
    rice = item(svc)
    data = PurchaseInput([line(rice, 1, unit_cost=300)], svc.supplier.id, "A-100")
    svc.purchases.create(svc.owner, data)
    with pytest.raises(ValidationError) as err:
        svc.purchases.create(svc.owner, data)
    assert err.value.code == "error.purchase_duplicate"
    assert svc.items.get(rice.id).stock == Q(1)                       # the refused one changed nothing
    other = svc.suppliers.add(svc.owner, "Other Co")
    svc.purchases.create(svc.owner, PurchaseInput([line(rice, 1, unit_cost=300)], other.id, "A-100"))   # same number, other supplier
    svc.purchases.create(svc.owner, PurchaseInput([line(rice, 1, unit_cost=300)]))                      # no supplier / invoice: fine
    svc.purchases.create(svc.owner, PurchaseInput([line(rice, 1, unit_cost=300)]))
    healthy(svc)


def test_validation(svc):
    rice, egg = item(svc), item(svc, code="EGG", name="Egg", unit="piece", fraction=False)
    def code_of(data):
        with pytest.raises(ValidationError) as err:
            svc.purchases.create(svc.owner, data)
        return err.value.code
    assert code_of(PurchaseInput([])) == "error.purchase_empty"
    assert code_of(PurchaseInput([line(rice, 0, unit_cost=300)])) == "error.quantity_invalid"
    assert code_of(PurchaseInput([line(egg, "2.5", unit_cost=30)])) == "error.fraction_not_allowed"
    assert code_of(PurchaseInput([line(rice, 1, unit_cost=300)], purchase_date="2026-11-06")) == "error.date_future"
    assert code_of(PurchaseInput([line(rice, 1, unit_cost=300)], purchase_date="05/11/2026")) == "error.date_invalid"
    assert code_of(PurchaseInput([line(rice, 1, unit_cost=300, expiry="2026-11-01")])) == "error.expiry_invalid"
    assert code_of(PurchaseInput([line(rice, 1, unit_cost=300, expiry="soon")])) == "error.expiry_invalid"
    svc.items.set_active(svc.owner, rice.id, False)
    assert code_of(PurchaseInput([line(rice, 1, unit_cost=300)])) == "error.item_inactive"
    with pytest.raises(ValueError):
        svc.purchases.create(svc.owner, PurchaseInput([line(egg, 1)]))                     # neither cost given
    with pytest.raises(ValueError):
        svc.purchases.create(svc.owner, PurchaseInput([line(egg, 1, unit_cost=30, total=30)]))   # both given


def test_a_bad_line_rolls_back_the_whole_purchase(svc):
    good, egg = item(svc), item(svc, code="EGG", name="Egg", unit="piece", fraction=False)
    with pytest.raises(ValidationError):
        svc.purchases.create(svc.owner, PurchaseInput([line(good, 10, unit_cost=300), line(egg, "1.5", unit_cost=30)]))
    assert svc.items.get(good.id).stock == Q(0) and svc.purchases.search() == []
    assert svc.conn.in_transaction is False
    healthy(svc)


def test_same_item_twice_in_one_purchase(svc):
    rice = item(svc)
    svc.purchases.create(svc.owner, PurchaseInput([line(rice, 10, unit_cost=300, expiry="2027-01-01"),
                                                   line(rice, 10, unit_cost=320, expiry="2026-12-01")]))
    after = svc.items.get(rice.id)
    assert after.stock == Q(20) and after.cost == R(310)
    assert svc.conn.execute("SELECT COUNT(*) FROM item_batches").fetchone()[0] == 2
    used = svc.stock.consume(svc.owner, rice.id, Q(10), "sale")
    assert used[0].cost == R(320)          # the batch expiring first is sold first
    healthy(svc)


def test_warning_when_average_cost_exceeds_sale_price(svc):
    rice = item(svc, sale=400)
    result = svc.purchases.create(svc.owner, PurchaseInput([line(rice, 10, unit_cost=450)]))
    assert len(result.warnings) == 1
    w = result.warnings[0]
    assert (w.kind, w.item_id, w.avg_cost, w.sale) == ("cost_above_sale", rice.id, R(450), R(400))
    assert svc.items.get(rice.id).stock == Q(10)                  # saved anyway: a warning, not a block


def test_updating_sale_price_during_purchase_clears_the_warning_and_is_audited(svc):
    rice = item(svc, sale=400)
    result = svc.purchases.create(svc.owner, PurchaseInput([line(rice, 10, unit_cost=450, new_sale=R(500))]))
    assert result.warnings == () and svc.items.get(rice.id).sale == R(500)
    change = svc.audit.search("item.price_change")[0]
    assert "purchase #" in change["reason"] and "50000" in change["new_json"] and "40000" in change["old_json"]


def test_purchase_is_audited(svc):
    rice = item(svc)
    svc.purchases.create(svc.owner, PurchaseInput([line(rice, 10, unit_cost=300)], svc.supplier.id, "INV-9"))
    entry = svc.audit.search("purchase.create")[0]
    assert "INV-9" in entry["new_json"] and "300000" in entry["new_json"] and entry["username"] == "owner"


def test_search_and_filters(svc):
    rice = item(svc)
    other = svc.suppliers.add(svc.owner, "Zed Co")
    svc.purchases.create(svc.owner, PurchaseInput([line(rice, 1, unit_cost=300)], svc.supplier.id, "A-1", purchase_date="2026-10-01"))
    svc.purchases.create(svc.owner, PurchaseInput([line(rice, 1, unit_cost=300)], other.id, "B-2", purchase_date="2026-11-01"))
    assert [p.invoice_no for p in svc.purchases.search()] == ["B-2", "A-1"]                 # newest first
    assert [p.invoice_no for p in svc.purchases.search(date_from="2026-10-15")] == ["B-2"]
    assert [p.invoice_no for p in svc.purchases.search(date_to="2026-10-15")] == ["A-1"]
    assert [p.invoice_no for p in svc.purchases.search(supplier_id=other.id)] == ["B-2"]
    assert [p.invoice_no for p in svc.purchases.search(text="ali")] == ["A-1"]               # supplier name
    assert [p.invoice_no for p in svc.purchases.search(text="b-2")] == ["B-2"]               # invoice number
    assert svc.purchases.search(text="%") == []
    assert svc.purchases.get(999) is None


# ---------------- suppliers ----------------
def test_supplier_crud(svc):
    s = svc.suppliers.add(svc.owner, " Khan & Sons ", "0301", None, "cash only")
    assert s.name == "Khan & Sons" and s.phone == "0301" and s.address is None
    with pytest.raises(ValidationError) as dup:
        svc.suppliers.add(svc.owner, "khan & sons")
    assert dup.value.code == "error.list_exists"
    with pytest.raises(ValidationError):
        svc.suppliers.add(svc.owner, "  ")
    svc.suppliers.update(svc.owner, s.id, "Khan Brothers", "0302")
    assert svc.suppliers.get(s.id).name == "Khan Brothers"
    svc.suppliers.set_active(svc.owner, s.id, False)
    assert s.id not in [x.id for x in svc.suppliers.list()] and s.id in [x.id for x in svc.suppliers.list(True)]


# ---------------- alerts ----------------
def test_expiry_alerts_and_settings(svc):
    from app.services.alert_service import AlertService
    alerts = AlertService(svc.conn, svc.settings, today=lambda: TODAY)
    rice, daal, oil = item(svc), item(svc, code="DAAL", name="Daal"), item(svc, code="OIL", name="Oil", unit="litre")
    svc.purchases.create(svc.owner, PurchaseInput([
        line(rice, 10, unit_cost=300, expiry="2026-11-20"),    # 15 days away
        line(daal, 5, unit_cost=200, expiry="2026-11-05"),     # today: not expired yet
        line(oil, 8, unit_cost=500, expiry="2027-05-01"),      # far away
        line(rice, 3, unit_cost=300),                          # no expiry: never alerts
    ], purchase_date="2026-11-01"))
    assert alerts.expiry_days() == 30
    soon = alerts.expiry_alerts()
    assert [(a.item_name_en, a.days_left) for a in soon] == [("Daal", 0), ("Rice", 15)] and not any(a.expired for a in soon)
    assert [a.item_name_en for a in alerts.expiry_alerts(within_days=7)] == ["Daal"]
    alerts.set_expiry_days(200)
    assert [a.item_name_en for a in alerts.expiry_alerts()] == ["Daal", "Rice", "Oil"]
    with pytest.raises(ValueError):
        alerts.set_expiry_days(-1)


def test_expired_stock_and_write_off(svc):
    from app.services.alert_service import AlertService
    alerts = AlertService(svc.conn, svc.settings, today=lambda: "2026-12-10")
    rice = item(svc)
    svc.purchases.create(svc.owner, PurchaseInput([line(rice, 10, unit_cost=300, expiry="2026-12-01"),
                                                   line(rice, 6, unit_cost=300, expiry="2027-03-01")], purchase_date="2026-11-01"))
    expired = alerts.expiry_alerts(expired_only=True)
    assert len(expired) == 1 and expired[0].expired and expired[0].days_left == -9 and expired[0].qty_left == Q(10)
    written = svc.stock.write_off_batch(svc.owner, expired[0].batch_id, "expired on shelf")
    assert written == Q(10) and svc.items.get(rice.id).stock == Q(6)
    assert alerts.expiry_alerts(expired_only=True) == []                  # gone from the alert list
    assert svc.stock.movements(rice.id)[0].kind == "adjust_expiry"
    with pytest.raises(ValidationError):
        svc.stock.write_off_batch(svc.owner, expired[0].batch_id)         # nothing left to write off
    healthy(svc)


def test_write_off_takes_the_chosen_batch_not_the_fifo_one(svc):
    rice = item(svc)
    svc.purchases.create(svc.owner, PurchaseInput([line(rice, 4, unit_cost=300, expiry="2026-12-01"),
                                                   line(rice, 6, unit_cost=300, expiry="2027-03-01")]))
    later = svc.conn.execute("SELECT id FROM item_batches WHERE expiry_date = '2027-03-01'").fetchone()["id"]
    svc.stock.write_off_batch(svc.owner, later)
    left = {r["expiry_date"]: r["qty_left_milli"] for r in svc.conn.execute("SELECT * FROM item_batches")}
    assert left == {"2026-12-01": 4000, "2027-03-01": 0}
    healthy(svc)
