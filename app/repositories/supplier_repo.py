from __future__ import annotations

import sqlite3


class SupplierRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list(self, include_inactive: bool = False) -> list[sqlite3.Row]:
        where = "" if include_inactive else "WHERE is_active = 1"
        return self._conn.execute(f"SELECT * FROM suppliers {where} ORDER BY name COLLATE NOCASE").fetchall()

    def get(self, supplier_id: int) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()

    def insert(self, name: str, phone: str | None, address: str | None, note: str | None) -> int:
        cur = self._conn.execute("INSERT INTO suppliers(name, phone, address, note) VALUES (?, ?, ?, ?)",
                                 (name, phone, address, note))
        return int(cur.lastrowid)

    def update(self, supplier_id: int, name: str, phone: str | None, address: str | None, note: str | None) -> None:
        self._conn.execute("UPDATE suppliers SET name = ?, phone = ?, address = ?, note = ? WHERE id = ?",
                           (name, phone, address, note, supplier_id))

    def set_active(self, supplier_id: int, active: bool) -> None:
        self._conn.execute("UPDATE suppliers SET is_active = ? WHERE id = ?", (int(active), supplier_id))
