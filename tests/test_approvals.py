import pytest

from app.db.connection import connect
from app.db.migrator import migrate
from app.domain.user import ROLE_CASHIER, ROLE_OWNER, ROLE_SUPERADMIN, SYSTEM
from app.security.passwords import ValidationError
from app.services.access import AccessController
from app.services.approval_service import ApprovalGuard, ApprovalLocked, ApprovalService
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.permission_service import PermissionService
from tests.helpers import FakeClock


@pytest.fixture
def env(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    clock = FakeClock()
    audit = AuditService(conn)
    auth = AuthService(conn, audit, now=clock)
    perms = PermissionService(conn, audit)
    perms.seed_defaults()
    approvals = ApprovalService(conn, audit, now=clock, guard=ApprovalGuard(5, 60))
    admin = auth.create_user(SYSTEM, "admin", "Dev", ROLE_SUPERADMIN, "adminpass")
    owner = auth.create_user(admin, "owner", "Owner", ROLE_OWNER, "ownerpass")
    cashier = auth.create_user(owner, "ali", "Ali", ROLE_CASHIER, "alipass1")
    yield {"approvals": approvals, "auth": auth, "owner": owner, "cashier": cashier, "clock": clock,
           "access": AccessController(perms, approvals, auth, audit), "conn": conn}
    conn.close()


def test_owner_password_approves(env):
    result = env["approvals"].request(env["cashier"], "sales.void", "ownerpass")
    assert result is not None and result.method == "password" and result.approver_name == "Owner"


def test_wrong_secret_not_approved(env):
    assert env["approvals"].request(env["cashier"], "sales.void", "alipass1") is None  # cashier's own password is no good


def test_pin_approves_only_its_actions(env):
    env["approvals"].create_pin(env["owner"], "Quick", "4821", ["sales.void", "stock.quickfix"])
    ok = env["approvals"].request(env["cashier"], "stock.quickfix", "4821")
    assert ok is not None and ok.method == "pin" and ok.approver_name == "Owner"
    assert env["approvals"].request(env["cashier"], "sales.return", "4821") is None   # not in its list


def test_wildcard_pin_and_revoke(env):
    pin_id = env["approvals"].create_pin(env["owner"], "All", "9090")
    assert env["approvals"].request(env["cashier"], "sales.return", "9090") is not None
    env["approvals"].revoke_pin(env["owner"], pin_id)
    assert env["approvals"].request(env["cashier"], "sales.return", "9090") is None


def test_pin_rules(env):
    with pytest.raises(PermissionError):
        env["approvals"].create_pin(env["cashier"], "x", "1234")           # cashiers cannot issue PINs
    with pytest.raises(ValidationError):
        env["approvals"].create_pin(env["owner"], "x", "12")
    with pytest.raises(PermissionError):
        env["approvals"].create_pin(env["owner"], "x", "1234", ["users.manage"])  # non-approvable action


def test_non_approvable_actions_refuse_even_the_right_password(env):
    with pytest.raises(PermissionError):
        env["approvals"].request(env["cashier"], "users.manage", "ownerpass")


def test_guessing_is_throttled_then_recovers(env):
    approvals, clock = env["approvals"], env["clock"]
    for _ in range(5):
        assert approvals.request(env["cashier"], "sales.void", "nope") is None
    with pytest.raises(ApprovalLocked) as err:
        approvals.request(env["cashier"], "sales.void", "ownerpass")   # even the right one is refused while locked
    assert 1 <= err.value.seconds <= 61
    clock.advance(seconds=61)
    assert approvals.request(env["cashier"], "sales.void", "ownerpass") is not None


def test_deactivated_owner_pin_stops_working(env):
    env["approvals"].create_pin(env["owner"], "Q", "5555")
    admin = env["auth"].list_users()[0]
    sa = next(u for u in env["auth"].list_users() if u.role == ROLE_SUPERADMIN)
    env["auth"].set_active(sa, env["owner"].id, False)
    assert env["approvals"].request(env["cashier"], "sales.void", "5555") is None


def test_approvals_are_audited_without_secrets(env):
    env["approvals"].create_pin(env["owner"], "Q", "5555")
    env["approvals"].request(env["cashier"], "sales.void", "5555")
    env["approvals"].request(env["cashier"], "sales.void", "wrong-secret")
    rows = list(env["conn"].execute("SELECT * FROM audit_log WHERE action LIKE 'access.%'"))
    assert {r["action"] for r in rows} == {"access.approved", "access.approval_failed"}
    approved = next(r for r in rows if r["action"] == "access.approved")
    assert approved["username"] == "ali" and approved["approved_by"] == "Owner" and approved["approval_method"] == "pin"
    dump = " ".join(str(tuple(r)) for r in env["conn"].execute("SELECT * FROM audit_log"))
    assert "5555" not in dump and "wrong-secret" not in dump


def test_access_controller_reauth(env):
    access, cashier = env["access"], env["cashier"]
    assert access.confirm_password(cashier, "sales.void", "alipass1") is True
    assert access.confirm_password(cashier, "sales.void", "nope") is False
