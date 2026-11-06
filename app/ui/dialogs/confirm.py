from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox, QWidget

from app.ui.i18n.manager import I18n


def confirm(i18n: I18n, parent: QWidget | None, title: str, text: str) -> bool:
    """A Yes/No question with translated buttons. Returns True only on Yes (No is the default)."""
    box = QMessageBox(QMessageBox.Icon.Question, title, text, QMessageBox.StandardButton.NoButton, parent)
    yes = box.addButton(i18n.tr("prompt.yes"), QMessageBox.ButtonRole.YesRole)
    no = box.addButton(i18n.tr("prompt.no"), QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(no)
    box.exec()
    return box.clickedButton() is yes
