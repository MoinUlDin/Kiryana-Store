from __future__ import annotations

from dataclasses import dataclass

ROLE_SUPERADMIN = "superadmin"
ROLE_OWNER = "owner"
ROLE_CASHIER = "cashier"
ROLES = (ROLE_SUPERADMIN, ROLE_OWNER, ROLE_CASHIER)


@dataclass(frozen=True)
class User:
    id: int
    username: str
    display_name: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role in (ROLE_SUPERADMIN, ROLE_OWNER)


# Acts for developer tooling and first-run setup. Audit rows store user_id NULL for it.
SYSTEM = User(0, "system", "System", ROLE_SUPERADMIN)
