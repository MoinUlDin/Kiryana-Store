"""Bulk item import from a spreadsheet: read, validate every row (nothing is saved), then apply
the good rows in ONE transaction. Existing items (matched by short code) are skipped by default,
so a corrected file can be imported again without creating duplicates."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.db.connection import atomic
from app.domain.item import ItemInput
from app.domain.money import Money
from app.domain.quantity import Quantity
from app.domain.text import normalize_search
from app.domain.user import User
from app.infra.spreadsheet import MAX_ROWS, SpreadsheetError, read_rows
from app.security.passwords import ValidationError
from app.services.audit_service import AuditService
from app.services.item_service import ItemService
from app.services.named_list_service import NamedListService

REQUIRED = ("short_code", "unit", "sale")  # plus a name: name_en or name_ur

_ALIASES = {
    "short_code": "shortcode code itemcode sku productcode",
    "name_en": "nameen name nameenglish englishname itemname item product productname",
    "name_ur": "nameur nameurdu urduname urdu",
    "category": "category categoryname group",
    "brand": "brand company",
    "unit": "unit uom unitofmeasure soldby",
    "sale": "saleprice sellingprice price rate salerate retailprice mrp",
    "cost": "costprice cost purchaseprice buyprice costrate",
    "barcode": "barcode qr qrcode barcodeqr",
    "opening": "openingstock stock qty quantity openingqty onhand",
    "low": "lowstock lowstockalert reorderlevel minstock minimumstock",
    "tax": "tax taxpercent taxrate",
    "fraction": "allowfraction fraction allowfractions fractions",
}
HEADER_MAP = {alias: key for key, aliases in _ALIASES.items() for alias in aliases.split()}

_UNITS = {
    "piece": "piece", "pieces": "piece", "pc": "piece", "pcs": "piece", "each": "piece", "unit": "piece",
    "عدد": "piece", "دانہ": "piece", "نگ": "piece",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilogram": "kg", "کلو": "kg", "کلوگرام": "kg",
    "litre": "litre", "liter": "litre", "ltr": "litre", "lt": "litre", "l": "litre", "لیٹر": "litre", "لٹر": "litre",
}
_YES = {"yes", "y", "true", "1", "ہاں", "جی"}
_NO = {"no", "n", "false", "0", "نہیں", "نا"}
_EXPONENT = re.compile(r"^-?\d+(\.\d+)?[eE][+-]?\d+$")
_DECIMAL_ZERO = re.compile(r"^-?\d+\.0+$")


@dataclass(frozen=True)
class RowIssue:
    code: str
    params: dict = field(default_factory=dict)
    column: str | None = None


@dataclass(frozen=True)
class ParsedRow:
    item: ItemInput
    category: str | None
    brand: str | None
    opening: Quantity
    existing_id: int | None = None


@dataclass
class RowResult:
    row: int            # the row number as shown in Excel
    action: str         # create | update | skip | error
    code: str
    name: str
    issues: list[RowIssue] = field(default_factory=list)
    data: ParsedRow | None = None


@dataclass
class ImportPreview:
    file_issues: list[RowIssue] = field(default_factory=list)
    rows: list[RowResult] = field(default_factory=list)
    new_categories: list[str] = field(default_factory=list)
    new_brands: list[str] = field(default_factory=list)

    def count(self, action: str) -> int:
        return sum(1 for r in self.rows if r.action == action)

    @property
    def importable(self) -> int:
        return self.count("create") + self.count("update")


@dataclass(frozen=True)
class ImportOutcome:
    created: int
    updated: int
    skipped: int
    errors: int
    categories_created: int
    brands_created: int


# ---------------------------------------------------------------------------------------- cell parsing
def _clean_code(text: str) -> str:
    """Codes and barcodes: Excel may hand over 8.9E+12 or 123.0 for a numeric cell."""
    text = text.strip()
    if _EXPONENT.match(text):
        text = format(Decimal(text), "f")
    if _DECIMAL_ZERO.match(text):
        text = text.split(".")[0]
    return text


def _lenient(text: str, places: int, code: str) -> Decimal:
    """A number as Excel stores it: tolerates thousands commas, Urdu digits and float noise
    (0.30000000000000004 -> 0.30), but rejects a real extra decimal digit (1.005 as money)."""
    cleaned = normalize_search(text).replace(",", "").replace("\u066b", ".").replace(" ", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValidationError(code) from exc
    if not value.is_finite():
        raise ValidationError(code)
    rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if abs(value - rounded) > Decimal("0.0000001"):
        raise ValidationError(code)
    return rounded


def _money(text: str, *, allow_empty: bool) -> Money:
    if not text.strip():
        if allow_empty:
            return Money(0)
        raise ValidationError("error.price_invalid")
    value = _lenient(text, 2, "error.price_invalid")
    if value < 0:
        raise ValidationError("error.price_invalid")
    return Money(int(value * 100))


def _quantity(text: str) -> Quantity:
    if not text.strip():
        return Quantity(0)
    value = _lenient(text, 3, "error.quantity_invalid")
    if value < 0:
        raise ValidationError("error.quantity_invalid")
    return Quantity(int(value * 1000))


def _tax(text: str) -> int | None:
    text = text.strip().rstrip("%").strip()
    if not text:
        return None
    value = _lenient(text, 2, "error.tax_invalid")
    if not 0 <= value <= 100:
        raise ValidationError("error.tax_invalid")
    return int(value * 100)


def _unit(text: str) -> str:
    key = text.strip().lower().replace(".", "")
    if not key:
        raise ValidationError("import.error.unit_required")
    unit = _UNITS.get(key)
    if unit is None:
        raise ValidationError("import.error.unit_unknown", value=text.strip())
    return unit


def _flag(text: str) -> bool | None:
    key = text.strip().lower()
    if not key:
        return None
    if key in _YES:
        return True
    if key in _NO:
        return False
    raise ValidationError("import.error.bool_invalid")


def _header_key(text: str) -> str | None:
    return HEADER_MAP.get(re.sub(r"[\s_\-./%()]+", "", text.lower()))


# ---------------------------------------------------------------------------------------- the service
class ImportService:
    def __init__(self, conn: sqlite3.Connection, audit: AuditService, items: ItemService,
                 categories: NamedListService, brands: NamedListService) -> None:
        self._conn = conn
        self._audit = audit
        self._items = items
        self._categories = categories
        self._brands = brands

    @staticmethod
    def read_file(path) -> list[list[str]]:
        return read_rows(path)   # raises SpreadsheetError

    # ---- step 1: check everything, save nothing --------------------------------------------
    def preview(self, rows: list[list[str]], update_existing: bool = False) -> ImportPreview:
        result = ImportPreview()
        header_index = next((i for i, row in enumerate(rows) if any(cell.strip() for cell in row)), None)
        if header_index is None:
            result.file_issues.append(RowIssue("import.error.no_header"))
            return result
        if len(rows) > MAX_ROWS + 1:
            result.file_issues.append(RowIssue("import.error.too_big", {"max": MAX_ROWS}))
            return result

        columns: dict[str, int] = {}
        for index, cell in enumerate(rows[header_index]):
            key = _header_key(cell)
            if key and key not in columns:
                columns[key] = index
        missing = [k for k in REQUIRED if k not in columns]
        if "name_en" not in columns and "name_ur" not in columns:
            missing.insert(1, "name_en")
        if missing:
            result.file_issues.append(RowIssue("import.error.missing_columns", {"columns": ", ".join(missing)}))
            return result

        existing_categories = {c.name_en.lower() for c in self._categories.list(include_inactive=True)}
        existing_brands = {b.name_en.lower() for b in self._brands.list(include_inactive=True)}
        new_categories: dict[str, str] = {}
        new_brands: dict[str, str] = {}
        seen: dict[str, int] = {}   # code or barcode (lower case) -> first row that used it

        for offset, row in enumerate(rows[header_index + 1:], start=header_index + 2):
            if not any(cell.strip() for cell in row):
                continue
            outcome = self._check_row(offset, row, columns, seen, update_existing)
            result.rows.append(outcome)
            if outcome.action in ("create", "update") and outcome.data:
                for name, known, bucket in ((outcome.data.category, existing_categories, new_categories),
                                            (outcome.data.brand, existing_brands, new_brands)):
                    if name and name.lower() not in known:
                        bucket.setdefault(name.lower(), name)
        result.new_categories = list(new_categories.values())
        result.new_brands = list(new_brands.values())
        return result

    def _check_row(self, number: int, row: list[str], columns: dict[str, int], seen: dict[str, int],
                   update_existing: bool) -> RowResult:
        def cell(key: str) -> str:
            index = columns.get(key)
            return row[index].strip() if index is not None and index < len(row) else ""

        issues: list[RowIssue] = []

        def attempt(key: str, parse, *args, **kwargs):
            try:
                return parse(*args, **kwargs)
            except ValidationError as exc:
                issues.append(RowIssue(exc.code, exc.params, key))
                return None

        code = _clean_code(cell("short_code"))
        name_ur = cell("name_ur") or None
        name_en = cell("name_en") or name_ur or ""
        label = name_en or code
        if not code:
            issues.append(RowIssue("error.code_required", column="short_code"))
        if not name_en:
            issues.append(RowIssue("error.name_required", column="name_en"))
        unit = attempt("unit", _unit, cell("unit"))
        sale = attempt("sale", _money, cell("sale"), allow_empty=False)
        cost = attempt("cost", _money, cell("cost"), allow_empty=True)
        opening = attempt("opening", _quantity, cell("opening"))
        low = attempt("low", _quantity, cell("low"))
        tax = attempt("tax", _tax, cell("tax"))
        fraction = attempt("fraction", _flag, cell("fraction"))
        barcode = _clean_code(cell("barcode")) or None
        if issues:
            return RowResult(number, "error", code, label, issues)

        allow_fraction = (unit != "piece") if fraction is None else fraction
        item = ItemInput(name_en=name_en, name_ur=name_ur, short_code=code, unit=unit, sale=sale, cost=cost,
                         barcode=barcode, allow_fraction=allow_fraction, tax_bp=tax, low_stock=low)
        parsed = ParsedRow(item, cell("category") or None, cell("brand") or None, opening)

        # codes repeated inside the file
        for value in filter(None, (code.lower(), barcode.lower() if barcode else None)):
            if value in seen:
                return RowResult(number, "error", code, label,
                                 [RowIssue("import.error.dup_in_file", {"row": seen[value]},
                                           "short_code" if value == code.lower() else "barcode")])

        def claim() -> None:   # only rows that will really be used reserve their code and barcode
            seen[code.lower()] = number
            if barcode:
                seen[barcode.lower()] = number

        existing = self._items.get_by_short_code(code)
        if existing is not None:
            if not update_existing:
                claim()
                return RowResult(number, "skip", code, label, [RowIssue("import.skipped_exists")], parsed)
            if existing.unit != unit and self._items.has_history(existing.id):
                return RowResult(number, "error", code, label, [RowIssue("import.error.unit_differs", column="unit")])
            parsed = ParsedRow(item, parsed.category, parsed.brand, parsed.opening, existing.id)
        try:
            self._items.validate(item, existing.id if existing else None)
        except ValidationError as exc:
            column = {"error.code_taken": "short_code", "error.barcode_taken": "barcode"}.get(exc.code)
            return RowResult(number, "error", code, label, [RowIssue(exc.code, exc.params, column)])
        claim()
        return RowResult(number, "update" if existing else "create", code, label, [], parsed)

    # ---- step 2: save the good rows, all or nothing ---------------------------------------
    def apply(self, actor: User, preview: ImportPreview) -> ImportOutcome:
        categories_created = brands_created = created = updated = 0
        with atomic(self._conn):
            category_ids = {c.name_en.lower(): c.id for c in self._categories.list(include_inactive=True)}
            brand_ids = {b.name_en.lower(): b.id for b in self._brands.list(include_inactive=True)}
            for name in preview.new_categories:
                if name.lower() not in category_ids:
                    category_ids[name.lower()] = self._categories.add(actor, name).id
                    categories_created += 1
            for name in preview.new_brands:
                if name.lower() not in brand_ids:
                    brand_ids[name.lower()] = self._brands.add(actor, name).id
                    brands_created += 1
            for row in preview.rows:
                if row.action not in ("create", "update") or row.data is None:
                    continue
                data = row.data
                item = ItemInput(**{**data.item.__dict__,
                                    "category_id": category_ids.get((data.category or "").lower()),
                                    "brand_id": brand_ids.get((data.brand or "").lower())})
                if row.action == "create":
                    self._items.create(actor, item, data.opening if data.opening.milli else None)
                    created += 1
                else:
                    self._items.update(actor, data.existing_id, item)
                    updated += 1
            skipped, errors = preview.count("skip"), preview.count("error")
            self._audit.log(actor, "import.items", entity="item",
                            new={"created": created, "updated": updated, "skipped": skipped, "errors": errors,
                                 "categories_created": categories_created, "brands_created": brands_created})
        return ImportOutcome(created, updated, preview.count("skip"), preview.count("error"),
                             categories_created, brands_created)
