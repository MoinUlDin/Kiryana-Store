from __future__ import annotations

import sqlite3

from app.db.connection import transaction


class SettingsRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str, user_id: int | None = None) -> None:
        with transaction(self._conn):
            self._conn.execute(
                """INSERT INTO settings(key, value, updated_by) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                     value = excluded.value,
                     updated_by = excluded.updated_by,
                     updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
                (key, value, user_id),
            )
