from __future__ import annotations

import sqlite3


class StockRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_batch(self, item_id: int, source: str, qty_milli: int, cost_paisa: int, expiry: str | None,
                     purchase_line_id: int | None = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO item_batches(item_id, source, qty_in_milli, qty_left_milli, cost_paisa, expiry_date, purchase_line_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item_id, source, qty_milli, qty_milli, cost_paisa, expiry, purchase_line_id),
        )
        return int(cur.lastrowid)

    def get_batch(self, batch_id: int) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM item_batches WHERE id = ?", (batch_id,)).fetchone()

    def expiry_rows(self, last_date: str | None, today: str, expired_only: bool) -> list[sqlite3.Row]:
        """Batches that still hold stock and have an expiry date, soonest first."""
        clauses, params = ["b.qty_left_milli > 0", "b.expiry_date IS NOT NULL"], []
        if expired_only:
            clauses.append("b.expiry_date < ?")
            params.append(today)
        elif last_date is not None:
            clauses.append("b.expiry_date <= ?")
            params.append(last_date)
        return self._conn.execute(
            f"""SELECT b.id AS batch_id, b.qty_left_milli, b.expiry_date, i.id AS item_id, i.name_en, i.name_ur,
                       i.short_code, i.unit
                FROM item_batches b JOIN items i ON i.id = b.item_id
                WHERE {' AND '.join(clauses)} ORDER BY b.expiry_date, i.name_en COLLATE NOCASE""",
            params,
        ).fetchall()

    def fifo_batches(self, item_id: int) -> list[sqlite3.Row]:
        """Earliest expiry first; batches without an expiry last; then oldest first."""
        return self._conn.execute(
            """SELECT * FROM item_batches WHERE item_id = ? AND qty_left_milli > 0
               ORDER BY (expiry_date IS NULL), expiry_date, received_at, id""",
            (item_id,),
        ).fetchall()

    def reduce_batch(self, batch_id: int, take_milli: int) -> None:
        self._conn.execute("UPDATE item_batches SET qty_left_milli = qty_left_milli - ? WHERE id = ?", (take_milli, batch_id))

    def add_to_item_stock(self, item_id: int, delta_milli: int) -> None:
        self._conn.execute("UPDATE items SET stock_milli = stock_milli + ? WHERE id = ?", (delta_milli, item_id))

    def insert_movement(self, item_id: int, batch_id: int | None, kind: str, qty_milli: int,
                        ref_type: str | None, ref_id: int | None, reason: str | None, user_id: int | None) -> None:
        self._conn.execute(
            "INSERT INTO stock_movements(item_id, batch_id, kind, qty_milli, ref_type, ref_id, reason, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, batch_id, kind, qty_milli, ref_type, ref_id, reason, user_id),
        )

    def movements(self, item_id: int, limit: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            """SELECT m.*, u.username FROM stock_movements m LEFT JOIN users u ON u.id = m.user_id
               WHERE m.item_id = ? ORDER BY m.id DESC LIMIT ?""",
            (item_id, limit),
        ).fetchall()

    def invariant_violations(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            """SELECT i.id, i.stock_milli,
                      COALESCE((SELECT SUM(qty_left_milli) FROM item_batches b WHERE b.item_id = i.id), 0) AS in_batches,
                      COALESCE((SELECT SUM(qty_milli) FROM stock_movements m WHERE m.item_id = i.id), 0) AS in_movements
               FROM items i
               WHERE i.stock_milli <> in_batches OR i.stock_milli <> in_movements"""
        ).fetchall()
