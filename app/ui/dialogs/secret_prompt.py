from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from app.ui.i18n.manager import I18n


class SecretPromptDialog(QDialog):
    """Asks for a password/PIN and keeps asking until `verify` accepts it or the user cancels.

    verify(secret) returns None on success, otherwise the (already translated) error text.
    Used for both 'confirm with your own password' and 'owner approval'.
    """

    def __init__(self, i18n: I18n, title: str, prompt: str, verify: Callable[[str], str | None], parent=None) -> None:
        super().__init__(parent)
        self._verify = verify
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        message = QLabel(prompt)
        message.setWordWrap(True)
        layout.addWidget(message)
        self._field = QLineEdit()
        self._field.setEchoMode(QLineEdit.EchoMode.Password)
        self._field.returnPressed.connect(self._submit)
        layout.addWidget(self._field)
        self._error = QLabel()
        self._error.setObjectName("ErrorLabel")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._error)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(i18n.tr("prompt.cancel"))
        cancel.clicked.connect(self.reject)
        ok = QPushButton(i18n.tr("prompt.ok"))
        ok.setObjectName("PrimaryButton")
        ok.setDefault(True)
        ok.clicked.connect(self._submit)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)
        self._field.setFocus()

    def _submit(self) -> None:
        secret = self._field.text()
        if not secret:
            return
        error = self._verify(secret)
        if error is None:
            self.accept()
            return
        self._error.setText(error)
        self._error.show()
        self._field.clear()
        self._field.setFocus()
