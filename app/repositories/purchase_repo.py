from __future__ import annotations

import sqlite3


class PurchaseRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, supplier_id, invoice_no, purchase_date, total, paid, paid_method, note, created_by) -> int:
        cur = self._conn.execute(
            """INSERT INTO purchases(supplier_id, invoice_no, purchase_date, total_paisa, paid_paisa,
                                     paid_method, note, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (supplier_id, invoice_no, purchase_date, total, paid, paid_method, note, created_by),
        )
        return int(cur.lastrowid)

    def insert_line(self, purchase_id, item_id, qty_milli, cost, line_total, expiry, avg_before, avg_after) -> int:
        cur = self._conn.execute(
            """INSERT INTO purchase_lines(purchase_id, item_id, qty_milli, cost_paisa, line_total_paisa,
                                          expiry_date, avg_cost_before, avg_cost_after)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (purchase_id, item_id, qty_milli, cost, line_total, expiry, avg_before, avg_after),
        )
        return int(cur.lastrowid)

    def link_batch(self, line_id: int, batch_id: int) -> None:
        self._conn.execute("UPDATE purchase_lines SET batch_id = ? WHERE id = ?", (batch_id, line_id))

    def invoice_exists(self, supplier_id: int, invoice_no: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM purchases WHERE supplier_id = ? AND invoice_no = ?", (supplier_id, invoice_no)
        ).fetchone() is not None

    def get(self, purchase_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            """SELECT p.*, s.name AS supplier_name, u.username AS created_by_name
               FROM purchases p LEFT JOIN suppliers s ON s.id = p.supplier_id
               LEFT JOIN users u ON u.id = p.created_by WHERE p.id = ?""",
            (purchase_id,),
        ).fetchone()

    def lines(self, purchase_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            """SELECT l.*, i.name_en, i.name_ur, i.short_code, i.unit FROM purchase_lines l
               JOIN items i ON i.id = l.item_id WHERE l.purchase_id = ? ORDER BY l.id""",
            (purchase_id,),
        ).fetchall()

    def search(self, date_from: str | None, date_to: str | None, supplier_id: int | None,
               pattern: str | None, limit: int) -> list[sqlite3.Row]:
        clauses, params = [], []
        if date_from:
            clauses.append("p.purchase_date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("p.purchase_date <= ?")
            params.append(date_to)
        if supplier_id is not None:
            clauses.append("p.supplier_id = ?")
            params.append(supplier_id)
        if pattern:
            clauses.append("(p.invoice_no LIKE ? ESCAPE '\\' OR s.name LIKE ? ESCAPE '\\')")
            params += [pattern, pattern]
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return self._conn.execute(
            f"""SELECT p.*, s.name AS supplier_name, u.username AS created_by_name
                FROM purchases p LEFT JOIN suppliers s ON s.id = p.supplier_id
                LEFT JOIN users u ON u.id = p.created_by {where}
                ORDER BY p.purchase_date DESC, p.id DESC LIMIT ?""",
            (*params, limit),
        ).fetchall()
