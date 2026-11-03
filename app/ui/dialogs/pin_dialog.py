from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QLineEdit, QRadioButton

from app.ui.dialogs.user_dialogs import _FormDialog
from app.ui.i18n.manager import I18n


class NewPinDialog(_FormDialog):
    """submit(label, pin, perm_keys_or_None) -> None on success, or an error message."""

    def __init__(self, i18n: I18n, approvable: list[str],
                 submit: Callable[[str, str, list[str] | None], str | None], parent=None):
        super().__init__(i18n, i18n.tr("pins.new.title"), parent)
        self._submit = submit
        tr = i18n.tr
        self._label = QLineEdit()
        self._pin = self.password_field()
        self._confirm = self.password_field()
        self._all = QRadioButton(tr("pins.scope_all"))
        self._pick = QRadioButton(tr("pins.scope_pick"))
        self._all.setChecked(True)
        self._list = QListWidget()
        self._list.setMinimumHeight(180)
        for key in approvable:
            item = QListWidgetItem(tr(f"perm.{key}"))
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._list.addItem(item)
        self._list.setEnabled(False)
        self._pick.toggled.connect(self._list.setEnabled)

        self.form.addRow(tr("pins.col.label"), self._label)
        self.form.addRow(tr("pins.pin"), self._pin)
        self.form.addRow(tr("pins.confirm"), self._confirm)
        self.form.addRow(self._all)
        self.form.addRow(self._pick)
        self.form.addRow(self._list)
        self._label.setFocus()

    def _save(self) -> None:
        tr = self.i18n.tr
        if self._pin.text() != self._confirm.text():
            self.show_error(tr("pins.error.mismatch"))
            return
        keys = None
        if self._pick.isChecked():
            keys = [self._list.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self._list.count())
                    if self._list.item(i).checkState() == Qt.CheckState.Checked]
            if not keys:
                self.show_error(tr("pins.error.none_selected"))
                return
        error = self._submit(self._label.text(), self._pin.text(), keys)
        if error:
            self.show_error(error)
        else:
            self.accept()
