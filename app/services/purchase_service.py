from __future__ import annotations

import sqlite3
from datetime import date
from typing import Callable

from app.db.connection import atomic
from app.domain.clock import local_today_iso
from app.domain.money import Money, div_round_half_up
from app.domain.purchase import (
    PAY_METHODS, Purchase, PurchaseInput, PurchaseLine, PurchaseResult, PurchaseWarning, resolve_line_costs,
)
from app.domain.quantity import Quantity
from app.domain.user import User
from app.repositories.item_repo import ItemRepo
from app.repositories.purchase_repo import PurchaseRepo
from app.repositories.supplier_repo import SupplierRepo
from app.security.passwords import ValidationError
from app.services.audit_service import AuditService
from app.services.stock_service import StockService

WARN_COST_ABOVE_SALE = "cost_above_sale"


def weighted_average_cost(old_stock: Quantity, old_cost: Money, add_qty: Quantity, add_cost: Money) -> Money:
    """(old_stock x old_cost + qty x purchase_cost) / (old_stock + qty), integers only, rounded once.
    With no stock on hand the old cost is meaningless, so the new cost simply wins."""
    if old_stock.milli <= 0:
        return add_cost
    value = old_stock.milli * old_cost.paisa + add_qty.milli * add_cost.paisa
    return Money(div_round_half_up(value, old_stock.milli + add_qty.milli))


def _parse_date(text: str, code: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValidationError(code) from exc


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _to_purchase(row: sqlite3.Row) -> Purchase:
    return Purchase(row["id"], row["supplier_id"], row["supplier_name"], row["invoice_no"], row["purchase_date"],
                    Money(row["total_paisa"]), Money(row["paid_paisa"]), row["paid_method"], row["note"],
                    row["created_by_name"], row["created_at"])


class PurchaseService:
    def __init__(self, conn: sqlite3.Connection, audit: AuditService, stock: StockService,
                 today: Callable[[], str] = local_today_iso) -> None:
        self._conn = conn
        self._repo = PurchaseRepo(conn)
        self._items = ItemRepo(conn)
        self._suppliers = SupplierRepo(conn)
        self._audit = audit
        self._stock = stock
        self._today = today

    # ---- creating ----------------------------------------------------------
    def create(self, actor: User, data: PurchaseInput) -> PurchaseResult:
        """One transaction: purchase, lines, batches, stock, average costs. Any error changes nothing."""
        if not data.lines:
            raise ValidationError("error.purchase_empty")
        today = self._today()
        purchase_date = _parse_date(data.purchase_date or today, "error.date_invalid")
        if purchase_date > today:
            raise ValidationError("error.date_future")
        invoice = (data.invoice_no or "").strip() or None
        if data.supplier_id is not None and self._suppliers.get(data.supplier_id) is None:
            raise ValueError("no such supplier")
        if data.supplier_id is not None and invoice and self._repo.invoice_exists(data.supplier_id, invoice):
            raise ValidationError("error.purchase_duplicate")

        prepared = [self._prepare_line(line, purchase_date) for line in data.lines]
        total = Money(sum(p["line_total"].paisa for p in prepared))
        if data.paid.paisa < 0 or data.paid > total:
            raise ValidationError("error.paid_exceeds_total")
        if data.paid.paisa > 0 and data.paid_method not in PAY_METHODS:
            raise ValidationError("error.pay_method_required")
        method = data.paid_method if data.paid.paisa > 0 else None

        warnings: list[PurchaseWarning] = []
        cost_changes: list[dict] = []
        try:
            with atomic(self._conn):
                purchase_id = self._repo.insert(data.supplier_id, invoice, purchase_date, total.paisa, data.paid.paisa,
                                                method, (data.note or "").strip() or None, actor.id or None)
                for p in prepared:
                    row = self._items.get(p["item_id"])  # re-read each time: the same item may appear twice
                    old_stock, old_cost = Quantity(row["stock_milli"]), Money(row["cost_paisa"])
                    new_avg = weighted_average_cost(old_stock, old_cost, p["qty"], p["unit_cost"])
                    line_id = self._repo.insert_line(purchase_id, p["item_id"], p["qty"].milli, p["unit_cost"].paisa,
                                                     p["line_total"].paisa, p["expiry"], old_cost.paisa, new_avg.paisa)
                    batch_id = self._stock.receive(actor, p["item_id"], p["qty"], p["unit_cost"], kind="purchase",
                                                   source="purchase", expiry=p["expiry"], ref_type="purchase",
                                                   ref_id=purchase_id, purchase_line_id=line_id)
                    self._repo.link_batch(line_id, batch_id)
                    if new_avg != old_cost:
                        self._items.set_cost(p["item_id"], new_avg.paisa)
                        cost_changes.append({"item_id": p["item_id"], "old": old_cost.paisa, "new": new_avg.paisa})
                    sale = Money(row["sale_paisa"])
                    if p["new_sale"] is not None and p["new_sale"] != sale:
                        self._items.set_sale(p["item_id"], p["new_sale"].paisa)
                        self._audit.log(actor, "item.price_change", entity="item", entity_id=p["item_id"],
                                        old={"sale_paisa": sale.paisa}, new={"sale_paisa": p["new_sale"].paisa},
                                        reason=f"purchase #{purchase_id}")
                        sale = p["new_sale"]
                    if new_avg > sale:
                        warnings.append(PurchaseWarning(WARN_COST_ABOVE_SALE, p["item_id"], row["name_en"], new_avg, sale))
                self._audit.log(actor, "purchase.create", entity="purchase", entity_id=purchase_id,
                                new={"total_paisa": total.paisa, "paid_paisa": data.paid.paisa, "lines": len(prepared),
                                     "supplier_id": data.supplier_id, "invoice_no": invoice, "date": purchase_date,
                                     "cost_changes": cost_changes})
        except sqlite3.IntegrityError as exc:  # unique invoice index raced past our check
            raise ValidationError("error.purchase_duplicate") from exc
        return PurchaseResult(purchase_id, total, tuple(warnings))

    def _prepare_line(self, line, purchase_date: str) -> dict:
        row = self._items.get(line.item_id)
        if row is None:
            raise ValueError(f"no such item {line.item_id}")
        if not row["is_active"]:
            raise ValidationError("error.item_inactive")
        if line.qty.milli <= 0:
            raise ValidationError("error.quantity_invalid")
        if not row["allow_fraction"] and not line.qty.is_whole:
            raise ValidationError("error.fraction_not_allowed")
        unit_cost, line_total = resolve_line_costs(line)
        if unit_cost.paisa < 0 or line_total.paisa < 0:
            raise ValidationError("error.price_invalid")
        if line.new_sale is not None and line.new_sale.paisa < 0:
            raise ValidationError("error.price_invalid")
        expiry = None
        if line.expiry_date:
            expiry = _parse_date(line.expiry_date, "error.expiry_invalid")
            if expiry < purchase_date:
                raise ValidationError("error.expiry_invalid")
        return {"item_id": line.item_id, "qty": line.qty, "unit_cost": unit_cost, "line_total": line_total,
                "expiry": expiry, "new_sale": line.new_sale}

    # ---- reading -----------------------------------------------------------
    def get(self, purchase_id: int) -> tuple[Purchase, list[PurchaseLine]] | None:
        row = self._repo.get(purchase_id)
        if row is None:
            return None
        lines = [PurchaseLine(r["item_id"], r["name_en"], r["name_ur"], r["short_code"], r["unit"],
                              Quantity(r["qty_milli"]), Money(r["cost_paisa"]), Money(r["line_total_paisa"]),
                              r["expiry_date"], Money(r["avg_cost_before"]), Money(r["avg_cost_after"]))
                 for r in self._repo.lines(purchase_id)]
        return _to_purchase(row), lines

    def search(self, date_from: str | None = None, date_to: str | None = None, supplier_id: int | None = None,
               text: str = "", limit: int = 500) -> list[Purchase]:
        text = text.strip()
        rows = self._repo.search(date_from, date_to, supplier_id, _like(text) if text else None, limit)
        return [_to_purchase(r) for r in rows]
