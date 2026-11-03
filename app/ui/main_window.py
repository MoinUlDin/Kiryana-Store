from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QLabel, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from app.domain.user import User
from app.services.approval_service import ApprovalLocked
from app.services.container import Services
from app.services.permission_service import Decision
from app.ui.actions import ActionRegistry
from app.ui.backstage import BackstageView
from app.ui.dialogs.secret_prompt import SecretPromptDialog
from app.ui.dialogs.user_dialogs import PasswordDialog
from app.ui.errors import error_text
from app.ui.i18n.manager import I18n
from app.ui.ribbon.bar import RibbonBar
from app.ui.ribbon.group import RibbonGroup
from app.ui.ribbon.tab import RibbonTab
from app.ui.ribbon_spec import TABS
from app.ui.pages.audit_page import AuditPage
from app.ui.pages.permissions_page import PermissionsPage
from app.ui.pages.pins_page import PinsPage
from app.ui.pages.users_page import UsersPage

log = logging.getLogger(__name__)
QUICK_ACCESS = ("new_bill", "hold_bill", "print_bill")
PAGES = {  # action id -> page class (each is created the first time it is opened)
    "users": UsersPage,
    "permissions": PermissionsPage,
    "approval_pins": PinsPage,
    "audit_log": AuditPage,
}


class MainWindow(QMainWindow):
    sign_out_requested = pyqtSignal()

    def __init__(self, i18n: I18n, services: Services, user: User) -> None:
        super().__init__()
        self.i18n = i18n
        self.services = services
        self.user = user
        self.signed_out = False
        self.resize(1200, 720)
        self.setMinimumSize(560, 420)

        self.actions = ActionRegistry(i18n, self)
        self.actions.attach(self)
        self.actions.triggered.connect(self._on_action)

        central = QWidget(self)
        central.setObjectName("Central")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.ribbon = RibbonBar(i18n, central)
        layout.addWidget(self.ribbon)
        for action_id in QUICK_ACCESS:
            self.ribbon.quick_access.add_action(self.actions.get(action_id))
        for spec in TABS:
            tab = RibbonTab(spec.key)
            for group_spec in spec.groups:
                group = RibbonGroup(group_spec.key, f"group.{group_spec.key}", group_spec.priority)
                for action_id, large in group_spec.items:
                    group.add_action(self.actions.get(action_id), large)
                tab.add_group(group)
            self.ribbon.add_tab(tab, f"tab.{spec.key}")
        self.ribbon.file_requested.connect(self._open_backstage)

        self.content = QStackedWidget(central)
        self._welcome = QLabel()
        self._welcome.setObjectName("Welcome")
        self._welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content.addWidget(self._welcome)
        self._pages: dict[str, QWidget] = {}
        layout.addWidget(self.content, 1)

        self.backstage = BackstageView(i18n, central)
        self.backstage.exit_requested.connect(self.close)
        self.backstage.sign_out_requested.connect(self._sign_out)

        self._user_label = QLabel()
        self.statusBar().addPermanentWidget(self._user_label)

        QShortcut(QKeySequence("Ctrl+F1"), self, activated=self.ribbon.toggle_collapsed)
        i18n.language_changed.connect(self._retranslate)
        self._retranslate()

    # ---- text ----------------------------------------------------------
    def _retranslate(self, _code: str = "") -> None:
        # The global language handler has already switched font/direction/stylesheet.
        tr = self.i18n.tr
        self.setWindowTitle(tr("app.title"))
        self.actions.retranslate()
        self.actions.refresh_permissions(self._visible_for_user)  # before measuring: hidden buttons take no width
        self.ribbon.retranslate()
        self.ribbon.refresh_visibility()
        self.backstage.retranslate()
        self._welcome.setText(tr("home.welcome"))
        self._user_label.setText(tr("status.user", name=self.user.display_name, role=tr(f"role.{self.user.role}")))
        for page in self._pages.values():
            page.retranslate()

    def _visible_for_user(self, perm: str) -> bool:
        """Hide only what this user can never get (not even with an Owner's approval)."""
        return self.services.access.decide(self.user, perm) is not Decision.DENIED

    # ---- actions + permission gate ---------------------------------------
    def _on_action(self, action_id: str) -> None:
        if action_id == "switch_language":
            self.i18n.set_language("ur" if self.i18n.lang == "en" else "en")
            return
        name = self.i18n.tr(f"act.{action_id}")
        perm = self.actions.perm_for(action_id)
        if perm and not self.guard(perm, name):
            return
        if action_id in PAGES:
            self._show_page(action_id)
        elif action_id == "change_password":
            self._change_own_password()
        else:
            self.statusBar().showMessage(self.i18n.tr("status.not_ready", name=name), 5000)

    def _show_page(self, action_id: str) -> None:
        page = self._pages.get(action_id)
        if page is None:
            page = PAGES[action_id](self.i18n, self.services, self.user)
            self._pages[action_id] = page
            self.content.addWidget(page)
        else:
            page.refresh()
        self.content.setCurrentWidget(page)
        self.statusBar().clearMessage()

    def _change_own_password(self) -> None:
        def submit(new_password: str, old_password: str | None) -> str | None:
            try:
                self.services.auth.change_password(self.user, self.user.id, new_password, old_password)
            except (ValueError, PermissionError) as exc:
                return error_text(self.i18n, exc)
            return None

        dialog = PasswordDialog(self.i18n, self.i18n.tr("password.change.title"), submit, ask_old=True, parent=self)
        if dialog.exec():
            self.statusBar().showMessage(self.i18n.tr("password.changed"), 5000)

    def guard(self, perm: str, action_name: str) -> bool:
        """True if the user may proceed. Shows the password / Owner-approval prompt when needed.
        Every real feature screen will call this before doing a restricted action."""
        tr = self.i18n.tr
        access = self.services.access
        decision = access.decide(self.user, perm)
        if decision is Decision.ALLOWED:
            return True
        if decision is Decision.DENIED:
            self.statusBar().showMessage(tr("access.denied", name=action_name), 5000)
            return False

        if decision is Decision.NEEDS_PASSWORD:
            title, prompt = tr("reauth.title"), tr("reauth.prompt", action=action_name)

            def verify(secret: str) -> str | None:
                return None if access.confirm_password(self.user, perm, secret) else tr("reauth.error")
        else:
            title, prompt = tr("approval.title"), tr("approval.prompt", action=action_name)

            def verify(secret: str) -> str | None:
                try:
                    approved = access.request_approval(self.user, perm, secret)
                except ApprovalLocked as locked:
                    return tr("approval.locked", seconds=locked.seconds)
                return None if approved else tr("approval.error")

        dialog = SecretPromptDialog(self.i18n, title, prompt, verify, self)
        return dialog.exec() == SecretPromptDialog.DialogCode.Accepted

    # ---- backstage / sign out -------------------------------------------
    def _open_backstage(self) -> None:
        self.backstage.open_view()
        self.backstage.setFocus()

    def _sign_out(self) -> None:
        self.signed_out = True
        self.close()

    def closeEvent(self, event) -> None:
        try:
            self.i18n.language_changed.disconnect(self._retranslate)
        except TypeError:
            pass
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.backstage.isVisible():
            self.backstage.setGeometry(self.centralWidget().rect())
