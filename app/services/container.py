from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.repositories.settings_repo import SettingsRepo
from app.services.access import AccessController
from app.services.approval_service import ApprovalService
from app.services.audit_service import AuditService
from app.services.alert_service import AlertService
from app.services.auth_service import AuthService
from app.services.import_service import ImportService
from app.services.item_service import ItemService
from app.services.named_list_service import NamedListService
from app.services.permission_service import PermissionService
from app.services.sale_service import HeldBillService, SaleService
from app.services.sales_settings import SalesSettings
from app.services.purchase_service import PurchaseService
from app.services.stock_service import StockService
from app.services.supplier_service import SupplierService


@dataclass
class Services:
    conn: sqlite3.Connection
    settings: SettingsRepo
    audit: AuditService
    auth: AuthService
    permissions: PermissionService
    approvals: ApprovalService
    access: AccessController
    stock: StockService
    items: ItemService
    categories: NamedListService
    brands: NamedListService
    suppliers: SupplierService
    purchases: PurchaseService
    alerts: AlertService
    importer: ImportService
    sales_settings: SalesSettings
    sales: SaleService
    held: HeldBillService


def build_services(conn: sqlite3.Connection) -> Services:
    audit = AuditService(conn)
    auth = AuthService(conn, audit)
    permissions = PermissionService(conn, audit)
    approvals = ApprovalService(conn, audit)
    permissions.seed_defaults()
    stock = StockService(conn, audit)
    settings = SettingsRepo(conn)
    items = ItemService(conn, audit, stock)
    categories = NamedListService(conn, audit, "categories", "category")
    brands = NamedListService(conn, audit, "brands", "brand")
    sales_settings = SalesSettings(settings)
    return Services(
        conn, settings, audit, auth, permissions, approvals,
        AccessController(permissions, approvals, auth, audit),
        stock, items, categories, brands,
        SupplierService(conn, audit), PurchaseService(conn, audit, stock), AlertService(conn, settings),
        ImportService(conn, audit, items, categories, brands),
        sales_settings, SaleService(conn, audit, stock, sales_settings),
        HeldBillService(conn, audit, items.get),
    )
