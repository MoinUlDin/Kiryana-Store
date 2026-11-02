from __future__ import annotations

import sqlite3

NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"


class UserRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, user_id: int) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def get_by_username(self, username: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()

    def insert(self, username: str, display_name: str, role: str, password_hash: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO users(username, display_name, role, password_hash) VALUES (?, ?, ?, ?)",
            (username, display_name, role, password_hash),
        )
        return int(cur.lastrowid)

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def count_role(self, role: str) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM users WHERE role = ?", (role,)).fetchone()[0]

    def list(self, active_only: bool = True) -> list[sqlite3.Row]:
        where = "WHERE is_active = 1" if active_only else ""
        return self._conn.execute(f"SELECT * FROM users {where} ORDER BY display_name COLLATE NOCASE").fetchall()

    def active_admins(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM users WHERE is_active = 1 AND role IN ('owner', 'superadmin')"
        ).fetchall()

    def set_password(self, user_id: int, password_hash: str) -> None:
        self._conn.execute(
            f"UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = NULL, updated_at = {NOW} WHERE id = ?",
            (password_hash, user_id),
        )

    def record_failure(self, user_id: int, attempts: int, locked_until: str | None) -> None:
        self._conn.execute(
            "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
            (attempts, locked_until, user_id),
        )

    def record_success(self, user_id: int, at_iso: str) -> None:
        self._conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = ? WHERE id = ?",
            (at_iso, user_id),
        )

    def set_active(self, user_id: int, active: bool) -> None:
        self._conn.execute(
            f"UPDATE users SET is_active = ?, updated_at = {NOW} WHERE id = ?", (1 if active else 0, user_id)
        )
