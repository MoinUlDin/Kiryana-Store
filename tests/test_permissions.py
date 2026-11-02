import pytest

from app.domain.permissions import PERMISSIONS, PERMS_BY_KEY
from app.domain.user import ROLE_CASHIER, ROLE_OWNER, ROLE_SUPERADMIN, SYSTEM
from app.services.permission_service import Decision
from tests.helpers import make_services


@pytest.fixture
def svc(tmp_path):
    s = make_services(tmp_path)
    admin = s.auth.create_user(SYSTEM, "admin", "Dev", ROLE_SUPERADMIN, "adminpass")
    owner = s.auth.create_user(admin, "owner", "Owner", ROLE_OWNER, "ownerpass")
    cashier = s.auth.create_user(owner, "ali", "Ali", ROLE_CASHIER, "alipass1")
    s.users = (admin, owner, cashier)
    yield s
    s.conn.close()


def test_permission_keys_unique():
    assert len(PERMS_BY_KEY) == len(PERMISSIONS)


def test_seed_is_idempotent_and_keeps_overrides(svc):
    admin, owner, cashier = svc.users
    svc.permissions.set_allowed(owner, ROLE_CASHIER, "sales.void", True)
    svc.permissions.seed_defaults()                       # app restart
    assert svc.permissions.decide(cashier, "sales.void") is Decision.ALLOWED


def test_default_decisions(svc):
    admin, owner, cashier = svc.users
    d = svc.permissions.decide
    assert d(cashier, "sales.discount") is Decision.ALLOWED
    assert d(cashier, "sales.void") is Decision.NEEDS_APPROVAL      # denied but an owner can approve
    assert d(cashier, "users.manage") is Decision.DENIED            # never approvable
    assert d(cashier, "audit.view") is Decision.DENIED
    assert d(owner, "sales.void") is Decision.ALLOWED
    assert d(owner, "system.config") is Decision.DENIED
    assert d(admin, "system.config") is Decision.ALLOWED
    assert d(owner, "backup.restore") is Decision.NEEDS_PASSWORD    # locked ask-password


def test_ask_password_applies_to_owner_too(svc):
    admin, owner, cashier = svc.users
    svc.permissions.set_ask_password(owner, ROLE_OWNER, "price.sale", True)
    svc.permissions.set_ask_password(owner, ROLE_CASHIER, "price.sale", True)
    svc.permissions.set_allowed(owner, ROLE_CASHIER, "price.sale", True)
    assert svc.permissions.decide(owner, "price.sale") is Decision.NEEDS_PASSWORD
    assert svc.permissions.decide(cashier, "price.sale") is Decision.NEEDS_PASSWORD
    assert svc.permissions.decide(admin, "price.sale") is Decision.ALLOWED   # developer is never prompted


def test_cashier_toggle_flow(svc):
    _a, owner, cashier = svc.users
    assert svc.permissions.decide(cashier, "reports.profit") is Decision.NEEDS_APPROVAL
    svc.permissions.set_allowed(owner, ROLE_CASHIER, "reports.profit", True)
    assert svc.permissions.decide(cashier, "reports.profit") is Decision.ALLOWED
    svc.permissions.set_allowed(owner, ROLE_CASHIER, "reports.profit", False)
    assert svc.permissions.decide(cashier, "reports.profit") is Decision.NEEDS_APPROVAL


def test_fixed_settings_cannot_be_changed(svc):
    _a, owner, cashier = svc.users
    with pytest.raises(PermissionError):
        svc.permissions.set_allowed(owner, ROLE_CASHIER, "users.manage", True)
    with pytest.raises(PermissionError):
        svc.permissions.set_allowed(owner, ROLE_OWNER, "sales.void", False)       # owner rights are fixed
    with pytest.raises(PermissionError):
        svc.permissions.set_ask_password(owner, ROLE_OWNER, "backup.restore", False)  # restore always asks
    with pytest.raises(PermissionError):
        svc.permissions.set_allowed(cashier, ROLE_CASHIER, "sales.void", True)    # cashiers cannot edit rules


def test_changes_are_audited(svc):
    _a, owner, _c = svc.users
    svc.permissions.set_allowed(owner, ROLE_CASHIER, "sales.void", True)
    rows = [r for r in svc.conn.execute("SELECT * FROM audit_log WHERE action = 'permission.change'")]
    assert len(rows) == 1 and rows[0]["reason"] == "cashier:sales.void" and rows[0]["username"] == "owner"


def test_unknown_permission_is_a_loud_error(svc):
    with pytest.raises(KeyError):
        svc.permissions.decide(svc.users[2], "no.such.permission")
