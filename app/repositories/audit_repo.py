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

    def search(self, pattern: str | None, limit: int, before_id: int | None) -> list[sqlite3.Row]:
        clauses, params = [], []
        if pattern:
            clauses.append("(action LIKE ? ESCAPE '\\' OR username LIKE ? ESCAPE '\\' OR reason LIKE ? ESCAPE '\\')")
            params += [pattern, pattern, pattern]
        if before_id is not None:
            clauses.append("id < ?")
            params.append(before_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return self._conn.execute(
            f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ?", (*params, limit)
        ).fetchall()
