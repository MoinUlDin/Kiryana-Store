from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTableWidgetItem

from app.domain.clock import from_iso
from app.domain.user import User
from app.services.container import Services
from app.ui.dialogs.user_dialogs import AddUserDialog, PasswordDialog
from app.ui.errors import error_text
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page


def local_time(iso: str | None, never: str) -> str:
    return from_iso(iso).astimezone().strftime("%Y-%m-%d %H:%M") if iso else never


class UsersPage(Page):
    title_key = "users.title"

    def __init__(self, i18n: I18n, services: Services, user: User, parent=None) -> None:
        super().__init__(i18n, parent)
        self.services = services
        self.user = user
        self._accounts = []

        bar = QHBoxLayout()
        self._add = QPushButton()
        self._add.setObjectName("PrimaryButton")
        self._add.clicked.connect(self._on_add)
        self._reset = QPushButton()
        self._reset.clicked.connect(self._on_reset)
        self._toggle = QPushButton()
        self._toggle.clicked.connect(self._on_toggle)
        for button in (self._add, self._reset, self._toggle):
            bar.addWidget(button)
        bar.addStretch(1)
        self.layout_.addLayout(bar)

        self._table = self.make_table(5)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self.layout_.addWidget(self._table, 1)
        self.layout_.addWidget(self.note)
        self.retranslate()

    def retranslate(self) -> None:
        super().retranslate()
        tr = self.i18n.tr
        self._add.setText(tr("users.add"))
        self._reset.setText(tr("users.reset"))
        self._table.setHorizontalHeaderLabels([
            tr("login.username"), tr("users.col.name"), tr("users.col.role"),
            tr("users.col.status"), tr("users.col.last_login"),
        ])
        self.refresh()

    def refresh(self) -> None:
        tr = self.i18n.tr
        selected = self._selected_id()
        self._accounts = self.services.auth.list_accounts(self.user)
        self._table.setRowCount(len(self._accounts))
        for row, account in enumerate(self._accounts):
            values = [
                account.user.username, account.user.display_name, tr(f"role.{account.user.role}"),
                tr("users.status.active" if account.is_active else "users.status.disabled"),
                local_time(account.last_login_at, tr("users.never")),
            ]
            for col, text in enumerate(values):
                self._table.setItem(row, col, QTableWidgetItem(text))
            if account.user.id == selected:
                self._table.selectRow(row)
        self._update_buttons()

    def _selected_id(self) -> int | None:
        row = self._table.currentRow()
        return self._accounts[row].user.id if 0 <= row < len(self._accounts) else None

    def _selected(self):
        row = self._table.currentRow()
        return self._accounts[row] if 0 <= row < len(self._accounts) else None

    def _update_buttons(self) -> None:
        account = self._selected()
        auth = self.services.auth
        manageable = account is not None and auth.can_manage(self.user, account.user.role)
        is_self = account is not None and account.user.id == self.user.id
        self._add.setEnabled(bool(auth.creatable_roles(self.user)))
        self._reset.setEnabled(manageable and not is_self)
        self._toggle.setEnabled(manageable and not is_self)
        tr = self.i18n.tr
        self._toggle.setText(tr("users.disable") if (account is None or account.is_active) else tr("users.enable"))

    # ---- actions ---------------------------------------------------------
    def _on_add(self) -> None:
        auth = self.services.auth

        def submit(name: str, username: str, role: str, password: str) -> str | None:
            try:
                auth.create_user(self.user, username, name, role, password)
            except (ValueError, PermissionError) as exc:
                return error_text(self.i18n, exc)
            return None

        if AddUserDialog(self.i18n, auth.creatable_roles(self.user), submit, self).exec():
            self.say(self.i18n.tr("users.created"))
            self.refresh()

    def _on_reset(self) -> None:
        account = self._selected()
        if account is None:
            return

        def submit(new_password: str, _old: str | None) -> str | None:
            try:
                self.services.auth.change_password(self.user, account.user.id, new_password)
            except (ValueError, PermissionError) as exc:
                return error_text(self.i18n, exc)
            return None

        title = f"{self.i18n.tr('password.reset.title')}: {account.user.username}"
        if PasswordDialog(self.i18n, title, submit, ask_old=False, parent=self).exec():
            self.say(self.i18n.tr("password.changed"))

    def _on_toggle(self) -> None:
        account = self._selected()
        if account is None:
            return
        try:
            self.services.auth.set_active(self.user, account.user.id, not account.is_active)
        except (ValueError, PermissionError) as exc:
            self.say(error_text(self.i18n, exc), error=True)
            return
        self.say(self.i18n.tr("users.updated"))
        self.refresh()
