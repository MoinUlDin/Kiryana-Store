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
