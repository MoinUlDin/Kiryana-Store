from __future__ import annotations

import sqlite3


class PermissionRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_default(self, role: str, key: str, allowed: bool, ask: bool) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO role_permissions(role, perm_key, allowed, ask_password) VALUES (?, ?, ?, ?)",
            (role, key, int(allowed), int(ask)),
        )

    def get(self, role: str, key: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT allowed, ask_password FROM role_permissions WHERE role = ? AND perm_key = ?", (role, key)
        ).fetchone()

    def list(self, role: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT perm_key, allowed, ask_password FROM role_permissions WHERE role = ? ORDER BY perm_key", (role,)
        ).fetchall()

    def update(self, role: str, key: str, allowed: bool, ask: bool) -> None:
        self._conn.execute(
            "UPDATE role_permissions SET allowed = ?, ask_password = ? WHERE role = ? AND perm_key = ?",
            (int(allowed), int(ask), role, key),
        )
