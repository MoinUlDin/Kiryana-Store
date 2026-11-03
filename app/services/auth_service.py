from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from functools import lru_cache
from typing import Callable

from app.db.connection import atomic
from app.domain.clock import from_iso, to_iso, utcnow
from app.domain.user import ROLE_CASHIER, ROLE_OWNER, ROLE_SUPERADMIN, ROLES, User
from app.repositories.user_repo import UserRepo
from app.security.passwords import (
    ValidationError, hash_secret, validate_password, validate_username, verify_secret,
)
from app.services.audit_service import AuditService

LOCK_AFTER_FAILURES = 5
LOCK_MINUTES = 5


@dataclass(frozen=True)
class Account:
    user: User
    is_active: bool
    last_login_at: str | None


class AuthStatus(Enum):
    OK = "ok"
    INVALID = "invalid"
    LOCKED = "locked"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class AuthResult:
    status: AuthStatus
    user: User | None = None
    locked_minutes: int = 0


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_secret("dummy-password")


def to_user(row: sqlite3.Row) -> User:
    return User(row["id"], row["username"], row["display_name"], row["role"])


class AuthService:
    def __init__(self, conn: sqlite3.Connection, audit: AuditService, now: Callable = utcnow) -> None:
        self._conn = conn
        self._users = UserRepo(conn)
        self._audit = audit
        self._now = now

    # ---- queries -------------------------------------------------------
    def user_count(self) -> int:
        return self._users.count()

    def list_users(self, active_only: bool = True) -> list[User]:
        return [to_user(r) for r in self._users.list(active_only)]

    def list_accounts(self, actor: User) -> list[Account]:
        """Accounts the actor may see: the Super Admin sees everyone, the Owner sees Owner and cashiers."""
        if not actor.is_admin:
            raise PermissionError("only the Owner or Super Admin can list accounts")
        rows = self._users.list(active_only=False)
        if actor.role != ROLE_SUPERADMIN:
            rows = [r for r in rows if r["role"] != ROLE_SUPERADMIN]
        return [Account(to_user(r), bool(r["is_active"]), r["last_login_at"]) for r in rows]

    def can_manage(self, actor: User, target_role: str) -> bool:
        """May `actor` reset passwords / enable / disable accounts of this role?"""
        return actor.role == ROLE_SUPERADMIN or (actor.role == ROLE_OWNER and target_role == ROLE_CASHIER)

    def creatable_roles(self, actor: User) -> list[str]:
        if actor.role == ROLE_SUPERADMIN:
            return [ROLE_OWNER, ROLE_CASHIER]
        return [ROLE_CASHIER] if actor.role == ROLE_OWNER else []

    def get_user(self, user_id: int) -> User | None:
        row = self._users.get(user_id)
        return to_user(row) if row else None

    # ---- sign in -------------------------------------------------------
    def authenticate(self, username: str, password: str) -> AuthResult:
        row = self._users.get_by_username(username)
        if row is None:
            verify_secret(password, _dummy_hash())  # keep timing similar for unknown users
            self._audit.log(None, "login.failed", new={"username": username.strip()[:40]})
            return AuthResult(AuthStatus.INVALID)
        user = to_user(row)
        if not row["is_active"]:
            return AuthResult(AuthStatus.INACTIVE)

        now = self._now()
        if row["locked_until"] and from_iso(row["locked_until"]) > now:
            remaining = from_iso(row["locked_until"]) - now
            return AuthResult(AuthStatus.LOCKED, locked_minutes=max(1, math.ceil(remaining.total_seconds() / 60)))

        if verify_secret(password, row["password_hash"]):
            self._users.record_success(user.id, to_iso(now))
            self._audit.log(user, "login")
            return AuthResult(AuthStatus.OK, user)

        attempts = row["failed_attempts"] + 1
        if attempts >= LOCK_AFTER_FAILURES:
            self._users.record_failure(user.id, 0, to_iso(now + timedelta(minutes=LOCK_MINUTES)))
            self._audit.log(user, "login.locked", new={"minutes": LOCK_MINUTES})
            return AuthResult(AuthStatus.LOCKED, locked_minutes=LOCK_MINUTES)
        self._users.record_failure(user.id, attempts, None)
        self._audit.log(user, "login.failed")
        return AuthResult(AuthStatus.INVALID)

    def verify_password(self, user_id: int, password: str) -> bool:
        row = self._users.get(user_id)
        return bool(row) and bool(row["is_active"]) and verify_secret(password, row["password_hash"])

    # ---- user management ----------------------------------------------
    def create_user(self, actor: User, username: str, display_name: str, role: str, password: str) -> User:
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}")
        self._check_can_create(actor, role)
        username = validate_username(username)
        name = display_name.strip()
        if not name:
            raise ValidationError("error.name_required")
        validate_password(password)
        try:
            with atomic(self._conn):
                user_id = self._users.insert(username, name, role, hash_secret(password))
                self._audit.log(actor, "user.create", entity="user", entity_id=user_id,
                                new={"username": username, "role": role})
        except sqlite3.IntegrityError as exc:
            raise ValidationError("error.username_taken") from exc
        return User(user_id, username, name, role)

    def _check_can_create(self, actor: User, role: str) -> None:
        if role == ROLE_SUPERADMIN:
            allowed = actor.role == ROLE_SUPERADMIN and self._users.count_role(ROLE_SUPERADMIN) == 0
        elif actor.role == ROLE_SUPERADMIN:
            allowed = True
        else:
            allowed = actor.role == ROLE_OWNER and role == ROLE_CASHIER
        if not allowed:
            raise PermissionError("not allowed to create this kind of user")

    def _manageable(self, actor: User, target_row: sqlite3.Row) -> bool:
        if actor.role == ROLE_SUPERADMIN:
            return True
        return actor.role == ROLE_OWNER and target_row["role"] == ROLE_CASHIER

    def change_password(self, actor: User, target_id: int, new_password: str, old_password: str | None = None) -> None:
        row = self._users.get(target_id)
        if row is None:
            raise ValueError("no such user")
        if actor.id == target_id:
            if old_password is None or not verify_secret(old_password, row["password_hash"]):
                raise ValidationError("reauth.error")
        elif not self._manageable(actor, row):
            raise PermissionError("not allowed to reset this password")
        validate_password(new_password)
        with atomic(self._conn):
            self._users.set_password(target_id, hash_secret(new_password))
            self._audit.log(actor, "user.password_change", entity="user", entity_id=target_id,
                            new={"username": row["username"], "self_service": actor.id == target_id})

    def set_active(self, actor: User, target_id: int, active: bool) -> None:
        row = self._users.get(target_id)
        if row is None:
            raise ValueError("no such user")
        if actor.id == target_id or not self._manageable(actor, row):
            raise PermissionError("not allowed to change this account")
        with atomic(self._conn):
            self._users.set_active(target_id, active)
            self._audit.log(actor, "user.activate" if active else "user.deactivate",
                            entity="user", entity_id=target_id, new={"username": row["username"]})
