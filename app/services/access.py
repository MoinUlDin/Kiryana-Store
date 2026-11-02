from __future__ import annotations

from app.domain.user import User
from app.services.approval_service import Approval, ApprovalService
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.permission_service import Decision, PermissionService


class AccessController:
    """The one place the UI asks 'may this user do this, and what must they confirm first?'"""

    def __init__(self, permissions: PermissionService, approvals: ApprovalService,
                 auth: AuthService, audit: AuditService) -> None:
        self._permissions = permissions
        self._approvals = approvals
        self._auth = auth
        self._audit = audit

    def decide(self, user: User, perm_key: str) -> Decision:
        return self._permissions.decide(user, perm_key)

    def confirm_password(self, user: User, perm_key: str, password: str) -> bool:
        ok = self._auth.verify_password(user.id, password)
        self._audit.log(user, "access.reauth" if ok else "access.reauth_failed", entity="permission", reason=perm_key)
        return ok

    def request_approval(self, user: User, perm_key: str, secret: str) -> Approval | None:
        return self._approvals.request(user, perm_key, secret)
