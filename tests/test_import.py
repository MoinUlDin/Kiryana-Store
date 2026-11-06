import pytest
from openpyxl import Workbook, load_workbook

from app.domain.item import ItemInput
from app.domain.money import Money
from app.domain.quantity import Quantity
from app.domain.user import ROLE_OWNER, ROLE_SUPERADMIN, SYSTEM
from app.infra.spreadsheet import SpreadsheetError, cell_to_text, read_rows, write_template
from app.services.import_service import ImportService
from tests.helpers import make_services

R = Money.from_rupees
Q = Quantity.from_decimal
HEAD = ["short_code", "name_en", "name_ur", "category", "brand", "unit", "sale_price", "cost_price",
        "barcode", "opening_stock", "low_stock_alert", "tax_percent", "allow_fraction"]


@pytest.fixture
def svc(tmp_path):
    s = make_services(tmp_path)
    admin = s.auth.create_user(SYSTEM, "admin", "Dev", ROLE_SUPERADMIN, "adminpass")
    s.owner = s.auth.create_user(admin, "owner", "Owner", ROLE_OWNER, "ownerpass")
    s.dir = tmp_path
    yield s
    s.conn.close()


def preview(svc, rows, update=False):
    return svc.importer.preview(rows, update_existing=update)


def row(code, name="Name", unit="kg", sale="100", **kw):
    base = {"short_code": code, "name_en": name, "name_ur": "", "category": "", "brand": "", "unit": unit,
            "sale_price": sale, "cost_price": "", "barcode": "", "opening_stock": "", "low_stock_alert": "",
            "tax_percent": "", "allow_fraction": ""}
    base.update(kw)
    return [base[h] for h in HEAD]


def by_code(prev):
    return {r.code: r for r in prev.rows}


# ---------------- reading real files ----------------
def test_template_round_trips_through_the_reader_and_the_importer(svc):
    path = svc.dir / "template.xlsx"
    write_template(path)
    rows = read_rows(path)
    assert rows[0] == HEAD and len(rows) == 3                                  # header + 2 examples
    prev = preview(svc, rows)
    assert prev.file_issues == [] and [r.action for r in prev.rows] == ["create", "create"]
    assert prev.new_categories == ["Grocery", "Soap"] and prev.new_brands == ["Lifebuoy"]
    outcome = svc.importer.apply(svc.owner, prev)
    assert (outcome.created, outcome.categories_created, outcome.brands_created) == (2, 2, 1)
    sugar = svc.items.get_by_short_code("SUG")
    assert sugar.unit == "kg" and sugar.sale == R(150) and sugar.cost == R(138) and sugar.stock == Q(50) and sugar.allow_fraction
    lifebuoy = svc.items.get_by_short_code("LB-S")
    assert lifebuoy.name_ur == "لائف بوائے چھوٹا" and lifebuoy.barcode == "8901030865278" and not lifebuoy.allow_fraction
    assert svc.stock.check_invariants() == []
    assert [m.kind for m in svc.stock.movements(sugar.id)] == ["opening"]


def test_excel_style_numbers_and_gaps(svc):
    wb = Workbook()
    ws = wb.active
    ws.title = "Items"
    ws.append(HEAD)
    ws.append(["A1", "Rice", None, None, None, "kg", 400.5, 320, 8901234567890, 12.5, 5, None, None])   # numeric barcode
    ws.append([None] * 13)                                                                              # blank row
    ws.append(["A2", "Daal", None, None, None, "KG", 0.1 + 0.2, None, None, None, None, None, None])   # float noise 0.30000000000000004
    ws.cell(row=6, column=1, value="A3")                                                                # gap of two rows
    ws.cell(row=6, column=2, value="Tea")
    ws.cell(row=6, column=6, value="piece")
    ws.cell(row=6, column=7, value=1234)
    path = svc.dir / "excel.xlsx"
    wb.save(path)
    prev = preview(svc, read_rows(path))
    rows = by_code(prev)
    assert [r.action for r in prev.rows] == ["create", "create", "create"]
    assert rows["A1"].data.item.barcode == "8901234567890" and rows["A1"].data.item.sale == R("400.5")
    assert rows["A1"].data.opening == Q("12.5")
    assert rows["A2"].data.item.sale == Money(30)                  # 0.30000000000000004 -> Rs 0.30
    assert rows["A3"].row == 6                                     # row numbers match what Excel shows
    svc.importer.apply(svc.owner, prev)
    assert svc.items.get_by_short_code("A3").sale == R(1234)


def test_cell_to_text():
    assert cell_to_text(None) == "" and cell_to_text(5) == "5" and cell_to_text(5.0) == "5"
    assert cell_to_text(0.1 + 0.2) == "0.30000000000000004" and cell_to_text(" x ") == "x" and cell_to_text(True) == "1"
    assert cell_to_text(8.901234567890E12) == "8901234567890"      # no exponent in the text


def test_csv_with_bom_and_semicolons(svc):
    path = svc.dir / "items.csv"
    path.write_text("\ufeffshort_code;name_en;unit;sale_price\nC1;Chai;piece;10\nC2;چینی;kg;150\n", encoding="utf-8")
    prev = preview(svc, read_rows(path))
    assert prev.file_issues == [] and [r.action for r in prev.rows] == ["create", "create"]


def test_unreadable_files(svc):
    bad = svc.dir / "broken.xlsx"
    bad.write_bytes(b"this is not a zip")
    with pytest.raises(SpreadsheetError) as e1:
        read_rows(bad)
    assert e1.value.code == "import.error.read"
    old = svc.dir / "old.xls"
    old.write_bytes(b"xx")
    with pytest.raises(SpreadsheetError):
        read_rows(old)
    with pytest.raises(SpreadsheetError):
        read_rows(svc.dir / "missing.xlsx")


def test_sheet_named_items_is_preferred_and_first_sheet_otherwise(svc):
    wb = Workbook()
    wb.active.title = "Notes"
    wb.active.append(["nothing here"])
    items = wb.create_sheet("Items")
    items.append(["short_code", "name_en", "unit", "sale_price"])
    items.append(["Z1", "Zeera", "kg", 900])
    path = svc.dir / "two.xlsx"
    wb.save(path)
    assert read_rows(path)[1][0] == "Z1"


# ---------------- headers ----------------
def test_flexible_headers(svc):
    rows = [["Code", "Item Name", "اردو", "UOM", "Selling Price", "Cost", "Stock", "Reorder level"],
            ["F1", "Flour", "", "KG", "120", "100", "40", "10"]]
    prev = preview(svc, [["Code", "Item Name", "UOM", "Selling Price", "Cost", "Stock", "Reorder level"],
                         ["F1", "Flour", "KG", "120", "100", "40", "10"]])
    assert prev.file_issues == [] and prev.rows[0].action == "create"
    data = prev.rows[0].data
    assert data.item.cost == R(100) and data.opening == Q(40) and data.item.low_stock == Q(10)


def test_missing_columns_and_empty_files(svc):
    prev = preview(svc, [["short_code", "name_en"], ["A", "B"]])
    assert prev.file_issues[0].code == "import.error.missing_columns"
    assert "unit" in prev.file_issues[0].params["columns"] and "sale" in prev.file_issues[0].params["columns"]
    assert preview(svc, []).file_issues[0].code == "import.error.no_header"
    assert preview(svc, [[], [""]]).file_issues[0].code == "import.error.no_header"
    nameless = preview(svc, [["short_code", "unit", "sale_price"], ["A", "kg", "5"]])
    assert "name_en" in nameless.file_issues[0].params["columns"]


# ---------------- row checks ----------------
def test_row_errors_are_reported_per_column_and_do_not_stop_other_rows(svc):
    rows = [HEAD,
            row("OK1"),
            row("", name="No code"),
            row("BAD1", unit="metre"),
            row("BAD2", sale="abc"),
            row("BAD3", sale="1.005"),
            row("BAD4", sale="-5"),
            row("BAD5", opening_stock="2.5x"),
            row("BAD6", tax_percent="150"),
            row("BAD7", allow_fraction="maybe"),
            row("BAD8", name=""),
            row("OK2")]
    prev = preview(svc, rows)
    got = {(r.row, r.action): [(i.code, i.column) for i in r.issues] for r in prev.rows}
    # row 1 is the header, so OK1 is row 2 (the numbers match what Excel shows)
    assert got[(2, "create")] == [] and got[(12, "create")] == []
    assert got[(3, "error")] == [("error.code_required", "short_code")]
    assert got[(4, "error")] == [("import.error.unit_unknown", "unit")]
    assert got[(5, "error")] == [("error.price_invalid", "sale")]
    assert got[(6, "error")] == [("error.price_invalid", "sale")]      # a real third decimal is rejected, not rounded
    assert got[(7, "error")] == [("error.price_invalid", "sale")]
    assert got[(8, "error")] == [("error.quantity_invalid", "opening")]
    assert got[(9, "error")] == [("error.tax_invalid", "tax")]
    assert got[(10, "error")] == [("import.error.bool_invalid", "fraction")]
    assert got[(11, "error")] == [("error.name_required", "name_en")]
    assert prev.importable == 2


def test_several_problems_in_one_row_are_all_listed(svc):
    prev = preview(svc, [HEAD, row("X", unit="", sale="")])
    assert {i.column for i in prev.rows[0].issues} == {"unit", "sale"}


def test_unit_synonyms_urdu_and_fraction_defaults(svc):
    rows = [HEAD, row("U1", unit="کلو"), row("U2", unit="Pcs"), row("U3", unit="Ltr"), row("U4", unit="kg", allow_fraction="no"),
            row("U5", unit="piece", allow_fraction="ہاں")]
    prev = preview(svc, rows)
    items = {r.code: r.data.item for r in prev.rows}
    assert [items[c].unit for c in ("U1", "U2", "U3")] == ["kg", "piece", "litre"]
    assert [items[c].allow_fraction for c in ("U1", "U2", "U3", "U4", "U5")] == [True, False, True, False, True]


def test_urdu_digits_and_commas_in_numbers(svc):
    prev = preview(svc, [HEAD, row("N1", sale="١,٢٥٠.٥٠", opening_stock="۲٫۵")])
    data = prev.rows[0].data
    assert data.item.sale == R("1250.5") and data.opening == Q("2.5")


def test_name_falls_back_to_urdu(svc):
    prev = preview(svc, [HEAD, row("UR1", name="", **{"name_ur": "چاول"})])
    assert prev.rows[0].action == "create" and prev.rows[0].data.item.name_en == "چاول"


def test_duplicates_inside_the_file(svc):
    prev = preview(svc, [HEAD, row("D1"), row("d1"), row("D2", barcode="555"), row("D3", barcode="555"), row("555")])
    actions = [r.action for r in prev.rows]
    assert actions == ["create", "error", "create", "error", "error"]
    assert prev.rows[1].issues[0].code == "import.error.dup_in_file" and prev.rows[1].issues[0].params == {"row": 2}
    assert prev.rows[4].issues[0].params == {"row": 4}                 # a short code equal to another row's barcode


def test_existing_items_are_skipped_by_default_and_never_duplicated(svc):
    svc.items.create(svc.owner, ItemInput(name_en="Old", short_code="E1", unit="kg", sale=R(10)))
    prev = preview(svc, [HEAD, row("e1", name="New name", sale="99"), row("E2")])
    assert [r.action for r in prev.rows] == ["skip", "create"]
    outcome = svc.importer.apply(svc.owner, prev)
    assert (outcome.created, outcome.updated, outcome.skipped) == (1, 0, 1)
    assert svc.items.get_by_short_code("E1").name_en == "Old" and svc.items.get_by_short_code("E1").sale == R(10)
    again = svc.importer.apply(svc.owner, preview(svc, [HEAD, row("E1"), row("E2")]))    # importing the same file again
    assert (again.created, again.skipped) == (0, 2)
    assert len(svc.items.search("", include_inactive=True)) == 2


def test_update_mode_changes_details_but_not_stock(svc):
    item = svc.items.create(svc.owner, ItemInput(name_en="Old", short_code="U1", unit="kg", sale=R(10), allow_fraction=True),
                            opening=Q(5)).item
    prev = preview(svc, [HEAD, row("U1", name="Renamed", sale="99", cost_price="80", opening_stock="1000")], update=True)
    assert prev.rows[0].action == "update"
    outcome = svc.importer.apply(svc.owner, prev)
    after = svc.items.get(item.id)
    assert outcome.updated == 1 and after.name_en == "Renamed" and after.sale == R(99) and after.cost == R(80)
    assert after.stock == Q(5)                                          # stock untouched by an update
    assert len(svc.audit.search("item.price_change")) == 1


def test_update_mode_refuses_to_change_the_unit_of_items_with_history(svc):
    svc.items.create(svc.owner, ItemInput(name_en="Old", short_code="U1", unit="kg", sale=R(10)), opening=Q(5))
    prev = preview(svc, [HEAD, row("U1", unit="piece")], update=True)
    assert prev.rows[0].action == "error" and prev.rows[0].issues[0].code == "import.error.unit_differs"
    svc.items.create(svc.owner, ItemInput(name_en="Fresh", short_code="U2", unit="kg", sale=R(10)))
    assert preview(svc, [HEAD, row("U2", unit="piece")], update=True).rows[0].action == "update"   # no history: fine


def test_database_conflicts_are_caught_in_the_preview(svc):
    svc.items.create(svc.owner, ItemInput(name_en="A", short_code="A1", unit="kg", sale=R(10), barcode="999"))
    prev = preview(svc, [HEAD, row("B1", barcode="999"), row("999", name="Code equals a barcode")])
    assert [r.action for r in prev.rows] == ["error", "error"]
    assert prev.rows[0].issues[0].code == "error.barcode_taken" and prev.rows[0].issues[0].column == "barcode"
    assert prev.rows[1].issues[0].code == "error.code_taken"


def test_preview_saves_nothing(svc):
    preview(svc, [HEAD, row("P1", category="Grocery", brand="Acme", opening_stock="5")])
    assert svc.items.search("", include_inactive=True) == [] and svc.categories.list() == [] and svc.brands.list() == []


# ---------------- applying ----------------
def test_apply_creates_everything_and_reuses_existing_categories(svc):
    svc.categories.add(svc.owner, "grocery")                          # already there, different case
    prev = preview(svc, [HEAD, row("A", category="Grocery"), row("B", category="Grocery", brand="Acme"),
                         row("C", category="Soap", brand="ACME", opening_stock="3", cost_price="7", low_stock_alert="1")])
    assert prev.new_categories == ["Soap"] and prev.new_brands == ["Acme"]
    outcome = svc.importer.apply(svc.owner, prev)
    assert (outcome.created, outcome.categories_created, outcome.brands_created) == (3, 1, 1)
    assert sorted(c.name_en for c in svc.categories.list()) == ["Soap", "grocery"]
    c = svc.items.get_by_short_code("C")
    assert c.category_id == next(x.id for x in svc.categories.list() if x.name_en == "Soap")
    assert c.brand_id == svc.items.get_by_short_code("B").brand_id          # "Acme" and "ACME" are one brand
    assert c.stock == Q(3) and c.low_stock == Q(1)
    assert svc.audit.search("import.items")[0]["username"] == "owner"
    assert svc.stock.check_invariants() == []


def test_apply_is_all_or_nothing(svc):
    prev = preview(svc, [HEAD, row("G1", category="NewCat"), row("G2")])
    svc.items.create(svc.owner, ItemInput(name_en="Race", short_code="G2", unit="kg", sale=R(1)))   # appears after the preview
    with pytest.raises(Exception):
        svc.importer.apply(svc.owner, prev)
    assert svc.items.get_by_short_code("G1") is None and svc.categories.list() == []
    assert svc.conn.in_transaction is False
    assert svc.stock.check_invariants() == []


def test_big_import_is_fast_enough(svc):
    import time
    rows = [HEAD] + [row(f"B{i}", name=f"Item {i}", opening_stock="5", cost_price="5", sale="9") for i in range(1500)]
    started = time.time()
    prev = preview(svc, rows)
    outcome = svc.importer.apply(svc.owner, prev)
    elapsed = time.time() - started
    assert outcome.created == 1500 and elapsed < 30
    assert svc.stock.check_invariants() == []
