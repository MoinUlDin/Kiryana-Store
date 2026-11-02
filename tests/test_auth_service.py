import pytest

from app.db.connection import connect
from app.db.migrator import migrate
from app.domain.user import ROLE_CASHIER, ROLE_OWNER, ROLE_SUPERADMIN, SYSTEM
from app.security.passwords import ValidationError
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService, AuthStatus
from tests.helpers import FakeClock


@pytest.fixture
def env(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    clock = FakeClock()
    audit = AuditService(conn)
    yield AuthService(conn, audit, now=clock), clock, conn
    conn.close()


def seed(auth):
    admin = auth.create_user(SYSTEM, "admin", "Developer", ROLE_SUPERADMIN, "adminpass")
    owner = auth.create_user(admin, "owner", "Shop Owner", ROLE_OWNER, "ownerpass")
    cashier = auth.create_user(owner, "ali", "Ali", ROLE_CASHIER, "alipass1")
    return admin, owner, cashier


def test_create_and_login(env):
    auth, _clock, _conn = env
    _admin, _owner, cashier = seed(auth)
    result = auth.authenticate("ALI", "alipass1")          # username is case-insensitive
    assert result.status is AuthStatus.OK and result.user == cashier
    assert auth.authenticate("ali", "wrong").status is AuthStatus.INVALID
    assert auth.authenticate("nobody", "x").status is AuthStatus.INVALID


def test_only_one_superadmin(env):
    auth, _c, _db = env
    admin, _owner, _cashier = seed(auth)
    with pytest.raises(PermissionError):
        auth.create_user(admin, "admin2", "Second", ROLE_SUPERADMIN, "password1")


def test_creation_rules(env):
    auth, _c, _db = env
    admin, owner, cashier = seed(auth)
    with pytest.raises(PermissionError):
        auth.create_user(owner, "owner2", "Other Owner", ROLE_OWNER, "password1")   # owner makes cashiers only
    with pytest.raises(PermissionError):
        auth.create_user(cashier, "cash2", "Nope", ROLE_CASHIER, "password1")
    assert auth.create_user(admin, "owner2", "Other Owner", ROLE_OWNER, "password1").role == ROLE_OWNER


def test_duplicate_username_and_bad_input(env):
    auth, _c, _db = env
    _a, owner, _ = seed(auth)
    with pytest.raises(ValidationError) as err:
        auth.create_user(owner, "ALI", "Another Ali", ROLE_CASHIER, "password1")
    assert err.value.code == "error.username_taken"
    with pytest.raises(ValidationError):
        auth.create_user(owner, "bob", "  ", ROLE_CASHIER, "password1")
    with pytest.raises(ValidationError):
        auth.create_user(owner, "bob", "Bob", ROLE_CASHIER, "123")


def test_lockout_after_five_failures_and_recovery(env):
    auth, clock, _db = env
    seed(auth)
    for _ in range(4):
        assert auth.authenticate("ali", "bad").status is AuthStatus.INVALID
    fifth = auth.authenticate("ali", "bad")
    assert fifth.status is AuthStatus.LOCKED and fifth.locked_minutes == 5
    # correct password is refused while locked
    assert auth.authenticate("ali", "alipass1").status is AuthStatus.LOCKED
    clock.advance(minutes=3)
    locked = auth.authenticate("ali", "alipass1")
    assert locked.status is AuthStatus.LOCKED and locked.locked_minutes == 2
    clock.advance(minutes=3)
    assert auth.authenticate("ali", "alipass1").status is AuthStatus.OK


def test_success_resets_failure_counter(env):
    auth, _c, _db = env
    seed(auth)
    for _ in range(3):
        auth.authenticate("ali", "bad")
    assert auth.authenticate("ali", "alipass1").status is AuthStatus.OK
    for _ in range(4):
        assert auth.authenticate("ali", "bad").status is AuthStatus.INVALID  # counter started over


def test_inactive_user_cannot_log_in(env):
    auth, _c, _db = env
    _a, owner, cashier = seed(auth)
    auth.set_active(owner, cashier.id, False)
    assert auth.authenticate("ali", "alipass1").status is AuthStatus.INACTIVE
    assert cashier not in auth.list_users()
    auth.set_active(owner, cashier.id, True)
    assert auth.authenticate("ali", "alipass1").status is AuthStatus.OK


def test_password_change_rules(env):
    auth, _c, _db = env
    admin, owner, cashier = seed(auth)
    with pytest.raises(ValidationError):                       # self-service needs the old password
        auth.change_password(cashier, cashier.id, "newpass12", old_password="wrong")
    auth.change_password(cashier, cashier.id, "newpass12", old_password="alipass1")
    assert auth.authenticate("ali", "newpass12").status is AuthStatus.OK
    auth.change_password(owner, cashier.id, "ownerreset1")     # owner can reset a cashier
    assert auth.authenticate("ali", "ownerreset1").status is AuthStatus.OK
    with pytest.raises(PermissionError):                       # owner cannot reset the Super Admin
        auth.change_password(owner, admin.id, "hacked123")
    with pytest.raises(PermissionError):                       # cashier cannot reset others
        auth.change_password(cashier, owner.id, "hacked123")


def test_cannot_disable_yourself_or_higher_roles(env):
    auth, _c, _db = env
    admin, owner, _cashier = seed(auth)
    with pytest.raises(PermissionError):
        auth.set_active(owner, owner.id, False)
    with pytest.raises(PermissionError):
        auth.set_active(owner, admin.id, False)


def test_audit_never_contains_passwords(env):
    auth, _c, conn = env
    seed(auth)
    auth.authenticate("ali", "wrongpass-xyz")
    auth.authenticate("ali", "alipass1")
    dump = " ".join(str(tuple(r)) for r in conn.execute("SELECT * FROM audit_log"))
    for secret in ("adminpass", "ownerpass", "alipass1", "wrongpass-xyz"):
        assert secret not in dump
    actions = {r["action"] for r in conn.execute("SELECT action FROM audit_log")}
    assert {"user.create", "login", "login.failed"} <= actions
