from __future__ import annotations

import sqlite3


class SaleRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def next_bill_no(self) -> int:
        self._conn.execute("UPDATE bill_counter SET last_bill_no = last_bill_no + 1 WHERE id = 1")
        return self._conn.execute("SELECT last_bill_no FROM bill_counter WHERE id = 1").fetchone()[0]

    def insert_order(self, **cols: object) -> int:
        names = ", ".join(cols)
        marks = ", ".join("?" for _ in cols)
        cur = self._conn.execute(f"INSERT INTO orders({names}) VALUES ({marks})", tuple(cols.values()))
        return int(cur.lastrowid)

    def insert_line(self, **cols: object) -> int:
        names = ", ".join(cols)
        marks = ", ".join("?" for _ in cols)
        cur = self._conn.execute(f"INSERT INTO order_lines({names}) VALUES ({marks})", tuple(cols.values()))
        return int(cur.lastrowid)

    def insert_payment(self, order_id: int, method: str, amount_paisa: int) -> None:
        self._conn.execute("INSERT INTO payments(order_id, method, amount_paisa) VALUES (?, ?, ?)",
                           (order_id, method, amount_paisa))

    def get(self, order_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT o.*, u.display_name AS cashier_name FROM orders o LEFT JOIN users u ON u.id = o.cashier_id WHERE o.id = ?",
            (order_id,)).fetchone()

    def get_by_bill_no(self, bill_no: int) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT o.*, u.display_name AS cashier_name FROM orders o LEFT JOIN users u ON u.id = o.cashier_id WHERE o.bill_no = ?",
            (bill_no,)).fetchone()

    def lines(self, order_id: int) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM order_lines WHERE order_id = ? ORDER BY id", (order_id,)).fetchall()

    def payments(self, order_id: int) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM payments WHERE order_id = ? ORDER BY id", (order_id,)).fetchall()

    def search(self, date_from: str | None, date_to: str | None, limit: int) -> list[sqlite3.Row]:
        clauses, params = [], []
        if date_from:
            clauses.append("o.business_date >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("o.business_date <= ?")
            params.append(date_to)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return self._conn.execute(
            f"SELECT o.*, u.display_name AS cashier_name FROM orders o LEFT JOIN users u ON u.id = o.cashier_id "
            f"{where} ORDER BY o.id DESC LIMIT ?", (*params, limit)).fetchall()


class HeldBillRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, cashier_id: int, label: str, cart_json: str) -> int:
        cur = self._conn.execute("INSERT INTO held_bills(cashier_id, label, cart_json) VALUES (?, ?, ?)",
                                 (cashier_id, label, cart_json))
        return int(cur.lastrowid)

    def list(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT h.*, u.display_name AS cashier_name FROM held_bills h LEFT JOIN users u ON u.id = h.cashier_id "
            "ORDER BY h.id").fetchall()

    def get(self, held_id: int) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM held_bills WHERE id = ?", (held_id,)).fetchone()

    def delete(self, held_id: int) -> None:
        self._conn.execute("DELETE FROM held_bills WHERE id = ?", (held_id,))
