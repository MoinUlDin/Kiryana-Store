from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidgetItem

from app.domain.permissions import PERMISSIONS
from app.domain.user import ROLE_CASHIER, ROLE_OWNER, User
from app.services.container import Services
from app.ui.errors import error_text
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page

# column -> (role, what it edits)
CASHIER_ALLOWED, CASHIER_ASK, OWNER_ASK = 1, 2, 3


class PermissionsPage(Page):
    title_key = "perms.title"
    intro_key = "perms.intro"

    def __init__(self, i18n: I18n, services: Services, user: User, parent=None) -> None:
        super().__init__(i18n, parent)
        self.services = services
        self.user = user
        self._table = self.make_table(4, selectable=False)
        self._table.itemChanged.connect(self._on_item_changed)
        self.layout_.addWidget(self._table, 1)
        self.layout_.addWidget(self.note)
        self.retranslate()

    def retranslate(self) -> None:
        super().retranslate()
        tr = self.i18n.tr
        self._table.setHorizontalHeaderLabels([
            tr("perms.col.perm"), tr("perms.col.cashier_allowed"),
            tr("perms.col.cashier_ask"), tr("perms.col.owner_ask"),
        ])
        self.refresh()

    def refresh(self) -> None:
        tr = self.i18n.tr
        cashier = self.services.permissions.table(ROLE_CASHIER)
        owner = self.services.permissions.table(ROLE_OWNER)
        self._table.blockSignals(True)
        self._table.setRowCount(len(PERMISSIONS))
        for row, perm in enumerate(PERMISSIONS):
            label = QTableWidgetItem(tr(f"perm.{perm.key}"))
            label.setData(Qt.ItemDataRole.UserRole, perm.key)
            self._table.setItem(row, 0, label)
            cells = (
                (CASHIER_ALLOWED, cashier[perm.key][0], perm.approvable),
                (CASHIER_ASK, cashier[perm.key][1], not perm.locked_ask),
                (OWNER_ASK, owner[perm.key][1], perm.owner_allowed and not perm.locked_ask),
            )
            for col, checked, editable in cells:
                item = QTableWidgetItem()
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                flags = Qt.ItemFlag.ItemIsEnabled
                if editable:
                    flags |= Qt.ItemFlag.ItemIsUserCheckable
                else:
                    item.setToolTip(tr("perms.fixed"))
                item.setFlags(flags)
                self._table.setItem(row, col, item)
        self._table.resizeColumnsToContents()
        self._table.blockSignals(False)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        col = item.column()
        if col == 0:
            return
        key = self._table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        value = item.checkState() == Qt.CheckState.Checked
        perms = self.services.permissions
        try:
            if col == CASHIER_ALLOWED:
                perms.set_allowed(self.user, ROLE_CASHIER, key, value)
            elif col == CASHIER_ASK:
                perms.set_ask_password(self.user, ROLE_CASHIER, key, value)
            else:
                perms.set_ask_password(self.user, ROLE_OWNER, key, value)
        except PermissionError as exc:
            self._table.blockSignals(True)  # put the box back the way it was
            item.setCheckState(Qt.CheckState.Unchecked if value else Qt.CheckState.Checked)
            self._table.blockSignals(False)
            self.say(error_text(self.i18n, exc), error=True)
            return
        self.say(self.i18n.tr("perms.saved"))
