from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.domain.user import User
from app.repositories.audit_repo import AuditRepo


def _dump(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class AuditService:
    """Append-only trail. Never pass secrets (passwords, PINs) in old/new."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._repo = AuditRepo(conn)

    def log(
        self, actor: User | None, action: str, *, entity: str | None = None, entity_id: int | None = None,
        old: Any = None, new: Any = None, reason: str | None = None,
        approved_by: str | None = None, approval_method: str | None = None,
    ) -> None:
        self._repo.insert(
            user_id=(actor.id or None) if actor else None,
            username=actor.username if actor else None,
            action=action, entity=entity, entity_id=entity_id,
            old_json=_dump(old), new_json=_dump(new), reason=reason,
            approved_by=approved_by, approval_method=approval_method,
        )

    def recent(self, limit: int = 100):
        return self._repo.recent(limit)

    def search(self, text: str = "", limit: int = 200, before_id: int | None = None) -> list[sqlite3.Row]:
        """Newest first. `before_id` pages backwards: pass the smallest id you already have."""
        text = text.strip()
        pattern = None
        if text:
            escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
        return self._repo.search(pattern, limit, before_id)


def describe_entry(row: sqlite3.Row) -> str:
    """One readable line for the audit viewer."""
    parts = []
    if row["entity"]:
        parts.append(f"{row['entity']}#{row['entity_id']}" if row["entity_id"] else str(row["entity"]))
    if row["reason"]:
        parts.append(str(row["reason"]))
    if row["old_json"] or row["new_json"]:
        old, new = row["old_json"], row["new_json"]
        parts.append(f"{old} -> {new}" if old and new else (new or old))
    if row["approved_by"]:
        parts.append(f"approved by {row['approved_by']} ({row['approval_method']})")
    return " | ".join(parts)
