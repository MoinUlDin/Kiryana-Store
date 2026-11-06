from __future__ import annotations

import json
import sqlite3
from typing import Callable

from app.db.connection import atomic
from app.domain.cart import Cart
from app.domain.clock import local_today_iso
from app.domain.item import Item
from app.domain.money import Money
from app.domain.pricing import compute_totals, discount_amount, line_gross
from app.domain.quantity import Quantity
from app.domain.sale import PAYMENT_METHODS, CheckoutInput, Order, OrderLine, Payment
from app.domain.user import User
from app.repositories.item_repo import ItemRepo
from app.repositories.sale_repo import HeldBillRepo, SaleRepo
from app.security.passwords import ValidationError
from app.services.audit_service import AuditService
from app.services.item_service import to_item
from app.services.sales_settings import SalesSettings
from app.services.stock_service import StockService


def _order_from_rows(row: sqlite3.Row, lines=(), payments=()) -> Order:
    return Order(
        id=row["id"], bill_no=row["bill_no"], business_date=row["business_date"], created_at=row["created_at"],
        cashier_name=row["cashier_name"], subtotal=Money(row["subtotal_paisa"]),
        item_discount=Money(row["item_discount_paisa"]), bill_discount=Money(row["bill_discount_paisa"]),
        rounding=Money(row["rounding_paisa"]), payable=Money(row["payable_paisa"]), status=row["status"],
        note=row["note"],
        lines=tuple(OrderLine(r["item_id"], r["name_snapshot"], r["name_ur_snapshot"], r["unit_snapshot"],
                              Quantity(r["qty_milli"]), Money(r["unit_price_paisa"]), Money(r["cost_snapshot_paisa"]),
                              r["entry_mode"], Money(r["gross_paisa"]), Money(r["discount_paisa"]),
                              Money(r["bill_discount_paisa"]), Money(r["line_total_paisa"]), bool(r["is_misc"]))
                    for r in lines),
        payments=tuple(Payment(r["method"], Money(r["amount_paisa"])) for r in payments),
    )


class SaleService:
    def __init__(self, conn: sqlite3.Connection, audit: AuditService, stock: StockService, settings: SalesSettings,
                 today: Callable[[], str] = local_today_iso) -> None:
        self._conn = conn
        self._repo = SaleRepo(conn)
        self._items = ItemRepo(conn)
        self._audit = audit
        self._stock = stock
        self._settings = settings
        self._today = today

    # ---- checkout ------------------------------------------------------------------
    def checkout(self, actor: User, data: CheckoutInput) -> Order:
        """Turn a cart into a bill. One transaction: bill number, bill, lines, stock, payments.
        Prices and stock are read from the database here; nothing the screen computed is trusted."""
        if not data.lines:
            raise ValidationError("error.cart_empty")
        prepared = [self._prepare(line) for line in data.lines]

        # stock: the SUM per item must be available (the same item may be on several lines)
        demand: dict[int, int] = {}
        for p in prepared:
            if p["item_id"] is not None:
                demand[p["item_id"]] = demand.get(p["item_id"], 0) + p["qty"].milli
        for item_id, needed in demand.items():
            row = self._items.get(item_id)
            if needed > row["stock_milli"]:
                raise ValidationError("error.sale_stock_short", item_id=item_id, name=row["name_en"],
                                      available=Quantity(row["stock_milli"]).format())

        totals = compute_totals([p["gross"] for p in prepared], [p["discount"] for p in prepared],
                                data.bill_discount, self._settings.rounding())
        payments = [(pay.method, pay.amount) for pay in data.payments]
        if any(method not in PAYMENT_METHODS or amount.paisa <= 0 for method, amount in payments):
            raise ValidationError("error.payment_invalid")
        if sum(a.paisa for _m, a in payments) != totals.payable.paisa:
            raise ValidationError("error.payment_mismatch")

        with atomic(self._conn):
            bill_no = self._repo.next_bill_no()
            order_id = self._repo.insert_order(
                bill_no=bill_no, business_date=self._today(), cashier_id=actor.id,
                subtotal_paisa=totals.subtotal.paisa, item_discount_paisa=totals.item_discount.paisa,
                bill_discount_paisa=totals.bill_discount.paisa, rounding_paisa=totals.rounding.paisa,
                payable_paisa=totals.payable.paisa, note=(data.note or "").strip() or None)
            for p, amounts in zip(prepared, totals.lines):
                self._repo.insert_line(
                    order_id=order_id, item_id=p["item_id"], is_misc=int(p["item_id"] is None),
                    name_snapshot=p["name_en"], name_ur_snapshot=p["name_ur"], unit_snapshot=p["unit"],
                    qty_milli=p["qty"].milli, unit_price_paisa=p["unit_price"].paisa,
                    cost_snapshot_paisa=p["cost"].paisa, entry_mode=p["mode"], gross_paisa=amounts.gross.paisa,
                    discount_paisa=amounts.discount.paisa, bill_discount_paisa=amounts.bill_share.paisa,
                    line_total_paisa=amounts.net.paisa)
                if p["item_id"] is not None:
                    self._stock.consume(actor, p["item_id"], p["qty"], "sale", ref_type="order", ref_id=order_id)
                else:
                    self._audit.log(actor, "sale.misc_item", entity="order", entity_id=order_id,
                                    new={"name": p["name_en"], "price_paisa": p["unit_price"].paisa,
                                         "qty_milli": p["qty"].milli})
            for method, amount in payments:
                self._repo.insert_payment(order_id, method, amount.paisa)
            self._audit.log(actor, "sale.checkout", entity="order", entity_id=order_id,
                            new={"bill_no": bill_no, "payable_paisa": totals.payable.paisa,
                                 "discount_paisa": totals.total_discount.paisa, "lines": len(prepared),
                                 "payments": {m: a.paisa for m, a in payments}})
        return self.get(order_id)

    def _prepare(self, line) -> dict:
        if line.item_id is None:   # Misc item: a one-off with a typed name and price
            name = (line.misc_name or "").strip()
            if not name:
                raise ValidationError("error.name_required")
            if line.misc_price is None or line.misc_price.paisa < 0:
                raise ValidationError("error.price_invalid")
            if line.qty.milli <= 0:
                raise ValidationError("error.quantity_invalid")
            item_fields = dict(item_id=None, name_en=name, name_ur=None, unit="piece", unit_price=line.misc_price,
                               cost=Money(0), mode="qty", qty=line.qty)
            gross = line_gross(line.misc_price, line.qty, "qty", None)
        else:
            row = self._items.get(line.item_id)
            if row is None:
                raise ValueError(f"no such item {line.item_id}")
            item: Item = to_item(row)
            if not item.is_active:
                raise ValidationError("error.item_inactive", name=item.name_en)
            qty, mode, amount = line.qty, line.mode, line.amount
            if mode == "amount":
                if not item.allow_fraction:
                    raise ValidationError("error.fraction_not_allowed")
                if amount is None or amount.paisa <= 0 or item.sale.paisa <= 0:
                    raise ValidationError("error.price_invalid")
                qty = Quantity.for_amount(amount, item.sale)   # exact amount, rounded quantity
            if qty.milli <= 0:
                raise ValidationError("error.quantity_invalid")
            if not item.allow_fraction and not qty.is_whole:
                raise ValidationError("error.fraction_not_allowed")
            item_fields = dict(item_id=item.id, name_en=item.name_en, name_ur=item.name_ur, unit=item.unit,
                               unit_price=item.sale, cost=item.cost, mode=mode, qty=qty)
            gross = line_gross(item.sale, qty, mode, amount)
        discount_amount(gross, line.discount)   # validates early so the error names the right problem
        return {**item_fields, "gross": gross, "discount": line.discount}

    # ---- reading -------------------------------------------------------------------
    def get(self, order_id: int) -> Order | None:
        row = self._repo.get(order_id)
        return _order_from_rows(row, self._repo.lines(order_id), self._repo.payments(order_id)) if row else None

    def get_by_bill_no(self, bill_no: int) -> Order | None:
        row = self._repo.get_by_bill_no(bill_no)
        return self.get(row["id"]) if row else None

    def list(self, date_from: str | None = None, date_to: str | None = None, limit: int = 500) -> list[Order]:
        return [_order_from_rows(r) for r in self._repo.search(date_from, date_to, limit)]


class HeldBillService:
    """Bills put on hold are stored in the database, so a restart or power cut loses nothing."""

    def __init__(self, conn: sqlite3.Connection, audit: AuditService, items: Callable[[int], Item | None]) -> None:
        self._conn = conn
        self._repo = HeldBillRepo(conn)
        self._audit = audit
        self._lookup = items

    def hold(self, actor: User, cart: Cart, label: str) -> int:
        if cart.is_empty:
            raise ValidationError("error.cart_empty")
        with atomic(self._conn):
            held_id = self._repo.insert(actor.id, label.strip() or "-", json.dumps(cart.to_dict(), ensure_ascii=False))
            self._audit.log(actor, "bill.hold", entity="held_bill", entity_id=held_id, new={"lines": len(cart.lines)})
        return held_id

    def list(self) -> list[dict]:
        out = []
        for r in self._repo.list():
            data = json.loads(r["cart_json"])
            out.append({"id": r["id"], "label": r["label"], "created_at": r["created_at"],
                        "cashier_name": r["cashier_name"], "line_count": len(data.get("lines", []))})
        return out

    def resume(self, actor: User, held_id: int) -> tuple[Cart, list[str]]:
        """Take a held bill back. It is removed from the held list; items that no longer exist are reported."""
        row = self._repo.get(held_id)
        if row is None:
            raise ValueError("no such held bill")
        cart, dropped = Cart.from_dict(json.loads(row["cart_json"]), self._lookup)
        with atomic(self._conn):
            self._repo.delete(held_id)
            self._audit.log(actor, "bill.resume", entity="held_bill", entity_id=held_id, new={"dropped": dropped})
        return cart, dropped

    def discard(self, actor: User, held_id: int) -> None:
        if self._repo.get(held_id) is None:
            raise ValueError("no such held bill")
        with atomic(self._conn):
            self._repo.delete(held_id)
            self._audit.log(actor, "bill.discard", entity="held_bill", entity_id=held_id)
