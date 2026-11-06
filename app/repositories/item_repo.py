from __future__ import annotations

import sqlite3

_COLUMNS = ("name_en", "name_ur", "short_code", "barcode", "category_id", "brand_id", "unit",
            "allow_fraction", "cost_paisa", "sale_paisa", "tax_bp", "low_stock_milli", "search_key")
NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"


def _like(token: str) -> str:
    return "%" + token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class ItemRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, item_id: int) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()

    def find_code(self, code: str) -> sqlite3.Row | None:
        """Exact barcode first, then short code."""
        row = self._conn.execute("SELECT * FROM items WHERE barcode = ?", (code,)).fetchone()
        return row or self._conn.execute("SELECT * FROM items WHERE short_code = ? COLLATE NOCASE", (code,)).fetchone()

    def code_conflicts(self, value: str, exclude_id: int | None) -> dict[str, bool]:
        """Is `value` already used as someone's short code or barcode?"""
        exclude = -1 if exclude_id is None else exclude_id
        as_code = self._conn.execute(
            "SELECT 1 FROM items WHERE short_code = ? COLLATE NOCASE AND id <> ?", (value, exclude)).fetchone()
        as_barcode = self._conn.execute(
            "SELECT 1 FROM items WHERE barcode = ? AND id <> ?", (value, exclude)).fetchone()
        return {"short_code": bool(as_code), "barcode": bool(as_barcode)}

    def insert(self, values: dict) -> int:
        names = ", ".join(_COLUMNS)
        marks = ", ".join("?" for _ in _COLUMNS)
        cur = self._conn.execute(f"INSERT INTO items({names}) VALUES ({marks})", tuple(values[c] for c in _COLUMNS))
        return int(cur.lastrowid)

    def update(self, item_id: int, values: dict) -> None:
        sets = ", ".join(f"{c} = ?" for c in _COLUMNS)
        self._conn.execute(f"UPDATE items SET {sets}, updated_at = {NOW} WHERE id = ?",
                           (*(values[c] for c in _COLUMNS), item_id))

    def set_cost(self, item_id: int, cost_paisa: int) -> None:
        self._conn.execute(f"UPDATE items SET cost_paisa = ?, updated_at = {NOW} WHERE id = ?", (cost_paisa, item_id))

    def set_sale(self, item_id: int, sale_paisa: int) -> None:
        self._conn.execute(f"UPDATE items SET sale_paisa = ?, updated_at = {NOW} WHERE id = ?", (sale_paisa, item_id))

    def set_active(self, item_id: int, active: bool) -> None:
        self._conn.execute(f"UPDATE items SET is_active = ?, updated_at = {NOW} WHERE id = ?", (int(active), item_id))

    def get_by_short_code(self, code: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM items WHERE short_code = ? COLLATE NOCASE", (code,)).fetchone()

    def reference_count(self, item_id: int) -> int:
        """Rows elsewhere that point at this item. Zero means it can be deleted for real."""
        return self._conn.execute(
            """SELECT (SELECT COUNT(*) FROM stock_movements WHERE item_id = :i)
                    + (SELECT COUNT(*) FROM item_batches    WHERE item_id = :i)
                    + (SELECT COUNT(*) FROM purchase_lines  WHERE item_id = :i)
                    + (SELECT COUNT(*) FROM order_lines     WHERE item_id = :i)""",
            {"i": item_id},
        ).fetchone()[0]

    def delete(self, item_id: int) -> None:
        self._conn.execute("DELETE FROM items WHERE id = ?", (item_id,))

    def movement_count(self, item_id: int) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM stock_movements WHERE item_id = ?", (item_id,)).fetchone()[0]

    def search(self, tokens: list[str], exact: str, category_id: int | None, low_only: bool,
               include_inactive: bool, limit: int) -> list[sqlite3.Row]:
        clauses, params = [], []
        for token in tokens:
            clauses.append("search_key LIKE ? ESCAPE '\\'")
            params.append(_like(token))
        if category_id is not None:
            clauses.append("category_id = ?")
            params.append(category_id)
        if low_only:
            clauses.append("low_stock_milli > 0 AND stock_milli <= low_stock_milli")
        if not include_inactive:
            clauses.append("is_active = 1")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return self._conn.execute(
            f"""SELECT * FROM items {where}
                ORDER BY (short_code = ? COLLATE NOCASE OR barcode = ?) DESC, name_en COLLATE NOCASE
                LIMIT ?""",
            (*params, exact, exact, limit),
        ).fetchall()
