from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from app.db.connection import atomic
from app.domain.clock import utcnow
from app.domain.permissions import PERMS_BY_KEY
from app.domain.user import User
from app.repositories.pin_repo import PinRepo
from app.repositories.user_repo import UserRepo
from app.security.passwords import hash_secret, validate_pin, verify_secret
from app.services.audit_service import AuditService


class ApprovalLocked(Exception):
    def __init__(self, seconds: int) -> None:
        super().__init__(f"locked for {seconds}s")
        self.seconds = seconds


class ApprovalGuard:
    """Slows down guessing of owner passwords / PINs from a cashier's screen."""

    def __init__(self, max_attempts: int = 5, lock_seconds: int = 60) -> None:
        self._max = max_attempts
        self._lock_seconds = lock_seconds
        self._failures = 0
        self._locked_until: datetime | None = None

    def check(self, now: datetime) -> None:
        if self._locked_until and now < self._locked_until:
            raise ApprovalLocked(max(1, int((self._locked_until - now).total_seconds()) + 1))

    def record_failure(self, now: datetime) -> None:
        self._failures += 1
        if self._failures >= self._max:
            self._failures = 0
            self._locked_until = now + timedelta(seconds=self._lock_seconds)

    def reset(self) -> None:
        self._failures = 0
        self._locked_until = None


@dataclass(frozen=True)
class Approval:
    approver_name: str
    method: str  # 'password' or 'pin'


class ApprovalService:
    def __init__(self, conn: sqlite3.Connection, audit: AuditService, now: Callable = utcnow,
                 guard: ApprovalGuard | None = None) -> None:
        self._conn = conn
        self._users = UserRepo(conn)
        self._pins = PinRepo(conn)
        self._audit = audit
        self._now = now
        self._guard = guard or ApprovalGuard()

    def request(self, requester: User, perm_key: str, secret: str) -> Approval | None:
        """Does `secret` belong to an Owner/Super Admin password or a PIN valid for this action?"""
        if not PERMS_BY_KEY[perm_key].approvable:
            raise PermissionError("this action cannot be approved remotely")
        now = self._now()
        self._guard.check(now)

        approval = self._match_password(secret) or self._match_pin(secret, perm_key)
        if approval is None:
            self._guard.record_failure(now)
            self._audit.log(requester, "access.approval_failed", entity="permission", reason=perm_key)
            return None
        self._guard.reset()
        self._audit.log(requester, "access.approved", entity="permission", reason=perm_key,
                        approved_by=approval.approver_name, approval_method=approval.method)
        return approval

    def _match_password(self, secret: str) -> Approval | None:
        for row in self._users.active_admins():
            if verify_secret(secret, row["password_hash"]):
                return Approval(row["display_name"], "password")
        return None

    def _match_pin(self, secret: str, perm_key: str) -> Approval | None:
        for row in self._pins.active():
            allowed = row["allowed_actions"]
            if allowed != "*" and perm_key not in json.loads(allowed):
                continue
            if verify_secret(secret, row["pin_hash"]):
                return Approval(row["owner_name"], "pin")
        return None

    # ---- PIN management (Owner / Super Admin) ---------------------------
    def create_pin(self, actor: User, label: str, pin: str, perm_keys: list[str] | None = None) -> int:
        if not actor.is_admin:
            raise PermissionError("only the Owner or Super Admin can create PINs")
        validate_pin(pin)
        if perm_keys is not None:
            for key in perm_keys:
                if not PERMS_BY_KEY[key].approvable:
                    raise PermissionError(f"{key} cannot be approved with a PIN")
        allowed = "*" if perm_keys is None else json.dumps(sorted(perm_keys))
        with atomic(self._conn):
            pin_id = self._pins.insert(actor.id, label.strip() or "PIN", hash_secret(pin), allowed)
            self._audit.log(actor, "pin.create", entity="pin", entity_id=pin_id,
                            new={"label": label.strip(), "actions": allowed})
        return pin_id

    def revoke_pin(self, actor: User, pin_id: int) -> None:
        if not actor.is_admin:
            raise PermissionError("only the Owner or Super Admin can revoke PINs")
        with atomic(self._conn):
            self._pins.revoke(pin_id)
            self._audit.log(actor, "pin.revoke", entity="pin", entity_id=pin_id)
