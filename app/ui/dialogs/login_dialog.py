from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from app.domain.user import User
from app.services.auth_service import AuthService, AuthStatus
from app.ui.i18n.manager import I18n


class LoginDialog(QDialog):
    def __init__(self, i18n: I18n, auth: AuthService, parent=None) -> None:
        super().__init__(parent)
        self._i18n = i18n
        self._auth = auth
        self.user: User | None = None
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        self._heading = QLabel()
        self._heading.setObjectName("PageTitle")
        layout.addWidget(self._heading)

        self._user_label = QLabel()
        layout.addWidget(self._user_label)
        self._username = QComboBox()
        self._username.setEditable(True)  # pick from the list or type
        for user in auth.list_users():
            self._username.addItem(user.username)
        self._username.setCurrentIndex(-1)
        layout.addWidget(self._username)

        self._pass_label = QLabel()
        layout.addWidget(self._pass_label)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.returnPressed.connect(self._submit)
        layout.addWidget(self._password)

        self._error = QLabel()
        self._error.setObjectName("ErrorLabel")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._error)

        row = QHBoxLayout()
        self._language = QPushButton()
        self._language.clicked.connect(self._toggle_language)
        self._quit = QPushButton()
        self._quit.clicked.connect(self.reject)
        self._submit_button = QPushButton()
        self._submit_button.setObjectName("PrimaryButton")
        self._submit_button.setDefault(True)
        self._submit_button.clicked.connect(self._submit)
        row.addWidget(self._language)
        row.addStretch(1)
        row.addWidget(self._quit)
        row.addWidget(self._submit_button)
        layout.addLayout(row)

        i18n.language_changed.connect(self._retranslate)
        self._retranslate()
        self._username.setFocus()

    def _retranslate(self, _code: str = "") -> None:
        tr = self._i18n.tr
        self.setWindowTitle(tr("app.title"))
        self._heading.setText(tr("login.title"))
        self._user_label.setText(tr("login.username"))
        self._pass_label.setText(tr("login.password"))
        self._submit_button.setText(tr("login.submit"))
        self._quit.setText(tr("login.quit"))
        self._language.setText(tr("act.switch_language"))
        self._error.hide()

    def _toggle_language(self) -> None:
        self._i18n.set_language("ur" if self._i18n.lang == "en" else "en")

    def _submit(self) -> None:
        username = self._username.currentText().strip()
        password = self._password.text()
        if not username or not password:
            return
        result = self._auth.authenticate(username, password)
        if result.status is AuthStatus.OK:
            self.user = result.user
            self.accept()
            return
        key = {
            AuthStatus.LOCKED: "login.error.locked",
            AuthStatus.INACTIVE: "login.error.inactive",
        }.get(result.status, "login.error.invalid")
        self._error.setText(self._i18n.tr(key, minutes=result.locked_minutes))
        self._error.show()
        self._password.clear()
        self._password.setFocus()

    def closeEvent(self, event) -> None:
        try:
            self._i18n.language_changed.disconnect(self._retranslate)
        except TypeError:
            pass
        super().closeEvent(event)

    def done(self, result: int) -> None:  # accept()/reject() do not always trigger closeEvent
        try:
            self._i18n.language_changed.disconnect(self._retranslate)
        except TypeError:
            pass
        super().done(result)
