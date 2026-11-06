from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.db.connection import atomic
from app.domain.user import User
from app.repositories.supplier_repo import SupplierRepo
from app.security.passwords import ValidationError
from app.services.audit_service import AuditService


@dataclass(frozen=True)
class Supplier:
    id: int
    name: str
    phone: str | None
    address: str | None
    note: str | None
    is_active: bool


def _to_supplier(row: sqlite3.Row) -> Supplier:
    return Supplier(row["id"], row["name"], row["phone"], row["address"], row["note"], bool(row["is_active"]))


class SupplierService:
    def __init__(self, conn: sqlite3.Connection, audit: AuditService) -> None:
        self._conn = conn
        self._repo = SupplierRepo(conn)
        self._audit = audit

    def list(self, include_inactive: bool = False) -> list[Supplier]:
        return [_to_supplier(r) for r in self._repo.list(include_inactive)]

    def get(self, supplier_id: int) -> Supplier | None:
        row = self._repo.get(supplier_id)
        return _to_supplier(row) if row else None

    @staticmethod
    def _clean(name: str, phone: str | None, address: str | None, note: str | None):
        name = name.strip()
        if not name:
            raise ValidationError("error.name_required")
        return name, (phone or "").strip() or None, (address or "").strip() or None, (note or "").strip() or None

    def add(self, actor: User, name: str, phone: str | None = None, address: str | None = None,
            note: str | None = None) -> Supplier:
        name, phone, address, note = self._clean(name, phone, address, note)
        try:
            with atomic(self._conn):
                supplier_id = self._repo.insert(name, phone, address, note)
                self._audit.log(actor, "supplier.create", entity="supplier", entity_id=supplier_id, new={"name": name})
        except sqlite3.IntegrityError as exc:
            raise ValidationError("error.list_exists") from exc
        return self.get(supplier_id)

    def update(self, actor: User, supplier_id: int, name: str, phone: str | None = None,
               address: str | None = None, note: str | None = None) -> Supplier:
        old = self._repo.get(supplier_id)
        if old is None:
            raise ValueError("no such supplier")
        name, phone, address, note = self._clean(name, phone, address, note)
        try:
            with atomic(self._conn):
                self._repo.update(supplier_id, name, phone, address, note)
                self._audit.log(actor, "supplier.update", entity="supplier", entity_id=supplier_id,
                                old={"name": old["name"], "phone": old["phone"]}, new={"name": name, "phone": phone})
        except sqlite3.IntegrityError as exc:
            raise ValidationError("error.list_exists") from exc
        return self.get(supplier_id)

    def set_active(self, actor: User, supplier_id: int, active: bool) -> None:
        if self._repo.get(supplier_id) is None:
            raise ValueError("no such supplier")
        with atomic(self._conn):
            self._repo.set_active(supplier_id, active)
            self._audit.log(actor, "supplier.activate" if active else "supplier.deactivate",
                            entity="supplier", entity_id=supplier_id)
