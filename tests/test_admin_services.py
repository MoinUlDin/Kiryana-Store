import pytest

from app.domain.permissions import PERMISSIONS
from app.domain.user import ROLE_CASHIER, ROLE_OWNER, ROLE_SUPERADMIN, SYSTEM
from app.services.audit_service import describe_entry
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


def test_owner_does_not_see_super_admin(svc):
    admin, owner, cashier = svc.users
    owner_view = {a.user.username for a in svc.auth.list_accounts(owner)}
    assert owner_view == {"owner", "ali"}
    assert {a.user.username for a in svc.auth.list_accounts(admin)} == {"admin", "owner", "ali"}
    with pytest.raises(PermissionError):
        svc.auth.list_accounts(cashier)


def test_account_flags_and_last_login(svc):
    admin, owner, cashier = svc.users
    svc.auth.authenticate("ali", "alipass1")
    svc.auth.set_active(owner, cashier.id, False)
    ali = next(a for a in svc.auth.list_accounts(owner) if a.user.username == "ali")
    assert ali.is_active is False and ali.last_login_at is not None


def test_manage_and_create_rules_for_ui(svc):
    admin, owner, cashier = svc.users
    assert svc.auth.creatable_roles(admin) == [ROLE_OWNER, ROLE_CASHIER]
    assert svc.auth.creatable_roles(owner) == [ROLE_CASHIER]
    assert svc.auth.creatable_roles(cashier) == []
    assert svc.auth.can_manage(owner, ROLE_CASHIER) and not svc.auth.can_manage(owner, ROLE_OWNER)
    assert svc.auth.can_manage(admin, ROLE_OWNER) and not svc.auth.can_manage(cashier, ROLE_CASHIER)


def test_audit_search_and_paging(svc):
    for i in range(7):
        svc.audit.log(svc.users[1], "test.event", reason=f"item_{i}")
    svc.audit.log(svc.users[2], "login.failed")
    first = svc.audit.search("test.event", limit=3)
    assert len(first) == 3 and all(r["action"] == "test.event" for r in first)
    assert first[0]["id"] > first[-1]["id"]                         # newest first
    second = svc.audit.search("test.event", limit=10, before_id=first[-1]["id"])
    assert len(second) == 4 and second[0]["id"] < first[-1]["id"]    # continues where page one stopped
    assert {r["username"] for r in svc.audit.search("ali")} >= {"ali"}
    assert svc.audit.search("item_3")[0]["reason"] == "item_3"       # matches the reason column too


def test_audit_search_treats_wildcards_literally(svc):
    svc.audit.log(svc.users[1], "a.b", reason="100% done")
    svc.audit.log(svc.users[1], "a.b", reason="plain")
    assert [r["reason"] for r in svc.audit.search("100%")] == ["100% done"]
    assert len(svc.audit.search("%")) == 1


def test_describe_entry(svc):
    svc.permissions.set_allowed(svc.users[1], ROLE_CASHIER, "sales.void", True)
    row = svc.audit.search("permission.change")[0]
    text = describe_entry(row)
    assert "cashier:sales.void" in text and "->" in text
    svc.approvals.create_pin(svc.users[1], "Q", "5555")
    svc.approvals.request(svc.users[2], "sales.return", "5555")
    approved = describe_entry(svc.audit.search("access.approved")[0])
    assert "approved by Owner (pin)" in approved


def test_list_pins(svc):
    admin, owner, cashier = svc.users
    svc.approvals.create_pin(owner, "Everything", "1111")
    svc.approvals.create_pin(owner, "Void only", "2222", ["sales.void"])
    pins = {p.label: p for p in svc.approvals.list_pins(owner)}
    assert pins["Everything"].perm_keys is None and pins["Void only"].perm_keys == ["sales.void"]
    assert pins["Void only"].owner_name == "Owner"
    svc.approvals.revoke_pin(owner, pins["Void only"].id)
    assert [p.label for p in svc.approvals.list_pins(owner)] == ["Everything"]
    with pytest.raises(PermissionError):
        svc.approvals.list_pins(cashier)
