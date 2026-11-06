from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from app.db.connection import atomic
from app.domain.item import UNITS, Item, ItemInput
from app.domain.money import Money
from app.domain.quantity import Quantity
from app.domain.text import normalize_search
from app.domain.user import User
from app.repositories.item_repo import ItemRepo
from app.repositories.named_list_repo import NamedListRepo
from app.security.passwords import ValidationError
from app.services.audit_service import AuditService
from app.services.stock_service import StockService

_CODE = re.compile(r"^[A-Za-z0-9_\-.]{1,20}$")
_BARCODE = re.compile(r"^\S{1,64}$")
WARN_COST_ABOVE_SALE = "cost_above_sale"


@dataclass(frozen=True)
class SaveResult:
    item: Item
    warnings: tuple[str, ...] = ()


def to_item(row: sqlite3.Row) -> Item:
    return Item(
        id=row["id"], name_en=row["name_en"], name_ur=row["name_ur"], short_code=row["short_code"],
        barcode=row["barcode"], category_id=row["category_id"], brand_id=row["brand_id"], unit=row["unit"],
        allow_fraction=bool(row["allow_fraction"]), cost=Money(row["cost_paisa"]), sale=Money(row["sale_paisa"]),
        tax_bp=row["tax_bp"], stock=Quantity(row["stock_milli"]), low_stock=Quantity(row["low_stock_milli"]),
        is_active=bool(row["is_active"]),
    )


class ItemService:
    def __init__(self, conn: sqlite3.Connection, audit: AuditService, stock: StockService) -> None:
        self._conn = conn
        self._repo = ItemRepo(conn)
        self._categories = NamedListRepo(conn, "categories")
        self._brands = NamedListRepo(conn, "brands")
        self._audit = audit
        self._stock = stock

    # ---- reading -----------------------------------------------------------
    def get(self, item_id: int) -> Item | None:
        row = self._repo.get(item_id)
        return to_item(row) if row else None

    def get_by_short_code(self, code: str) -> Item | None:
        row = self._repo.get_by_short_code(code.strip()) if code.strip() else None
        return to_item(row) if row else None

    def find_by_code(self, code: str) -> Item | None:
        """Exact barcode or short code (what the scanner / quick entry sends)."""
        code = code.strip()
        row = self._repo.find_code(code) if code else None
        return to_item(row) if row else None

    def search(self, text: str = "", category_id: int | None = None, low_only: bool = False,
               include_inactive: bool = False, limit: int = 500) -> list[Item]:
        tokens = normalize_search(text).split()
        rows = self._repo.search(tokens, text.strip(), category_id, low_only, include_inactive, limit)
        return [to_item(r) for r in rows]

    def has_history(self, item_id: int) -> bool:
        return self._repo.movement_count(item_id) > 0

    # ---- validation --------------------------------------------------------
    def validate(self, data: ItemInput, exclude_id: int | None = None) -> dict:
        """Check everything about an item form and return the cleaned column values (raises ValidationError)."""
        name_en = data.name_en.strip()
        if not name_en:
            raise ValidationError("error.name_required")
        code = data.short_code.strip()
        if not code:
            raise ValidationError("error.code_required")
        if not _CODE.match(code):
            raise ValidationError("error.code_invalid")
        barcode = (data.barcode or "").strip() or None
        if barcode is not None and not _BARCODE.match(barcode):
            raise ValidationError("error.barcode_invalid")
        if data.unit not in UNITS:
            raise ValueError(f"unknown unit {data.unit!r}")
        if data.sale.paisa < 0 or data.cost.paisa < 0:
            raise ValidationError("error.price_invalid")
        if data.tax_bp is not None and not 0 <= data.tax_bp <= 10000:
            raise ValidationError("error.tax_invalid")
        if data.low_stock.milli < 0:
            raise ValidationError("error.quantity_invalid")
        if data.category_id is not None and self._categories.get(data.category_id) is None:
            raise ValueError("no such category")
        if data.brand_id is not None and self._brands.get(data.brand_id) is None:
            raise ValueError("no such brand")

        # A short code and a barcode share one lookup (find_by_code), so neither may equal the other's value.
        for value, label in ((code, "short_code"), (barcode, "barcode")):
            if value is None:
                continue
            clash = self._repo.code_conflicts(value, exclude_id)
            if clash["short_code"] or clash["barcode"]:
                raise ValidationError("error.code_taken" if label == "short_code" else "error.barcode_taken")
        if barcode is not None and barcode.lower() == code.lower():
            raise ValidationError("error.barcode_taken")

        search_key = normalize_search(f"{name_en} {data.name_ur or ''} {code} {barcode or ''}")
        return {
            "name_en": name_en, "name_ur": (data.name_ur or "").strip() or None, "short_code": code,
            "barcode": barcode, "category_id": data.category_id, "brand_id": data.brand_id, "unit": data.unit,
            "allow_fraction": int(data.allow_fraction), "cost_paisa": data.cost.paisa, "sale_paisa": data.sale.paisa,
            "tax_bp": data.tax_bp, "low_stock_milli": data.low_stock.milli, "search_key": search_key,
        }

    @staticmethod
    def _warnings(data: ItemInput) -> tuple[str, ...]:
        return (WARN_COST_ABOVE_SALE,) if data.cost > data.sale else ()

    # ---- writing -----------------------------------------------------------
    def create(self, actor: User, data: ItemInput, opening: Quantity | None = None) -> SaveResult:
        values = self.validate(data, None)
        if opening is not None and opening.milli < 0:
            raise ValidationError("error.quantity_invalid")
        if opening and opening.milli and not data.allow_fraction and not opening.is_whole:
            raise ValidationError("error.fraction_not_allowed")
        try:
            with atomic(self._conn):
                item_id = self._repo.insert(values)
                warnings = self._warnings(data)
                self._audit.log(actor, "item.create", entity="item", entity_id=item_id,
                                new={k: values[k] for k in values if k != "search_key"}, reason=", ".join(warnings) or None)
                if opening and opening.milli > 0:
                    self._stock.receive(actor, item_id, opening, data.cost, kind="opening", source="opening",
                                        reason="opening stock")
        except sqlite3.IntegrityError as exc:  # a unique constraint raced past our checks
            raise ValidationError("error.code_taken") from exc
        return SaveResult(self.get(item_id), warnings)

    def update(self, actor: User, item_id: int, data: ItemInput) -> SaveResult:
        old_row = self._repo.get(item_id)
        if old_row is None:
            raise ValueError("no such item")
        values = self.validate(data, item_id)
        if not data.allow_fraction and old_row["stock_milli"] % 1000 != 0:
            raise ValidationError("error.fraction_not_allowed")
        try:
            with atomic(self._conn):
                self._repo.update(item_id, values)
                changed = {k: [old_row[k], values[k]] for k in values if k != "search_key" and old_row[k] != values[k]}
                if changed:
                    self._audit.log(actor, "item.update", entity="item", entity_id=item_id,
                                    old={k: v[0] for k, v in changed.items()}, new={k: v[1] for k, v in changed.items()})
                if "unit" in changed:
                    # Allowed even with stock history so a wrong unit can always be fixed. The numbers are kept
                    # as they are (5 kg becomes 5 pieces); the change is audited.
                    self._audit.log(actor, "item.unit_change", entity="item", entity_id=item_id,
                                    old={"unit": changed["unit"][0]}, new={"unit": changed["unit"][1]},
                                    reason="stock quantity numbers kept as they are")
                price_changes = {k: v for k, v in changed.items() if k in ("sale_paisa", "cost_paisa")}
                if price_changes:  # price changes get their own audit line, as the SRS requires
                    self._audit.log(actor, "item.price_change", entity="item", entity_id=item_id,
                                    old={k: v[0] for k, v in price_changes.items()},
                                    new={k: v[1] for k, v in price_changes.items()})
        except sqlite3.IntegrityError as exc:
            raise ValidationError("error.code_taken") from exc
        return SaveResult(self.get(item_id), self._warnings(data))

    def can_delete(self, item_id: int) -> bool:
        return self._repo.get(item_id) is not None and self._repo.reference_count(item_id) == 0

    def delete(self, actor: User, item_id: int) -> None:
        """Remove an item entered by mistake. Only possible while nothing refers to it: no stock history,
        no purchases, no sales. Anything with history is deactivated instead."""
        row = self._repo.get(item_id)
        if row is None:
            raise ValueError("no such item")
        if self._repo.reference_count(item_id) > 0:
            raise ValidationError("error.item_in_use")
        try:
            with atomic(self._conn):
                self._repo.delete(item_id)
                self._audit.log(actor, "item.delete", entity="item", entity_id=item_id,
                                old={k: row[k] for k in ("name_en", "name_ur", "short_code", "barcode", "unit",
                                                         "sale_paisa", "cost_paisa")})
        except sqlite3.IntegrityError as exc:   # a table added later (sales) still refers to it
            raise ValidationError("error.item_in_use") from exc

    def set_active(self, actor: User, item_id: int, active: bool) -> None:
        if self._repo.get(item_id) is None:
            raise ValueError("no such item")
        with atomic(self._conn):
            self._repo.set_active(item_id, active)
            self._audit.log(actor, "item.activate" if active else "item.deactivate", entity="item", entity_id=item_id)
