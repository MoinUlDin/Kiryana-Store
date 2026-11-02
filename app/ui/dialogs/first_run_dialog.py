from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from app.db.connection import atomic
from app.domain.user import ROLE_OWNER, ROLE_SUPERADMIN, SYSTEM
from app.security.passwords import ValidationError
from app.services.container import Services
from app.ui.i18n.manager import I18n


class FirstRunDialog(QDialog):
    """Shown once on a fresh database: creates the Super Admin and the Owner together."""

    def __init__(self, i18n: I18n, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._i18n = i18n
        self._services = services
        self.setModal(True)
        self.setMinimumWidth(460)
        tr = i18n.tr
        self.setWindowTitle(tr("firstrun.title"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        title = QLabel(tr("firstrun.title"))
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        intro = QLabel(tr("firstrun.intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._sa = self._account_box(tr("firstrun.superadmin"), default_username="admin")
        self._owner = self._account_box(tr("firstrun.owner"))
        layout.addWidget(self._sa["box"])
        layout.addWidget(self._owner["box"])

        self._error = QLabel()
        self._error.setObjectName("ErrorLabel")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._error)

        row = QHBoxLayout()
        row.addStretch(1)
        create = QPushButton(tr("firstrun.create"))
        create.setObjectName("PrimaryButton")
        create.setDefault(True)
        create.clicked.connect(self._create)
        row.addWidget(create)
        layout.addLayout(row)

    def _account_box(self, title: str, default_username: str = "") -> dict:
        tr = self._i18n.tr
        box = QGroupBox(title)
        form = QFormLayout(box)
        fields = {
            "box": box,
            "name": QLineEdit(),
            "username": QLineEdit(default_username),
            "password": QLineEdit(),
            "confirm": QLineEdit(),
        }
        fields["password"].setEchoMode(QLineEdit.EchoMode.Password)
        fields["confirm"].setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(tr("firstrun.display_name"), fields["name"])
        form.addRow(tr("login.username"), fields["username"])
        form.addRow(tr("login.password"), fields["password"])
        form.addRow(tr("firstrun.confirm"), fields["confirm"])
        return fields

    def _show_error(self, text: str) -> None:
        self._error.setText(text)
        self._error.show()

    def _create(self) -> None:
        tr = self._i18n.tr
        sa, owner = self._sa, self._owner
        for account in (sa, owner):
            if account["password"].text() != account["confirm"].text():
                self._show_error(tr("firstrun.error.mismatch"))
                return
        if sa["username"].text().strip().lower() == owner["username"].text().strip().lower():
            self._show_error(tr("firstrun.error.same_username"))
            return
        auth = self._services.auth
        try:
            with atomic(self._services.conn):  # both accounts or neither
                admin = auth.create_user(SYSTEM, sa["username"].text(), sa["name"].text(),
                                         ROLE_SUPERADMIN, sa["password"].text())
                auth.create_user(admin, owner["username"].text(), owner["name"].text(),
                                 ROLE_OWNER, owner["password"].text())
        except ValidationError as exc:
            self._show_error(tr(exc.code, **exc.params))
            return
        self.accept()
