from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QTableWidgetItem

from app.domain.user import User
from app.services.audit_service import describe_entry
from app.services.container import Services
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page
from app.ui.pages.users_page import local_time

PAGE_SIZE = 200


class AuditPage(Page):
    title_key = "audit.title"

    def __init__(self, i18n: I18n, services: Services, user: User, parent=None) -> None:
        super().__init__(i18n, parent)
        self.services = services
        self.user = user
        self._last_id: int | None = None
        self._can_load_more = False

        bar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.returnPressed.connect(self.refresh)
        self._refresh = QPushButton()
        self._refresh.setObjectName("PrimaryButton")
        self._refresh.clicked.connect(self.refresh)
        bar.addWidget(self._search, 1)
        bar.addWidget(self._refresh)
        self.layout_.addLayout(bar)

        self._table = self.make_table(4, selectable=False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self.layout_.addWidget(self._table, 1)

        foot = QHBoxLayout()
        self._more = QPushButton()
        self._more.clicked.connect(self._load_more)
        foot.addWidget(self.note, 1)
        foot.addWidget(self._more)
        self.layout_.addLayout(foot)
        self.retranslate()

    def retranslate(self) -> None:
        super().retranslate()
        tr = self.i18n.tr
        self._search.setPlaceholderText(tr("audit.search"))
        self._refresh.setText(tr("audit.refresh"))
        self._more.setText(tr("audit.more"))
        self._table.setHorizontalHeaderLabels([
            tr("audit.col.time"), tr("audit.col.user"), tr("audit.col.action"), tr("audit.col.details"),
        ])
        self.refresh()

    def refresh(self) -> None:
        self._table.setRowCount(0)
        self._last_id = None
        self._append(self.services.audit.search(self._search.text(), PAGE_SIZE))
        self._table.resizeColumnsToContents()

    def _load_more(self) -> None:
        self._append(self.services.audit.search(self._search.text(), PAGE_SIZE, self._last_id))

    def _append(self, rows) -> None:
        start = self._table.rowCount()
        self._table.setRowCount(start + len(rows))
        for offset, row in enumerate(rows):
            values = [local_time(row["at"], ""), row["username"] or "-", row["action"], describe_entry(row)]
            for col, text in enumerate(values):
                self._table.setItem(start + offset, col, QTableWidgetItem(text))
        if rows:
            self._last_id = rows[-1]["id"]
        self._can_load_more = len(rows) == PAGE_SIZE
        self._more.setEnabled(self._can_load_more)
        self.say(self.i18n.tr("audit.count", count=self._table.rowCount()))
