from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.db.connection import atomic
from app.domain.user import User
from app.repositories.named_list_repo import NamedListRepo
from app.security.passwords import ValidationError
from app.services.audit_service import AuditService


@dataclass(frozen=True)
class NamedEntry:
    id: int
    name_en: str
    name_ur: str | None

    def display(self, lang: str) -> str:
        return self.name_ur if (lang == "ur" and self.name_ur) else self.name_en


class NamedListService:
    """Categories and brands. `entity` is the audit label ('category' or 'brand')."""

    def __init__(self, conn: sqlite3.Connection, audit: AuditService, table: str, entity: str) -> None:
        self._conn = conn
        self._repo = NamedListRepo(conn, table)
        self._audit = audit
        self._entity = entity

    @staticmethod
    def _entry(row: sqlite3.Row) -> NamedEntry:
        return NamedEntry(row["id"], row["name_en"], row["name_ur"])

    def list(self, include_inactive: bool = False) -> list[NamedEntry]:
        return [self._entry(r) for r in self._repo.list(include_inactive)]

    @staticmethod
    def _clean(name_en: str, name_ur: str | None) -> tuple[str, str | None]:
        name_en = name_en.strip()
        if not name_en:
            raise ValidationError("error.name_required")
        return name_en, (name_ur or "").strip() or None

    def add(self, actor: User, name_en: str, name_ur: str | None = None) -> NamedEntry:
        name_en, name_ur = self._clean(name_en, name_ur)
        try:
            with atomic(self._conn):
                row_id = self._repo.insert(name_en, name_ur)
                self._audit.log(actor, f"{self._entity}.create", entity=self._entity, entity_id=row_id,
                                new={"name_en": name_en, "name_ur": name_ur})
        except sqlite3.IntegrityError as exc:
            raise ValidationError("error.list_exists") from exc
        return NamedEntry(row_id, name_en, name_ur)

    def rename(self, actor: User, row_id: int, name_en: str, name_ur: str | None = None) -> None:
        old = self._repo.get(row_id)
        if old is None:
            raise ValueError("no such entry")
        name_en, name_ur = self._clean(name_en, name_ur)
        try:
            with atomic(self._conn):
                self._repo.update(row_id, name_en, name_ur)
                self._audit.log(actor, f"{self._entity}.rename", entity=self._entity, entity_id=row_id,
                                old={"name_en": old["name_en"], "name_ur": old["name_ur"]},
                                new={"name_en": name_en, "name_ur": name_ur})
        except sqlite3.IntegrityError as exc:
            raise ValidationError("error.list_exists") from exc

    def delete(self, actor: User, row_id: int) -> None:
        old = self._repo.get(row_id)
        if old is None:
            raise ValueError("no such entry")
        if self._repo.usage_count(row_id) > 0:
            raise ValidationError("error.list_in_use")
        with atomic(self._conn):
            self._repo.delete(row_id)
            self._audit.log(actor, f"{self._entity}.delete", entity=self._entity, entity_id=row_id,
                            old={"name_en": old["name_en"]})
