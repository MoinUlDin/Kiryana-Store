from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.repositories.settings_repo import SettingsRepo
from app.services.access import AccessController
from app.services.approval_service import ApprovalService
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.permission_service import PermissionService


@dataclass
class Services:
    conn: sqlite3.Connection
    settings: SettingsRepo
    audit: AuditService
    auth: AuthService
    permissions: PermissionService
    approvals: ApprovalService
    access: AccessController


def build_services(conn: sqlite3.Connection) -> Services:
    audit = AuditService(conn)
    auth = AuthService(conn, audit)
    permissions = PermissionService(conn, audit)
    approvals = ApprovalService(conn, audit)
    permissions.seed_defaults()
    return Services(conn, SettingsRepo(conn), audit, auth, permissions, approvals,
                    AccessController(permissions, approvals, auth, audit))
