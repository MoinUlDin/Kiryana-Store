from __future__ import annotations

import sqlite3


class AuditRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, **cols: object) -> None:
        names = ", ".join(cols)
        marks = ", ".join("?" for _ in cols)
        self._conn.execute(f"INSERT INTO audit_log({names}) VALUES ({marks})", tuple(cols.values()))

    def recent(self, limit: int = 100) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
