"""Pure-data description of the ribbon (no Qt). Tests check it against the catalogs.

priority: lower number = more important = stays expanded longest when the window narrows.
Glyphs are Segoe MDL2 Assets codepoints (built into Windows 10) used as placeholder icons.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionDef:
    id: str
    glyph: str
    shortcut: str | None = None
    perm: str | None = None  # permission key, wired up in Phase 1


@dataclass(frozen=True)
class GroupSpec:
    key: str
    priority: int
    items: tuple[tuple[str, bool], ...]  # (action_id, large)


@dataclass(frozen=True)
class TabSpec:
    key: str
    groups: tuple[GroupSpec, ...]


ACTIONS: tuple[ActionDef, ...] = (
    ActionDef("new_bill", "\uE710", "Ctrl+N"),
    ActionDef("hold_bill", "\uE769", "Ctrl+H"),
    ActionDef("resume_bill", "\uE768", "Ctrl+R"),
    ActionDef("find_item", "\uE721", "Ctrl+F"),
    ActionDef("discount", "\uE8EC", "F6", perm="sales.discount"),
    ActionDef("return_item", "\uE7A7", perm="sales.return"),
    ActionDef("void_bill", "\uE711", perm="sales.void"),
    ActionDef("checkout", "\uE73E", "F12"),
    ActionDef("print_bill", "\uE749", "Ctrl+P"),
    ActionDef("today_sales", "\uE787"),
    ActionDef("low_stock", "\uE7BA"),
    ActionDef("expiry", "\uE823"),
    ActionDef("items", "\uE8A5"),
    ActionDef("add_item", "\uE710", "Ctrl+Shift+N", perm="items.edit"),
    ActionDef("import_excel", "\uE896", perm="items.edit"),
    ActionDef("categories", "\uE700"),
    ActionDef("brands", "\uE700"),
    ActionDef("adjust_stock", "\uE70F", perm="stock.adjust"),
    ActionDef("new_purchase", "\uE710", perm="purchase.add"),
    ActionDef("purchase_history", "\uE81C"),
    ActionDef("customers", "\uE716"),
    ActionDef("udhar", "\uE77B"),
    ActionDef("receive_payment", "\uE73E", perm="udhar.receive"),
    ActionDef("sales_report", "\uE8A5"),
    ActionDef("profit_report", "\uE8A5", perm="reports.profit"),
    ActionDef("stock_value", "\uE8A5"),
    ActionDef("dues_report", "\uE8A5"),
    ActionDef("day_end", "\uE787", perm="cash.close"),
    ActionDef("expenses", "\uE8C8", perm="expenses.add"),
    ActionDef("shop_settings", "\uE713"),
    ActionDef("users", "\uE716", perm="users.manage"),
    ActionDef("permissions", "\uE72E", perm="users.manage"),
    ActionDef("backup_now", "\uE74E", perm="backup.run"),
    ActionDef("switch_language", "\uE774"),
)

TABS: tuple[TabSpec, ...] = (
    TabSpec("home", (
        GroupSpec("quick", 1, (("new_bill", True), ("hold_bill", False), ("resume_bill", False), ("find_item", False))),
        GroupSpec("today", 2, (("today_sales", True), ("low_stock", False), ("expiry", False))),
        GroupSpec("language", 9, (("switch_language", True),)),
    )),
    TabSpec("sales", (
        GroupSpec("bill", 1, (("new_bill", True), ("hold_bill", False), ("resume_bill", False), ("discount", False))),
        GroupSpec("payment", 1, (("checkout", True), ("print_bill", False))),
        GroupSpec("cash", 3, (("return_item", True), ("void_bill", True))),
    )),
    TabSpec("inventory", (
        GroupSpec("items", 1, (("items", True), ("add_item", True), ("import_excel", False), ("categories", False), ("brands", False))),
        GroupSpec("stock", 2, (("adjust_stock", True), ("low_stock", False), ("expiry", False))),
    )),
    TabSpec("purchases", (
        GroupSpec("purchases", 1, (("new_purchase", True), ("purchase_history", True))),
    )),
    TabSpec("customers", (
        GroupSpec("customers", 1, (("customers", True), ("udhar", True), ("receive_payment", True))),
    )),
    TabSpec("reports", (
        GroupSpec("reports", 1, (("sales_report", True), ("profit_report", True), ("stock_value", True), ("dues_report", True))),
        GroupSpec("cash", 2, (("day_end", True), ("expenses", True))),
    )),
    TabSpec("settings", (
        GroupSpec("shop", 1, (("shop_settings", True),)),
        GroupSpec("security", 2, (("users", True), ("permissions", True))),
        GroupSpec("backup", 3, (("backup_now", True),)),
    )),
)

ACTION_IDS = {a.id for a in ACTIONS}
