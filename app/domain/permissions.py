"""Every permission in the app, with its defaults. This is the single source of truth;
the database only stores the shop's overrides (role_permissions)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermDef:
    key: str
    cashier_default: bool = False
    owner_allowed: bool = True
    approvable: bool = True      # may a cashier be let through by an Owner password/PIN?
    ask_default: bool = False    # ask-password layer on by default
    locked_ask: bool = False     # ask-password can never be switched off


PERMISSIONS: tuple[PermDef, ...] = (
    PermDef("sales.discount", cashier_default=True),
    PermDef("sales.discount.unlimited"),
    PermDef("sales.misc", cashier_default=True),
    PermDef("sales.return"),
    PermDef("sales.void"),
    PermDef("udhar.sell", cashier_default=True),
    PermDef("udhar.receive", cashier_default=True),
    PermDef("stock.quickfix"),
    PermDef("stock.adjust"),
    PermDef("items.edit"),
    PermDef("price.sale"),
    PermDef("price.cost"),
    PermDef("purchase.add"),
    PermDef("reports.profit"),       # cost price and profit figures
    PermDef("reports.view_all"),     # without it a cashier sees only their own sales for today
    PermDef("customers.manage"),
    PermDef("expenses.add"),
    PermDef("cash.close"),
    PermDef("backup.run"),
    PermDef("backup.restore", approvable=False, locked_ask=True, ask_default=True),
    PermDef("audit.view", approvable=False),
    PermDef("users.manage", approvable=False),
    PermDef("system.config", owner_allowed=False, approvable=False),
)

PERMS_BY_KEY: dict[str, PermDef] = {p.key: p for p in PERMISSIONS}
