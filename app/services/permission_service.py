from __future__ import annotations

import sqlite3
from enum import Enum

from app.db.connection import atomic
from app.domain.permissions import PERMISSIONS, PERMS_BY_KEY
from app.domain.user import ROLE_CASHIER, ROLE_OWNER, ROLE_SUPERADMIN, User
from app.repositories.permission_repo import PermissionRepo
from app.services.audit_service import AuditService


class Decision(Enum):
    ALLOWED = "allowed"
    NEEDS_PASSWORD = "needs_password"      # layer 2: re-type your own password
    NEEDS_APPROVAL = "needs_approval"      # layer 1 said no, but an Owner can approve it
    DENIED = "denied"


class PermissionService:
    def __init__(self, conn: sqlite3.Connection, audit: AuditService) -> None:
        self._conn = conn
        self._repo = PermissionRepo(conn)
        self._audit = audit

    def seed_defaults(self) -> None:
        """Insert any missing rows. Existing shop overrides are never touched."""
        with atomic(self._conn):
            for perm in PERMISSIONS:
                self._repo.insert_default(ROLE_OWNER, perm.key, perm.owner_allowed, perm.ask_default or perm.locked_ask)
                self._repo.insert_default(ROLE_CASHIER, perm.key, perm.cashier_default, perm.ask_default or perm.locked_ask)

    def _flags(self, role: str, key: str) -> tuple[bool, bool]:
        perm = PERMS_BY_KEY[key]  # KeyError = programming error, on purpose
        row = self._repo.get(role, key)
        if row is None:
            allowed = perm.owner_allowed if role == ROLE_OWNER else perm.cashier_default
            ask = perm.ask_default
        else:
            allowed, ask = bool(row["allowed"]), bool(row["ask_password"])
        return allowed, ask or perm.locked_ask

    def decide(self, user: User, key: str) -> Decision:
        perm = PERMS_BY_KEY[key]
        if user.role == ROLE_SUPERADMIN:
            return Decision.ALLOWED
        allowed, ask = self._flags(user.role, key)
        if not allowed:
            return Decision.NEEDS_APPROVAL if (perm.approvable and user.role == ROLE_CASHIER) else Decision.DENIED
        return Decision.NEEDS_PASSWORD if ask else Decision.ALLOWED

    def table(self, role: str) -> dict[str, tuple[bool, bool]]:
        return {p.key: self._flags(role, p.key) for p in PERMISSIONS}

    # ---- settings screen will call these --------------------------------
    def _check_actor(self, actor: User) -> None:
        if not actor.is_admin:
            raise PermissionError("only the Owner or Super Admin can change permissions")

    def set_allowed(self, actor: User, role: str, key: str, allowed: bool) -> None:
        self._check_actor(actor)
        perm = PERMS_BY_KEY[key]
        if role != ROLE_CASHIER or not perm.approvable:
            raise PermissionError("this permission is fixed")
        old_allowed, ask = self._flags(role, key)
        with atomic(self._conn):
            self._repo.update(role, key, allowed, ask)
            self._audit.log(actor, "permission.change", entity="permission", reason=f"{role}:{key}",
                            old={"allowed": old_allowed}, new={"allowed": allowed})

    def set_ask_password(self, actor: User, role: str, key: str, ask: bool) -> None:
        self._check_actor(actor)
        perm = PERMS_BY_KEY[key]
        if role not in (ROLE_OWNER, ROLE_CASHIER) or (perm.locked_ask and not ask):
            raise PermissionError("this setting is fixed")
        allowed, old_ask = self._flags(role, key)
        with atomic(self._conn):
            self._repo.update(role, key, allowed, ask)
            self._audit.log(actor, "permission.change", entity="permission", reason=f"{role}:{key}",
                            old={"ask_password": old_ask}, new={"ask_password": ask})
