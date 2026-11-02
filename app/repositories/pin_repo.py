from __future__ import annotations

import sqlite3


class PinRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, owner_id: int, label: str, pin_hash: str, allowed_actions: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO approval_pins(owner_id, label, pin_hash, allowed_actions) VALUES (?, ?, ?, ?)",
            (owner_id, label, pin_hash, allowed_actions),
        )
        return int(cur.lastrowid)

    def active(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            """SELECT p.*, u.display_name AS owner_name FROM approval_pins p
               JOIN users u ON u.id = p.owner_id
               WHERE p.is_active = 1 AND u.is_active = 1"""
        ).fetchall()

    def get(self, pin_id: int) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM approval_pins WHERE id = ?", (pin_id,)).fetchone()

    def revoke(self, pin_id: int) -> None:
        self._conn.execute(
            "UPDATE approval_pins SET is_active = 0, revoked_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (pin_id,),
        )
