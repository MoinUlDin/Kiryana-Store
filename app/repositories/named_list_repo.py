from __future__ import annotations

import sqlite3

_TABLES = {"categories": "category_id", "brands": "brand_id"}


class NamedListRepo:
    """Categories and brands share one shape, so they share one repository."""

    def __init__(self, conn: sqlite3.Connection, table: str) -> None:
        if table not in _TABLES:
            raise ValueError(table)
        self._conn = conn
        self._table = table
        self._fk = _TABLES[table]

    def list(self, include_inactive: bool = False) -> list[sqlite3.Row]:
        where = "" if include_inactive else "WHERE is_active = 1"
        return self._conn.execute(f"SELECT * FROM {self._table} {where} ORDER BY name_en COLLATE NOCASE").fetchall()

    def get(self, row_id: int) -> sqlite3.Row | None:
        return self._conn.execute(f"SELECT * FROM {self._table} WHERE id = ?", (row_id,)).fetchone()

    def insert(self, name_en: str, name_ur: str | None) -> int:
        cur = self._conn.execute(f"INSERT INTO {self._table}(name_en, name_ur) VALUES (?, ?)", (name_en, name_ur))
        return int(cur.lastrowid)

    def update(self, row_id: int, name_en: str, name_ur: str | None) -> None:
        self._conn.execute(f"UPDATE {self._table} SET name_en = ?, name_ur = ? WHERE id = ?", (name_en, name_ur, row_id))

    def delete(self, row_id: int) -> None:
        self._conn.execute(f"DELETE FROM {self._table} WHERE id = ?", (row_id,))

    def usage_count(self, row_id: int) -> int:
        return self._conn.execute(f"SELECT COUNT(*) FROM items WHERE {self._fk} = ?", (row_id,)).fetchone()[0]
