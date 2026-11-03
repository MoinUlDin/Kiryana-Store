from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from app.ui.i18n.manager import I18n


class _FormDialog(QDialog):
    def __init__(self, i18n: I18n, title: str, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        self.form = QFormLayout()
        outer.addLayout(self.form)
        self._error = QLabel()
        self._error.setObjectName("ErrorLabel")
        self._error.setWordWrap(True)
        self._error.hide()
        outer.addWidget(self._error)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton(i18n.tr("dialog.cancel"))
        cancel.clicked.connect(self.reject)
        save = QPushButton(i18n.tr("dialog.save"))
        save.setObjectName("PrimaryButton")
        save.setDefault(True)
        save.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(save)
        outer.addLayout(row)

    def password_field(self) -> QLineEdit:
        field = QLineEdit()
        field.setEchoMode(QLineEdit.EchoMode.Password)
        return field

    def show_error(self, text: str) -> None:
        self._error.setText(text)
        self._error.show()

    def _save(self) -> None:
        raise NotImplementedError


class AddUserDialog(_FormDialog):
    """submit(name, username, role, password) -> None on success, or an error message."""

    def __init__(self, i18n: I18n, roles: list[str], submit: Callable[[str, str, str, str], str | None], parent=None):
        super().__init__(i18n, i18n.tr("users.add.title"), parent)
        self._submit = submit
        tr = i18n.tr
        self._name = QLineEdit()
        self._username = QLineEdit()
        self._role = QComboBox()
        for role in roles:
            self._role.addItem(tr(f"role.{role}"), role)
        self._password = self.password_field()
        self._confirm = self.password_field()
        self.form.addRow(tr("firstrun.display_name"), self._name)
        self.form.addRow(tr("login.username"), self._username)
        self.form.addRow(tr("users.col.role"), self._role)
        self.form.addRow(tr("login.password"), self._password)
        self.form.addRow(tr("firstrun.confirm"), self._confirm)
        self._name.setFocus()

    def _save(self) -> None:
        if self._password.text() != self._confirm.text():
            self.show_error(self.i18n.tr("password.mismatch"))
            return
        error = self._submit(self._name.text(), self._username.text(), self._role.currentData(), self._password.text())
        if error:
            self.show_error(error)
        else:
            self.accept()


class PasswordDialog(_FormDialog):
    """submit(new_password, old_password_or_None) -> None on success, or an error message."""

    def __init__(self, i18n: I18n, title: str, submit: Callable[[str, str | None], str | None],
                 ask_old: bool = False, parent=None):
        super().__init__(i18n, title, parent)
        self._submit = submit
        self._old = self.password_field() if ask_old else None
        self._new = self.password_field()
        self._confirm = self.password_field()
        if self._old is not None:
            self.form.addRow(i18n.tr("password.old"), self._old)
        self.form.addRow(i18n.tr("password.new"), self._new)
        self.form.addRow(i18n.tr("firstrun.confirm"), self._confirm)
        (self._old or self._new).setFocus()

    def _save(self) -> None:
        if self._new.text() != self._confirm.text():
            self.show_error(self.i18n.tr("password.mismatch"))
            return
        error = self._submit(self._new.text(), self._old.text() if self._old else None)
        if error:
            self.show_error(error)
        else:
            self.accept()
