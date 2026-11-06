from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidgetItem,
)

from app.domain.item import Item, ItemInput
from app.domain.quantity import Quantity
from app.domain.user import User
from app.services.container import Services
from app.services.item_service import WARN_COST_ABOVE_SALE
from app.services.permission_service import Decision
from app.ui.dialogs.confirm import confirm
from app.ui.dialogs.import_dialog import ImportDialog
from app.ui.dialogs.item_dialog import ItemDialog
from app.ui.dialogs.manage_list_dialog import ManageListDialog
from app.ui.dialogs.stock_dialogs import AdjustDialog, HistoryDialog
from app.ui.errors import error_text
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page

COL_CODE, COL_NAME, COL_CATEGORY, COL_UNIT, COL_PRICE, COL_COST, COL_STOCK, COL_STATUS = range(8)
RED = QBrush(QColor("#B42318"))


class ItemsPage(Page):
    title_key = "items.title"

    def __init__(self, i18n: I18n, services: Services, user: User, parent=None) -> None:
        super().__init__(i18n, parent)
        self.services = services
        self.user = user
        self._items: list[Item] = []

        filters = QHBoxLayout()
        self._search = QLineEdit()
        self._debounce = QTimer(self)  # wait for a pause in typing before searching
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self.refresh)
        self._search.textChanged.connect(lambda _t: self._debounce.start())
        self._search.returnPressed.connect(self.refresh)
        self._category = QComboBox()
        self._category.currentIndexChanged.connect(lambda _i: self.refresh())
        self._low = QCheckBox()
        self._low.toggled.connect(lambda _c: self.refresh())
        self._inactive = QCheckBox()
        self._inactive.toggled.connect(lambda _c: self.refresh())
        filters.addWidget(self._search, 1)
        filters.addWidget(self._category)
        filters.addWidget(self._low)
        filters.addWidget(self._inactive)
        self.layout_.addLayout(filters)

        bar = QHBoxLayout()
        self._buttons = {}
        for key, handler in (("add", self._on_add), ("edit", self._on_edit), ("adjust", self._on_adjust),
                             ("history", self._on_history), ("toggle", self._on_toggle), ("delete", self._on_delete),
                             ("import", self._on_import),
                             ("categories", self._on_categories), ("brands", self._on_brands)):
            button = QPushButton()
            button.clicked.connect(handler)
            self._buttons[key] = button
            bar.addWidget(button)
        self._buttons["add"].setObjectName("PrimaryButton")
        bar.addStretch(1)
        self.layout_.addLayout(bar)

        self._table = self.make_table(8)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._table.doubleClicked.connect(lambda _i: self._on_edit())
        self.layout_.addWidget(self._table, 1)
        foot = QHBoxLayout()
        self._count = QLabel()
        self._count.setObjectName("StatusNote")
        foot.addWidget(self.note, 1)
        foot.addWidget(self._count)
        self.layout_.addLayout(foot)
        self.retranslate()

    # ---- text / data ---------------------------------------------------------
    def retranslate(self) -> None:
        super().retranslate()
        tr = self.i18n.tr
        self._search.setPlaceholderText(tr("items.search"))
        self._low.setText(tr("items.low_only"))
        self._inactive.setText(tr("items.show_inactive"))
        for key, text in (("add", "items.add"), ("edit", "items.edit"), ("adjust", "items.adjust"),
                          ("history", "items.history"), ("categories", "items.categories"), ("brands", "items.brands"),
                          ("delete", "lists.delete"), ("import", "items.import")):
            self._buttons[key].setText(tr(text))
        self._table.setHorizontalHeaderLabels([
            tr("items.col.code"), tr("users.col.name"), tr("items.col.category"), tr("items.col.unit"),
            tr("items.col.price"), tr("items.col.cost"), tr("items.col.stock"), tr("users.col.status"),
        ])
        self._reload_categories()
        self.refresh()

    def _reload_categories(self) -> None:
        selected = self._category.currentData()
        self._category.blockSignals(True)
        self._category.clear()
        self._category.addItem(self.i18n.tr("items.all_categories"), None)
        for entry in self.services.categories.list():
            self._category.addItem(entry.display(self.i18n.lang), entry.id)
        self._category.setCurrentIndex(max(self._category.findData(selected), 0))
        self._category.blockSignals(False)

    def _can_see_cost(self) -> bool:
        return self.services.access.decide(self.user, "reports.profit") in (Decision.ALLOWED, Decision.NEEDS_PASSWORD)

    def refresh(self) -> None:
        tr = self.i18n.tr
        selected = self._selected_id()
        self._items = self.services.items.search(
            self._search.text(), self._category.currentData(), self._low.isChecked(), self._inactive.isChecked()
        )
        names = {c.id: c.display(self.i18n.lang) for c in self.services.categories.list(include_inactive=True)}
        self._table.setColumnHidden(COL_COST, not self._can_see_cost())
        self._table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            stock_text = f"{item.stock.format()} {tr('unit.' + item.unit)}"
            cells = {
                COL_CODE: item.short_code,
                COL_NAME: item.display_name(self.i18n.lang),
                COL_CATEGORY: names.get(item.category_id, "-"),
                COL_UNIT: tr(f"unit.{item.unit}"),
                COL_PRICE: item.sale.format(),
                COL_COST: item.cost.format(),
                COL_STOCK: stock_text,
                COL_STATUS: tr("users.status.active" if item.is_active else "users.status.disabled"),
            }
            for col, text in cells.items():
                cell = QTableWidgetItem(text)
                if col in (COL_PRICE, COL_COST, COL_STOCK):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                if col == COL_STOCK and (item.is_low or item.stock.milli == 0):
                    cell.setForeground(RED)
                if col == COL_COST and item.cost_above_sale:
                    cell.setForeground(RED)
                    cell.setToolTip(tr("item.warn.cost_above_sale"))
                if col == COL_NAME:
                    cell.setToolTip(f"{item.name_en}\n{item.name_ur or ''}".strip())
                self._table.setItem(row, col, cell)
            if item.id == selected:
                self._table.selectRow(row)
        self._count.setText(tr("items.count", count=len(self._items)))
        self._update_buttons()

    def _selected(self) -> Item | None:
        row = self._table.currentRow()
        return self._items[row] if 0 <= row < len(self._items) else None

    def _selected_id(self) -> int | None:
        item = self._selected()
        return item.id if item else None

    def _update_buttons(self) -> None:
        item = self._selected()
        for key in ("edit", "adjust", "history", "toggle"):
            self._buttons[key].setEnabled(item is not None)
        self._buttons["delete"].setEnabled(item is not None and self.services.items.can_delete(item.id))
        tr = self.i18n.tr
        self._buttons["toggle"].setText(tr("items.deactivate") if (item is None or item.is_active) else tr("items.activate"))

    # ---- entry point for ribbon actions (the main window already ran the permission guard) ---
    def handle_action(self, action_id: str) -> None:
        if action_id == "add_item":
            self._add_item()
        elif action_id == "adjust_stock":
            self._adjust_selected()
        elif action_id == "categories":
            self._manage("categories", "lists.categories")
        elif action_id == "brands":
            self._manage("brands", "lists.brands")
        elif action_id == "low_stock":
            self._low.setChecked(True)
        elif action_id == "import_excel":
            self._import_items()

    # ---- buttons (these ask for permission themselves) ---------------------------
    def _on_add(self) -> None:
        if self.guard("items.edit", self.i18n.tr("items.add")):
            self._add_item()

    def _on_edit(self) -> None:
        if self._selected() and self.guard("items.edit", self.i18n.tr("items.edit")):
            self._edit_item(self._selected())

    def _on_adjust(self) -> None:
        if self.guard("stock.adjust", self.i18n.tr("items.adjust")):
            self._adjust_selected()

    def _on_categories(self) -> None:
        if self.guard("items.edit", self.i18n.tr("items.categories")):
            self._manage("categories", "lists.categories")

    def _on_brands(self) -> None:
        if self.guard("items.edit", self.i18n.tr("items.brands")):
            self._manage("brands", "lists.brands")

    def _on_import(self) -> None:
        if self.guard("items.edit", self.i18n.tr("items.import")):
            self._import_items()

    def _on_delete(self) -> None:
        item = self._selected()
        if item is None or not self.guard("items.edit", self.i18n.tr("lists.delete")):
            return
        if not confirm(self.i18n, self, item.display_name(self.i18n.lang), self.i18n.tr("items.delete_confirm")):
            return
        try:
            self.services.items.delete(self.user, item.id)
        except (ValueError, PermissionError) as exc:
            self.say(error_text(self.i18n, exc), error=True)
            return
        self.say(self.i18n.tr("item.deleted"))
        self.refresh()

    def _on_history(self) -> None:
        item = self._selected()
        if item:
            HistoryDialog(self.i18n, item, self.services.stock.movements(item.id), self).exec()

    def _on_toggle(self) -> None:
        item = self._selected()
        if item is None or not self.guard("items.edit", self.i18n.tr("items.edit")):
            return
        self.services.items.set_active(self.user, item.id, not item.is_active)
        self.say(self.i18n.tr("item.deactivated" if item.is_active else "item.activated"))
        self.refresh()

    # ---- the real work -----------------------------------------------------------
    def _add_item(self) -> None:
        def submit(data: ItemInput, opening: Quantity | None) -> str | None:
            try:
                result = self.services.items.create(self.user, data, opening)
            except (ValueError, PermissionError) as exc:
                return error_text(self.i18n, exc)
            self._saved(result.warnings)
            return None

        ItemDialog(self.i18n, self.services, None, False, submit, self).exec()
        self.refresh()

    def _edit_item(self, item: Item) -> None:
        tr = self.i18n.tr

        def submit(data: ItemInput, _opening: Quantity | None) -> str | None:
            # Price changes may need a password even for the Owner (Settings > Permissions).
            if data.sale != item.sale and not self.guard("price.sale", tr("item.field.sale")):
                return tr("error.not_allowed")
            if data.cost != item.cost and not self.guard("price.cost", tr("item.field.cost")):
                return tr("error.not_allowed")
            if data.unit != item.unit and self.services.items.has_history(item.id) \
                    and not self.guard("stock.adjust", tr("item.field.unit")):   # it reinterprets stock numbers
                return tr("error.not_allowed")
            try:
                result = self.services.items.update(self.user, item.id, data)
            except (ValueError, PermissionError) as exc:
                return error_text(self.i18n, exc)
            self._saved(result.warnings)
            return None

        has_history = self.services.items.has_history(item.id)
        ItemDialog(self.i18n, self.services, item, has_history, submit, self).exec()
        self.refresh()

    def _saved(self, warnings: tuple[str, ...]) -> None:
        key = "item.saved_warn" if WARN_COST_ABOVE_SALE in warnings else "item.saved"
        self.say(self.i18n.tr(key))

    def _adjust_selected(self) -> None:
        item = self._selected()
        if item is None:
            self.say(self.i18n.tr("items.select_first"), error=True)
            return

        def submit(kind: str, qty: Quantity, note: str | None) -> str | None:
            try:
                self.services.stock.adjust(self.user, item.id, kind, qty, note)
            except (ValueError, PermissionError) as exc:
                return error_text(self.i18n, exc)
            return None

        if AdjustDialog(self.i18n, item, submit, self).exec():
            self.say(self.i18n.tr("adjust.done"))
            self.refresh()

    def _import_items(self) -> None:
        dialog = ImportDialog(self.i18n, self.services, self.user, self)
        dialog.exec()
        self._reload_categories()
        self.refresh()
        if dialog.outcome:
            self.say(self.i18n.tr("import.done", created=dialog.outcome.created, updated=dialog.outcome.updated,
                                  skipped=dialog.outcome.skipped))

    def _manage(self, which: str, title_key: str) -> None:
        service = self.services.categories if which == "categories" else self.services.brands
        ManageListDialog(self.i18n, service, self.user, title_key, self).exec()
        self._reload_categories()
        self.refresh()
