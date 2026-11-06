from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QComboBox, QDateEdit, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidgetItem

from app.domain.clock import local_today_iso
from app.domain.money import Money
from app.domain.purchase import Purchase, PurchaseInput
from app.domain.user import User
from app.services.container import Services
from app.ui.dialogs.purchase_dialog import PurchaseDialog
from app.ui.dialogs.purchase_line_dialog import to_qdate
from app.ui.dialogs.purchase_view_dialog import PurchaseViewDialog
from app.ui.dialogs.suppliers_dialog import SuppliersDialog
from app.ui.errors import error_text
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page


class PurchasesPage(Page):
    title_key = "purchases.title"

    def __init__(self, i18n: I18n, services: Services, user: User, parent=None) -> None:
        super().__init__(i18n, parent)
        self.services = services
        self.user = user
        self._purchases: list[Purchase] = []
        today = date.fromisoformat(local_today_iso())

        filters = QHBoxLayout()
        self._from_label, self._to_label = QLabel(), QLabel()
        self._from = QDateEdit(to_qdate(today - timedelta(days=30)))
        self._to = QDateEdit(to_qdate(today))
        for edit in (self._from, self._to):
            edit.setCalendarPopup(True)
            edit.dateChanged.connect(lambda _d: self.refresh())
        self._supplier = QComboBox()
        self._supplier.currentIndexChanged.connect(lambda _i: self.refresh())
        self._search = QLineEdit()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self.refresh)
        self._search.textChanged.connect(lambda _t: self._debounce.start())
        for widget in (self._from_label, self._from, self._to_label, self._to, self._supplier):
            filters.addWidget(widget)
        filters.addWidget(self._search, 1)
        self.layout_.addLayout(filters)

        bar = QHBoxLayout()
        self._new = QPushButton()
        self._new.setObjectName("PrimaryButton")
        self._new.clicked.connect(self._on_new)
        self._view = QPushButton()
        self._view.clicked.connect(self._on_view)
        self._suppliers = QPushButton()
        self._suppliers.clicked.connect(self._on_suppliers)
        for button in (self._new, self._view, self._suppliers):
            bar.addWidget(button)
        bar.addStretch(1)
        self.layout_.addLayout(bar)

        self._table = self.make_table(7)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._table.doubleClicked.connect(lambda _i: self._on_view())
        self.layout_.addWidget(self._table, 1)
        foot = QHBoxLayout()
        self._count = QLabel()
        self._count.setObjectName("StatusNote")
        foot.addWidget(self.note, 1)
        foot.addWidget(self._count)
        self.layout_.addLayout(foot)
        self.retranslate()

    def retranslate(self) -> None:
        super().retranslate()
        tr = self.i18n.tr
        self._from_label.setText(tr("purchases.from"))
        self._to_label.setText(tr("purchases.to"))
        self._search.setPlaceholderText(tr("purchases.search"))
        self._new.setText(tr("purchases.new"))
        self._view.setText(tr("purchases.view"))
        self._suppliers.setText(tr("purchases.suppliers"))
        self._table.setHorizontalHeaderLabels([
            tr("purchases.col.date"), tr("purchases.col.invoice"), tr("purchases.col.supplier"),
            tr("purchases.col.total"), tr("purchases.col.paid"), tr("purchases.col.due"), tr("purchases.col.by"),
        ])
        self._reload_suppliers()
        self.refresh()

    def _reload_suppliers(self) -> None:
        selected = self._supplier.currentData()
        self._supplier.blockSignals(True)
        self._supplier.clear()
        self._supplier.addItem(self.i18n.tr("purchases.all_suppliers"), None)
        for supplier in self.services.suppliers.list(include_inactive=True):
            self._supplier.addItem(supplier.name, supplier.id)
        self._supplier.setCurrentIndex(max(self._supplier.findData(selected), 0))
        self._supplier.blockSignals(False)

    def refresh(self) -> None:
        self._purchases = self.services.purchases.search(
            self._from.date().toPyDate().isoformat(), self._to.date().toPyDate().isoformat(),
            self._supplier.currentData(), self._search.text())
        self._table.setRowCount(len(self._purchases))
        for row, p in enumerate(self._purchases):
            values = [p.purchase_date, p.invoice_no or "-", p.supplier_name or "-", p.total.format(),
                      p.paid.format(), p.due.format(), p.created_by_name or "-"]
            for col, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if col in (3, 4, 5):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                self._table.setItem(row, col, cell)
        total = Money(sum(p.total.paisa for p in self._purchases))
        self._count.setText(self.i18n.tr("purchases.count", count=len(self._purchases), total=total.format()))
        self._update_buttons()

    def _selected(self) -> Purchase | None:
        row = self._table.currentRow()
        return self._purchases[row] if 0 <= row < len(self._purchases) else None

    def _update_buttons(self) -> None:
        self._view.setEnabled(self._selected() is not None)

    # ---- actions ------------------------------------------------------------
    def handle_action(self, action_id: str) -> None:
        if action_id == "new_purchase":
            self._new_purchase()
        elif action_id == "suppliers":
            self._manage_suppliers()

    def _on_new(self) -> None:
        if self.guard("purchase.add", self.i18n.tr("purchases.new")):
            self._new_purchase()

    def _on_suppliers(self) -> None:
        if self.guard("purchase.add", self.i18n.tr("purchases.suppliers")):
            self._manage_suppliers()

    def _on_view(self) -> None:
        p = self._selected()
        found = self.services.purchases.get(p.id) if p else None
        if found:
            PurchaseViewDialog(self.i18n, found[0], found[1], self).exec()

    def _manage_suppliers(self) -> None:
        SuppliersDialog(self.i18n, self.services.suppliers, self.user, self).exec()
        self._reload_suppliers()
        self.refresh()

    def _new_purchase(self) -> None:
        saved = {}

        def submit(data: PurchaseInput) -> str | None:
            try:
                saved["result"] = self.services.purchases.create(self.user, data)
            except (ValueError, PermissionError) as exc:
                return error_text(self.i18n, exc)
            return None

        today = date.fromisoformat(local_today_iso())
        if PurchaseDialog(self.i18n, self.services, today, self.guard, submit, self).exec():
            result = saved["result"]
            if result.warnings:
                names = ", ".join(w.item_name for w in result.warnings)
                self.say(self.i18n.tr("purchase.saved_warn", items=names), error=True)
            else:
                self.say(self.i18n.tr("purchase.saved"))
            self.refresh()
