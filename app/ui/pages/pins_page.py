from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTableWidgetItem

from app.domain.permissions import PERMISSIONS
from app.domain.user import User
from app.services.container import Services
from app.ui.dialogs.pin_dialog import NewPinDialog
from app.ui.errors import error_text
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page
from app.ui.pages.users_page import local_time

APPROVABLE = [p.key for p in PERMISSIONS if p.approvable]


class PinsPage(Page):
    title_key = "pins.title"
    intro_key = "pins.intro"

    def __init__(self, i18n: I18n, services: Services, user: User, parent=None) -> None:
        super().__init__(i18n, parent)
        self.services = services
        self.user = user
        self._pins = []

        bar = QHBoxLayout()
        self._new = QPushButton()
        self._new.setObjectName("PrimaryButton")
        self._new.clicked.connect(self._on_new)
        self._revoke = QPushButton()
        self._revoke.clicked.connect(self._on_revoke)
        bar.addWidget(self._new)
        bar.addWidget(self._revoke)
        bar.addStretch(1)
        self.layout_.addLayout(bar)

        self._table = self.make_table(4)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self.layout_.addWidget(self._table, 1)
        self.layout_.addWidget(self.note)
        self.retranslate()

    def retranslate(self) -> None:
        super().retranslate()
        tr = self.i18n.tr
        self._new.setText(tr("pins.new"))
        self._revoke.setText(tr("pins.revoke"))
        self._table.setHorizontalHeaderLabels([
            tr("pins.col.label"), tr("pins.col.actions"), tr("role.owner"), tr("pins.col.created"),
        ])
        self.refresh()

    def refresh(self) -> None:
        tr = self.i18n.tr
        self._pins = self.services.approvals.list_pins(self.user)
        self._table.setRowCount(len(self._pins))
        for row, pin in enumerate(self._pins):
            scope = tr("pins.all") if pin.perm_keys is None else tr("pins.some", count=len(pin.perm_keys))
            tip = "" if pin.perm_keys is None else "\n".join(tr(f"perm.{k}") for k in pin.perm_keys)
            values = [pin.label, scope, pin.owner_name, local_time(pin.created_at, "")]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col == 1 and tip:
                    item.setToolTip(tip)
                self._table.setItem(row, col, item)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self._revoke.setEnabled(0 <= self._table.currentRow() < len(self._pins))

    def _on_new(self) -> None:
        def submit(label: str, pin: str, keys: list[str] | None) -> str | None:
            try:
                self.services.approvals.create_pin(self.user, label, pin, keys)
            except (ValueError, PermissionError) as exc:
                return error_text(self.i18n, exc)
            return None

        if NewPinDialog(self.i18n, APPROVABLE, submit, self).exec():
            self.say(self.i18n.tr("pins.created"))
            self.refresh()

    def _on_revoke(self) -> None:
        row = self._table.currentRow()
        if not 0 <= row < len(self._pins):
            return
        try:
            self.services.approvals.revoke_pin(self.user, self._pins[row].id)
        except PermissionError as exc:
            self.say(error_text(self.i18n, exc), error=True)
            return
        self.say(self.i18n.tr("pins.revoked"))
        self.refresh()
