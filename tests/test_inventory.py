import pytest

from app.domain.item import ItemInput
from app.domain.money import Money
from app.domain.quantity import Quantity
from app.domain.user import ROLE_CASHIER, ROLE_OWNER, ROLE_SUPERADMIN, SYSTEM
from app.security.passwords import ValidationError
from tests.helpers import make_services

R = Money.from_rupees
Q = Quantity.from_decimal


@pytest.fixture
def svc(tmp_path):
    s = make_services(tmp_path)
    admin = s.auth.create_user(SYSTEM, "admin", "Dev", ROLE_SUPERADMIN, "adminpass")
    s.owner = s.auth.create_user(admin, "owner", "Owner", ROLE_OWNER, "ownerpass")
    yield s
    s.conn.close()


def rice(**kw):
    base = dict(name_en="Rice Basmati", name_ur="چاول باسمتی", short_code="RICE1", unit="kg",
                sale=R(400), cost=R(320), allow_fraction=True, low_stock=Q(5))
    base.update(kw)
    return ItemInput(**base)


def healthy(svc):
    assert svc.stock.check_invariants() == []


# ---------------- items ----------------
def test_create_item_with_opening_stock(svc):
    result = svc.items.create(svc.owner, rice(), opening=Q("20"))
    item = result.item
    assert item.stock == Q("20") and item.sale == R(400) and result.warnings == ()
    assert [m.kind for m in svc.stock.movements(item.id)] == ["opening"]
    healthy(svc)


def test_cost_above_sale_is_only_a_warning(svc):
    result = svc.items.create(svc.owner, rice(cost=R(450)))     # cost 450 > sale 400
    assert result.warnings == ("cost_above_sale",) and result.item.cost_above_sale
    assert svc.items.get(result.item.id) is not None            # it was saved anyway


def test_validation_errors(svc):
    cases = {
        "error.name_required": rice(name_en="  "),
        "error.code_required": rice(short_code=" "),
        "error.code_invalid": rice(short_code="has space"),
        "error.barcode_invalid": rice(barcode="two words"),
        "error.price_invalid": rice(sale=Money(-1)),
        "error.tax_invalid": rice(tax_bp=10001),
    }
    for code, data in cases.items():
        with pytest.raises(ValidationError) as err:
            svc.items.create(svc.owner, data)
        assert err.value.code == code, code


def test_codes_must_be_unique_across_short_codes_and_barcodes(svc):
    svc.items.create(svc.owner, rice(short_code="R1", barcode="8901234567890"))
    with pytest.raises(ValidationError) as e1:
        svc.items.create(svc.owner, rice(name_en="Other", short_code="r1"))            # same short code, other case
    assert e1.value.code == "error.code_taken"
    with pytest.raises(ValidationError) as e2:
        svc.items.create(svc.owner, rice(name_en="Other", short_code="R2", barcode="8901234567890"))
    assert e2.value.code == "error.barcode_taken"
    with pytest.raises(ValidationError):                                                # short code equals someone's barcode
        svc.items.create(svc.owner, rice(name_en="Other", short_code="8901234567890"))
    with pytest.raises(ValidationError):                                                # barcode equals someone's short code
        svc.items.create(svc.owner, rice(name_en="Other", short_code="R3", barcode="R1"))
    svc.items.create(svc.owner, rice(name_en="NoBarcode1", short_code="N1", barcode=""))
    svc.items.create(svc.owner, rice(name_en="NoBarcode2", short_code="N2"))             # many items may have no barcode


def test_piece_items_reject_fractions(svc):
    egg = ItemInput(name_en="Egg", short_code="EGG", unit="piece", sale=R(30), cost=R(25))
    with pytest.raises(ValidationError) as err:
        svc.items.create(svc.owner, egg, opening=Q("2.5"))
    assert err.value.code == "error.fraction_not_allowed"
    assert svc.items.create(svc.owner, egg, opening=Q("12")).item.stock == Q("12")


def test_update_logs_price_change_separately(svc):
    item = svc.items.create(svc.owner, rice()).item
    svc.items.update(svc.owner, item.id, rice(sale=R(420)))
    actions = [r["action"] for r in svc.audit.search("item.")]
    assert "item.price_change" in actions and "item.update" in actions
    changed = next(r for r in svc.audit.search("item.price_change"))
    assert "42000" in changed["new_json"] and "40000" in changed["old_json"]
    svc.items.update(svc.owner, item.id, rice(sale=R(420), name_en="Rice Basmati 2"))   # no price change this time
    assert len(svc.audit.search("item.price_change")) == 1


def test_unit_can_be_corrected_even_after_stock_history(svc):
    # Lifebuoy entered by mistake as a kg item with 5 in stock, but it is sold by the piece.
    item = svc.items.create(svc.owner, rice(short_code="LB1", name_en="Lifebuoy small", allow_fraction=True,
                                            low_stock=Q(2)), opening=Q(5)).item
    assert item.unit == "kg"
    fixed = svc.items.update(svc.owner, item.id, rice(short_code="LB1", name_en="Lifebuoy small", unit="piece",
                                                      allow_fraction=False, low_stock=Q(2))).item
    assert fixed.unit == "piece" and fixed.stock == Q(5)            # the numbers are kept: 5 kg -> 5 pieces
    assert [m.qty for m in svc.stock.movements(item.id)] == [Q(5)]
    entry = svc.audit.search("item.unit_change")[0]
    assert '"kg"' in entry["old_json"] and '"piece"' in entry["new_json"]
    healthy(svc)
    svc.stock.adjust(svc.owner, item.id, "damage", Q(1))             # and it now behaves like a piece item
    with pytest.raises(ValidationError):
        svc.stock.adjust(svc.owner, item.id, "damage", Q("0.5"))


def test_unit_change_to_piece_is_refused_while_stock_is_fractional(svc):
    item = svc.items.create(svc.owner, rice(), opening=Q("2.5")).item
    with pytest.raises(ValidationError) as err:
        svc.items.update(svc.owner, item.id, rice(unit="piece", allow_fraction=False))
    assert err.value.code == "error.fraction_not_allowed"
    assert svc.items.get(item.id).unit == "kg"                       # nothing changed
    svc.stock.adjust(svc.owner, item.id, "count", Q(3))              # fix the count first, then the unit works
    assert svc.items.update(svc.owner, item.id, rice(unit="piece", allow_fraction=False)).item.unit == "piece"


def test_unit_change_without_history_is_not_audited_as_a_history_change_but_still_logged(svc):
    fresh = svc.items.create(svc.owner, rice(short_code="X9", name_en="Fresh")).item
    svc.items.update(svc.owner, fresh.id, rice(short_code="X9", name_en="Fresh", unit="litre"))
    assert len(svc.audit.search("item.unit_change")) == 1


def test_delete_an_item_entered_by_mistake(svc):
    item = svc.items.create(svc.owner, rice(short_code="OOPS")).item
    assert svc.items.can_delete(item.id)
    svc.items.delete(svc.owner, item.id)
    assert svc.items.get(item.id) is None and svc.items.find_by_code("OOPS") is None
    assert "OOPS" in svc.audit.search("item.delete")[0]["old_json"]
    again = svc.items.create(svc.owner, rice(short_code="OOPS")).item          # the code is free again
    assert svc.items.find_by_code("OOPS").id == again.id


def test_items_with_history_cannot_be_deleted(svc):
    with_stock = svc.items.create(svc.owner, rice(short_code="S1"), opening=Q(1)).item
    assert not svc.items.can_delete(with_stock.id)
    with pytest.raises(ValidationError) as err:
        svc.items.delete(svc.owner, with_stock.id)
    assert err.value.code == "error.item_in_use" and svc.items.get(with_stock.id) is not None
    svc.items.set_active(svc.owner, with_stock.id, False)                       # the alternative is to deactivate


def test_items_used_in_a_purchase_cannot_be_deleted(svc):
    from app.domain.purchase import PurchaseInput, PurchaseLineInput
    from app.services.purchase_service import PurchaseService
    item = svc.items.create(svc.owner, rice(short_code="P1")).item
    PurchaseService(svc.conn, svc.audit, svc.stock, today=lambda: "2026-11-05").create(
        svc.owner, PurchaseInput([PurchaseLineInput(item.id, Q(1), R(300))]))
    with pytest.raises(ValidationError):
        svc.items.delete(svc.owner, item.id)


def test_cannot_forbid_fractions_while_stock_is_fractional(svc):
    item = svc.items.create(svc.owner, rice(), opening=Q("2.5")).item
    with pytest.raises(ValidationError):
        svc.items.update(svc.owner, item.id, rice(allow_fraction=False))


def test_deactivate_hides_from_default_search(svc):
    item = svc.items.create(svc.owner, rice()).item
    svc.items.set_active(svc.owner, item.id, False)
    assert svc.items.search("rice") == []
    assert [i.id for i in svc.items.search("rice", include_inactive=True)] == [item.id]


# ---------------- search ----------------
def test_search_by_name_code_barcode_and_urdu(svc):
    a = svc.items.create(svc.owner, rice(short_code="R1", barcode="111222333")).item
    b = svc.items.create(svc.owner, ItemInput(name_en="Sugar", name_ur="چینی", short_code="SUG", unit="kg", sale=R(150))).item
    assert [i.id for i in svc.items.search("basm")] == [a.id]
    assert [i.id for i in svc.items.search("r1")] == [a.id]
    assert [i.id for i in svc.items.search("222333")] == [a.id]
    assert [i.id for i in svc.items.search("چيني")] == [b.id]          # Arabic yeh still finds the Urdu name
    assert [i.id for i in svc.items.search("rice basm")] == [a.id]       # every word must match
    assert svc.items.search("zzz") == []
    assert {i.id for i in svc.items.search("")} == {a.id, b.id}


def test_exact_code_sorts_first_and_find_by_code(svc):
    svc.items.create(svc.owner, rice(name_en="Rice Cheap", short_code="RC", barcode=None))
    target = svc.items.create(svc.owner, rice(name_en="Zzz Special", short_code="RICE", barcode=None)).item
    assert svc.items.search("rice")[0].id == target.id                   # exact short code wins over name matches
    assert svc.items.find_by_code(" rice ").id == target.id
    assert svc.items.find_by_code("nothing") is None and svc.items.find_by_code("") is None


def test_search_treats_wildcards_literally(svc):
    svc.items.create(svc.owner, rice(name_en="Plain", short_code="P1"))
    assert svc.items.search("%") == [] and svc.items.search("_") == []


def test_low_stock_filter(svc):
    low = svc.items.create(svc.owner, rice(short_code="L1", low_stock=Q(5)), opening=Q(3)).item
    svc.items.create(svc.owner, rice(name_en="Fine", short_code="L2", low_stock=Q(5)), opening=Q(50))
    svc.items.create(svc.owner, rice(name_en="NoAlert", short_code="L3", low_stock=Q(0)), opening=Q(0))
    assert [i.id for i in svc.items.search(low_only=True)] == [low.id] and low.is_low


# ---------------- stock ----------------
def test_consume_takes_earliest_expiry_first(svc):
    item = svc.items.create(svc.owner, rice()).item
    late = svc.stock.receive(svc.owner, item.id, Q(10), R(300), kind="purchase", source="purchase", expiry="2027-06-01")
    none = svc.stock.receive(svc.owner, item.id, Q(10), R(310), kind="purchase", source="purchase")
    soon = svc.stock.receive(svc.owner, item.id, Q(10), R(320), kind="purchase", source="purchase", expiry="2026-12-01")
    used = svc.stock.consume(svc.owner, item.id, Q(15), "sale")
    assert [(c.batch_id, c.qty) for c in used] == [(soon, Q(10)), (late, Q(5))]   # soonest first, then next expiry
    assert none not in [c.batch_id for c in used]                                  # no-expiry batch is used last
    assert svc.items.get(item.id).stock == Q(15)
    healthy(svc)


def test_cannot_consume_more_than_stock(svc):
    item = svc.items.create(svc.owner, rice(), opening=Q(5)).item
    with pytest.raises(ValidationError) as err:
        svc.stock.consume(svc.owner, item.id, Q("5.001"), "sale")
    assert err.value.code == "error.stock_insufficient"
    assert svc.items.get(item.id).stock == Q(5)            # nothing changed
    healthy(svc)


def test_failed_consume_rolls_back_completely(svc):
    item = svc.items.create(svc.owner, rice(), opening=Q(5)).item
    try:
        svc.stock.consume(svc.owner, item.id, Q(9), "sale")
    except ValidationError:
        pass
    assert len(svc.stock.movements(item.id)) == 1 and svc.conn.in_transaction is False
    healthy(svc)


def test_damage_loss_expiry_reduce_stock_and_are_audited(svc):
    item = svc.items.create(svc.owner, rice(), opening=Q(20)).item
    for kind, qty in (("damage", Q(2)), ("loss", Q("0.5")), ("expiry", Q(1))):
        svc.stock.adjust(svc.owner, item.id, kind, qty, note=f"{kind} test")
    assert svc.items.get(item.id).stock == Q("16.5")
    kinds = {m.kind for m in svc.stock.movements(item.id)}
    assert {"adjust_damage", "adjust_loss", "adjust_expiry"} <= kinds
    assert len(svc.audit.search("stock.adjust")) == 3
    healthy(svc)


def test_count_correction_up_and_down(svc):
    item = svc.items.create(svc.owner, rice(), opening=Q(10)).item
    down = svc.stock.adjust(svc.owner, item.id, "count", Q(8))
    assert (down.old, down.new) == (Q(10), Q(8))
    up = svc.stock.adjust(svc.owner, item.id, "count", Q("12.5"))
    assert (up.old, up.new) == (Q(8), Q("12.5")) and svc.items.get(item.id).stock == Q("12.5")
    same = svc.stock.adjust(svc.owner, item.id, "count", Q("12.5"))
    assert not same.changed
    healthy(svc)


def test_upward_correction_uses_current_cost_for_the_new_batch(svc):
    item = svc.items.create(svc.owner, rice(cost=R(321)), opening=Q(1)).item
    svc.stock.adjust(svc.owner, item.id, "count", Q(3))
    batch = svc.conn.execute("SELECT * FROM item_batches WHERE source = 'adjustment'").fetchone()
    assert batch["cost_paisa"] == 32100 and batch["qty_in_milli"] == 2000


def test_quick_fix_from_zero(svc):
    item = svc.items.create(svc.owner, rice()).item            # system says 0
    result = svc.stock.quick_fix(svc.owner, item.id, Q(4), note="found on shelf")
    assert result.new == Q(4)
    assert svc.stock.movements(item.id)[0].kind == "quick_fix"
    assert svc.audit.search("stock.quick_fix")[0]["reason"] == "found on shelf"
    healthy(svc)


def test_stock_rules_for_piece_items(svc):
    egg = svc.items.create(svc.owner, ItemInput(name_en="Egg", short_code="EGG", unit="piece", sale=R(30)), opening=Q(10)).item
    with pytest.raises(ValidationError):
        svc.stock.adjust(svc.owner, egg.id, "damage", Q("0.5"))
    with pytest.raises(ValidationError):
        svc.stock.adjust(svc.owner, egg.id, "count", Q("7.5"))
    with pytest.raises(ValidationError):
        svc.stock.adjust(svc.owner, egg.id, "damage", Q(0))


def test_movements_are_append_only(svc):
    item = svc.items.create(svc.owner, rice(), opening=Q(5)).item
    import sqlite3
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        svc.conn.execute("UPDATE stock_movements SET qty_milli = 1")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        svc.conn.execute("DELETE FROM stock_movements")


def test_database_refuses_negative_stock_even_if_a_bug_tries(svc):
    item = svc.items.create(svc.owner, rice(), opening=Q(5)).item
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        svc.conn.execute("UPDATE items SET stock_milli = -1 WHERE id = ?", (item.id,))


def test_invariant_checker_detects_corruption(svc):
    item = svc.items.create(svc.owner, rice(), opening=Q(5)).item
    svc.conn.execute("UPDATE items SET stock_milli = 4000 WHERE id = ?", (item.id,))   # simulate a bug
    problems = svc.stock.check_invariants()
    assert len(problems) == 1 and f"item {item.id}" in problems[0]


def test_many_random_operations_keep_invariants(svc):
    import random
    rnd = random.Random(7)
    item = svc.items.create(svc.owner, rice(), opening=Q(50)).item
    for _ in range(200):
        action = rnd.choice(["receive", "consume", "count", "damage"])
        try:
            if action == "receive":
                svc.stock.receive(svc.owner, item.id, Quantity(rnd.randint(1, 5000)), R(300), kind="purchase",
                                  source="purchase", expiry=rnd.choice([None, "2027-01-01", "2026-12-01"]))
            elif action == "consume":
                svc.stock.consume(svc.owner, item.id, Quantity(rnd.randint(1, 8000)), "sale")
            elif action == "count":
                svc.stock.adjust(svc.owner, item.id, "count", Quantity(rnd.randint(0, 30000)))
            else:
                svc.stock.adjust(svc.owner, item.id, "damage", Quantity(rnd.randint(1, 3000)))
        except ValidationError:
            pass  # insufficient stock is a legitimate outcome
        assert svc.stock.check_invariants() == []


# ---------------- categories / brands ----------------
def test_categories_crud_and_protection(svc):
    cat = svc.categories.add(svc.owner, " Rice & Grains ", "چاول")
    assert cat.name_en == "Rice & Grains" and cat.display("ur") == "چاول" and cat.display("en") == "Rice & Grains"
    with pytest.raises(ValidationError) as dup:
        svc.categories.add(svc.owner, "rice & grains")
    assert dup.value.code == "error.list_exists"
    with pytest.raises(ValidationError):
        svc.categories.add(svc.owner, "  ")
    svc.categories.rename(svc.owner, cat.id, "Grains")
    assert [c.name_en for c in svc.categories.list()] == ["Grains"]
    svc.items.create(svc.owner, rice(category_id=cat.id))
    with pytest.raises(ValidationError) as used:
        svc.categories.delete(svc.owner, cat.id)
    assert used.value.code == "error.list_in_use"
    other = svc.categories.add(svc.owner, "Spare")
    svc.categories.delete(svc.owner, other.id)
    assert [c.name_en for c in svc.categories.list()] == ["Grains"]


def test_brands_are_independent_of_categories(svc):
    svc.brands.add(svc.owner, "Lifebuoy")
    assert [b.name_en for b in svc.brands.list()] == ["Lifebuoy"] and svc.categories.list() == []
    item = svc.items.create(svc.owner, rice(brand_id=svc.brands.list()[0].id)).item
    assert item.brand_id is not None
