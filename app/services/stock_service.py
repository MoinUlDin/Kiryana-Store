from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.db.connection import atomic
from app.domain.money import Money
from app.domain.quantity import Quantity
from app.domain.user import User
from app.repositories.item_repo import ItemRepo
from app.repositories.stock_repo import StockRepo
from app.security.passwords import ValidationError
from app.services.audit_service import AuditService

# reason category chosen in the adjust dialog -> stock_movements.kind
ADJUST_KINDS = {
    "damage": "adjust_damage",
    "loss": "adjust_loss",
    "expiry": "adjust_expiry",
    "count": "adjust_count",
}
DECREASE_ONLY = ("damage", "loss", "expiry")


@dataclass(frozen=True)
class Consumption:
    batch_id: int
    qty: Quantity
    cost: Money  # the batch's cost, handy for profit later


@dataclass(frozen=True)
class AdjustResult:
    old: Quantity
    new: Quantity

    @property
    def changed(self) -> bool:
        return self.old != self.new


@dataclass(frozen=True)
class Movement:
    id: int
    kind: str
    qty: Quantity
    reason: str | None
    username: str | None
    created_at: str


class StockService:
    """The only code allowed to change stock. Each method is one transaction and keeps
    items.stock_milli == SUM(batches) == SUM(movements)."""

    def __init__(self, conn: sqlite3.Connection, audit: AuditService) -> None:
        self._conn = conn
        self._items = ItemRepo(conn)
        self._stock = StockRepo(conn)
        self._audit = audit

    # ---- helpers ---------------------------------------------------------
    def _item(self, item_id: int) -> sqlite3.Row:
        row = self._items.get(item_id)
        if row is None:
            raise ValueError(f"no such item {item_id}")
        return row

    @staticmethod
    def _check_quantity(row: sqlite3.Row, qty: Quantity) -> None:
        if qty.milli <= 0:
            raise ValidationError("error.quantity_invalid")
        if not row["allow_fraction"] and not qty.is_whole:
            raise ValidationError("error.fraction_not_allowed")

    @staticmethod
    def _uid(actor: User | None) -> int | None:
        return (actor.id or None) if actor else None

    # ---- receiving -------------------------------------------------------
    def receive(self, actor: User | None, item_id: int, qty: Quantity, cost: Money, *, kind: str = "opening",
                source: str = "opening", expiry: str | None = None, ref_type: str | None = None,
                ref_id: int | None = None, reason: str | None = None, purchase_line_id: int | None = None) -> int:
        """Add stock as a new batch. Used for opening stock, purchases and upward corrections."""
        row = self._item(item_id)
        self._check_quantity(row, qty)
        with atomic(self._conn):
            batch_id = self._stock.insert_batch(item_id, source, qty.milli, cost.paisa, expiry, purchase_line_id)
            self._stock.add_to_item_stock(item_id, qty.milli)
            self._stock.insert_movement(item_id, batch_id, kind, qty.milli, ref_type, ref_id, reason, self._uid(actor))
        return batch_id

    # ---- consuming -------------------------------------------------------
    def consume(self, actor: User | None, item_id: int, qty: Quantity, kind: str, *, ref_type: str | None = None,
                ref_id: int | None = None, reason: str | None = None) -> list[Consumption]:
        """Take stock out, earliest expiry first. Raises if there is not enough."""
        row = self._item(item_id)
        self._check_quantity(row, qty)
        if qty.milli > row["stock_milli"]:
            raise ValidationError("error.stock_insufficient")
        taken: list[Consumption] = []
        remaining = qty.milli
        with atomic(self._conn):
            for batch in self._stock.fifo_batches(item_id):
                if remaining == 0:
                    break
                take = min(remaining, batch["qty_left_milli"])
                self._stock.reduce_batch(batch["id"], take)
                self._stock.insert_movement(item_id, batch["id"], kind, -take, ref_type, ref_id, reason, self._uid(actor))
                taken.append(Consumption(batch["id"], Quantity(take), Money(batch["cost_paisa"])))
                remaining -= take
            if remaining:  # batches and item stock disagree: refuse rather than corrupt anything
                raise RuntimeError("stock invariant violated: batches hold less than items.stock_milli")
            self._stock.add_to_item_stock(item_id, -qty.milli)
        return taken

    # ---- adjustments -----------------------------------------------------
    def adjust(self, actor: User, item_id: int, reason_kind: str, quantity: Quantity,
               note: str | None = None) -> AdjustResult:
        """damage / loss / expiry: `quantity` is how much to remove.
        count: `quantity` is the number actually counted on the shelf (can raise or lower stock)."""
        if reason_kind not in ADJUST_KINDS:
            raise ValueError(f"unknown adjustment kind {reason_kind!r}")
        if reason_kind in DECREASE_ONLY:
            return self._decrease(actor, item_id, ADJUST_KINDS[reason_kind], quantity, note, "stock.adjust", reason_kind)
        return self._set_count(actor, item_id, "adjust_count", quantity, note, "stock.adjust")

    def quick_fix(self, actor: User, item_id: int, counted: Quantity, note: str | None = None) -> AdjustResult:
        """From the sale screen: the shelf has stock but the system says 0 (or too little)."""
        return self._set_count(actor, item_id, "quick_fix", counted, note, "stock.quick_fix")

    def _decrease(self, actor, item_id, kind, quantity, note, audit_action, label) -> AdjustResult:
        row = self._item(item_id)
        old = Quantity(row["stock_milli"])
        with atomic(self._conn):
            self.consume(actor, item_id, quantity, kind, reason=note)
            result = AdjustResult(old, old - quantity)
            self._audit.log(actor, audit_action, entity="item", entity_id=item_id, reason=note or label,
                            old={"stock_milli": old.milli}, new={"stock_milli": result.new.milli, "kind": label})
        return result

    def _set_count(self, actor, item_id, kind, counted, note, audit_action) -> AdjustResult:
        row = self._item(item_id)
        old = Quantity(row["stock_milli"])
        if counted.milli < 0:
            raise ValidationError("error.quantity_invalid")
        if not row["allow_fraction"] and not counted.is_whole:
            raise ValidationError("error.fraction_not_allowed")
        delta = counted.milli - old.milli
        if delta == 0:
            return AdjustResult(old, old)
        with atomic(self._conn):
            if delta > 0:
                self.receive(actor, item_id, Quantity(delta), Money(row["cost_paisa"]), kind=kind,
                             source="adjustment", reason=note)
            else:
                self.consume(actor, item_id, Quantity(-delta), kind, reason=note)
            self._audit.log(actor, audit_action, entity="item", entity_id=item_id, reason=note or kind,
                            old={"stock_milli": old.milli}, new={"stock_milli": counted.milli, "kind": kind})
        return AdjustResult(old, counted)

    def write_off_batch(self, actor: User, batch_id: int, note: str | None = None) -> Quantity:
        """Remove everything left in ONE batch (for example an expired one), whatever its position in the queue."""
        batch = self._stock.get_batch(batch_id)
        if batch is None:
            raise ValueError("no such batch")
        left = batch["qty_left_milli"]
        if left <= 0:
            raise ValidationError("error.quantity_invalid")
        with atomic(self._conn):
            self._stock.reduce_batch(batch_id, left)
            self._stock.add_to_item_stock(batch["item_id"], -left)
            self._stock.insert_movement(batch["item_id"], batch_id, "adjust_expiry", -left, None, None,
                                        note, self._uid(actor))
            self._audit.log(actor, "stock.adjust", entity="item", entity_id=batch["item_id"],
                            reason=note or "expiry write-off",
                            new={"batch_id": batch_id, "written_off_milli": left, "kind": "expiry"})
        return Quantity(left)

    # ---- reading ---------------------------------------------------------
    def movements(self, item_id: int, limit: int = 200) -> list[Movement]:
        return [Movement(r["id"], r["kind"], Quantity(r["qty_milli"]), r["reason"], r["username"], r["created_at"])
                for r in self._stock.movements(item_id, limit)]

    def check_invariants(self) -> list[str]:
        """Empty list = healthy. Run at startup and in tests after every stock operation."""
        return [
            f"item {r['id']}: stock {r['stock_milli']} but batches hold {r['in_batches']} and movements sum to {r['in_movements']}"
            for r in self._stock.invariant_violations()
        ]
