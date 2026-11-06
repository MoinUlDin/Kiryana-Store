from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QTableWidgetItem

from app.domain.user import User
from app.services.alert_service import ExpiryAlert
from app.services.container import Services
from app.ui.errors import error_text
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page

RED = QBrush(QColor("#B42318"))
AMBER = QBrush(QColor("#B54708"))


class AlertsPage(Page):
    title_key = "alerts.title"

    def __init__(self, i18n: I18n, services: Services, user: User, parent=None) -> None:
        super().__init__(i18n, parent)
        self.services = services
        self.user = user
        self._alerts: list[ExpiryAlert] = []

        bar = QHBoxLayout()
        self._within_label = QLabel()
        self._days = QSpinBox()
        self._days.setRange(0, 3650)
        self._days.setValue(services.alerts.expiry_days())
        self._days.valueChanged.connect(self._on_days_changed)
        self._only_expired = QCheckBox()
        self._only_expired.toggled.connect(lambda _c: self.refresh())
        self._writeoff = QPushButton()
        self._writeoff.setObjectName("PrimaryButton")
        self._writeoff.clicked.connect(self._on_writeoff)
        bar.addWidget(self._within_label)
        bar.addWidget(self._days)
        bar.addWidget(self._only_expired)
        bar.addStretch(1)
        bar.addWidget(self._writeoff)
        self.layout_.addLayout(bar)

        self._table = self.make_table(6)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self.layout_.addWidget(self._table, 1)
        foot = QHBoxLayout()
        self._count = QLabel()
        self._count.setObjectName("StatusNote")
        foot.addWidget(self.note, 1)
        foot.addWidget(self._count)
        self.layout_.addLayout(foot)
        self.retranslate()

    def retranslate(self) -> None:
        super().retranslate()
        tr = self.i18n.tr
        self._within_label.setText(tr("alerts.within"))
        self._only_expired.setText(tr("alerts.only_expired"))
        self._writeoff.setText(tr("alerts.writeoff"))
        self._table.setHorizontalHeaderLabels([
            tr("items.col.code"), tr("users.col.name"), tr("alerts.col.left"), tr("alerts.col.expiry"),
            tr("alerts.col.days"), tr("users.col.status"),
        ])
        self.refresh()

    def _on_days_changed(self, value: int) -> None:
        self.services.alerts.set_expiry_days(value)
        self.refresh()

    def refresh(self) -> None:
        tr = self.i18n.tr
        self._alerts = self.services.alerts.expiry_alerts(
            within_days=self._days.value(), expired_only=self._only_expired.isChecked())
        self._table.setRowCount(len(self._alerts))
        for row, alert in enumerate(self._alerts):
            status = tr("alerts.expired") if alert.expired else tr("alerts.soon")
            values = [alert.short_code, alert.display_name(self.i18n.lang),
                      f"{alert.qty_left.format()} {tr('unit.' + alert.unit)}", alert.expiry_date,
                      str(alert.days_left), status]
            for col, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if col in (3, 4, 5):
                    cell.setForeground(RED if alert.expired else AMBER)
                if col in (2, 4):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                self._table.setItem(row, col, cell)
        self._count.setText(tr("alerts.count", count=len(self._alerts)))
        self._update_buttons()

    def _selected(self) -> ExpiryAlert | None:
        row = self._table.currentRow()
        return self._alerts[row] if 0 <= row < len(self._alerts) else None

    def _update_buttons(self) -> None:
        self._writeoff.setEnabled(self._selected() is not None)

    def _on_writeoff(self) -> None:
        alert = self._selected()
        if alert is None or not self.guard("stock.adjust", self.i18n.tr("alerts.writeoff")):
            return
        try:
            self.services.stock.write_off_batch(self.user, alert.batch_id, self.i18n.tr("adjust.expiry"))
        except (ValueError, PermissionError) as exc:
            self.say(error_text(self.i18n, exc), error=True)
            return
        self.say(self.i18n.tr("alerts.writeoff_done"))
        self.refresh()
