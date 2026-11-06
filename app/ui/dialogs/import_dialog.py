from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QTableWidgetItem, QVBoxLayout,
)

from app.domain.user import User
from app.infra.spreadsheet import SpreadsheetError, write_template
from app.security.passwords import ValidationError
from app.services.container import Services
from app.services.import_service import ImportOutcome, ImportPreview, RowIssue
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page

FIELD_LABEL = {
    "short_code": "item.field.short_code", "name_en": "item.field.name_en", "name_ur": "item.field.name_ur",
    "category": "items.col.category", "brand": "item.field.brand", "unit": "items.col.unit",
    "sale": "items.col.price", "cost": "item.field.cost", "barcode": "item.field.barcode",
    "opening": "item.field.opening", "low": "item.field.low", "tax": "item.field.tax", "fraction": "item.field.fraction",
}
RED = QBrush(QColor("#B42318"))
AMBER = QBrush(QColor("#B54708"))
GREEN = QBrush(QColor("#067647"))
COLORS = {"error": RED, "skip": AMBER, "create": GREEN, "update": GREEN}


class ImportDialog(QDialog):
    """Pick a file, see exactly what would happen to every row, then import the good ones."""

    def __init__(self, i18n: I18n, services: Services, user: User, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self._services = services
        self._user = user
        self._rows: list[list[str]] | None = None
        self._preview: ImportPreview | None = None
        self.outcome: ImportOutcome | None = None
        tr = i18n.tr
        self.setWindowTitle(tr("import.title"))
        self.resize(940, 640)

        layout = QVBoxLayout(self)
        hint = QLabel(tr("import.hint"))
        hint.setWordWrap(True)
        hint.setObjectName("StatusNote")
        layout.addWidget(hint)

        bar = QHBoxLayout()
        choose = QPushButton(tr("import.choose"))
        choose.setObjectName("PrimaryButton")
        choose.clicked.connect(self._choose_file)
        template = QPushButton(tr("import.template"))
        template.clicked.connect(self._save_template)
        bar.addWidget(choose)
        bar.addWidget(template)
        bar.addStretch(1)
        layout.addLayout(bar)

        self._update_existing = QCheckBox(tr("import.update_existing"))
        self._update_existing.toggled.connect(lambda _c: self._recompute())
        self._only_problems = QCheckBox(tr("import.only_problems"))
        self._only_problems.setChecked(True)
        self._only_problems.toggled.connect(lambda _c: self._render())
        layout.addWidget(self._update_existing)
        layout.addWidget(self._only_problems)

        self._error = QLabel()
        self._error.setObjectName("ErrorLabel")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._error)
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        self._table = Page.make_table(5, selectable=False)
        self._table.setHorizontalHeaderLabels([tr("import.col.row"), tr("items.col.code"), tr("users.col.name"),
                                               tr("import.col.result"), tr("import.col.details")])
        layout.addWidget(self._table, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton(tr("lists.close"))
        close.clicked.connect(self.accept)
        self._import = QPushButton()
        self._import.setObjectName("PrimaryButton")
        self._import.setEnabled(False)
        self._import.clicked.connect(self._do_import)
        row.addWidget(close)
        row.addWidget(self._import)
        layout.addLayout(row)

    # ---- helpers -----------------------------------------------------------------
    def _issue_text(self, issue: RowIssue) -> str:
        tr = self.i18n.tr
        text = tr(issue.code, **issue.params)
        if issue.column in FIELD_LABEL:
            text = f"{tr(FIELD_LABEL[issue.column])}: {text}"
        return text

    def _show_error(self, text: str | None) -> None:
        self._error.setVisible(bool(text))
        self._error.setText(text or "")

    # ---- steps ---------------------------------------------------------------------
    def _save_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self.i18n.tr("import.template"), "items_template.xlsx",
                                              "Excel (*.xlsx)")
        if path:
            write_template(path)
            self._summary.setText(self.i18n.tr("import.template_saved"))

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.i18n.tr("import.title"), "",
                                              "Excel / CSV (*.xlsx *.xlsm *.csv)")
        if not path:
            return
        self.outcome = None
        try:
            self._rows = self._services.importer.read_file(path)
        except SpreadsheetError as exc:
            self._rows = None
            self._show_error(self.i18n.tr(exc.code, **exc.params))
            self._preview = None
            self._render()
            return
        self._show_error(None)
        self._recompute()

    def _recompute(self) -> None:
        if self._rows is None:
            return
        self.outcome = None
        self._preview = self._services.importer.preview(self._rows, self._update_existing.isChecked())
        self._render()

    def _render(self) -> None:
        tr = self.i18n.tr
        prev = self._preview
        self._table.setRowCount(0)
        self._import.setEnabled(False)
        self._import.setText(tr("import.button", count=0))
        if prev is None:
            return
        if prev.file_issues:
            self._show_error(" ".join(self._issue_text(i) for i in prev.file_issues))
            self._summary.setText("")
            return
        self._show_error(None)
        text = tr("import.summary", rows=len(prev.rows), create=prev.count("create"), update=prev.count("update"),
                  skip=prev.count("skip"), error=prev.count("error"))
        if prev.new_categories or prev.new_brands:
            text += "\n" + tr("import.new_lists", categories=", ".join(prev.new_categories) or "-",
                              brands=", ".join(prev.new_brands) or "-")
        self._summary.setText(text)
        shown = [r for r in prev.rows if not self._only_problems.isChecked() or r.action in ("error", "skip")]
        self._table.setRowCount(len(shown))
        for index, result in enumerate(shown):
            details = "; ".join(self._issue_text(i) for i in result.issues)
            values = [str(result.row), result.code, result.name, tr(f"import.result.{result.action}"), details]
            for col, cell_text in enumerate(values):
                cell = QTableWidgetItem(cell_text)
                if col == 3:
                    cell.setForeground(COLORS[result.action])
                self._table.setItem(index, col, cell)
        self._table.resizeColumnsToContents()
        self._import.setText(tr("import.button", count=prev.importable))
        self._import.setEnabled(prev.importable > 0)

    def _do_import(self) -> None:
        if self._preview is None:
            return
        tr = self.i18n.tr
        try:
            outcome = self._services.importer.apply(self._user, self._preview)
        except (ValidationError, ValueError):
            self._show_error(tr("import.error.apply"))   # nothing was saved: the import is all-or-nothing
            return
        self.outcome = outcome
        self._show_error(None)
        text = tr("import.done", created=outcome.created, updated=outcome.updated, skipped=outcome.skipped)
        if outcome.errors:
            text += "\n" + tr("import.note_fix")
        self._summary.setText(text)
        self._import.setEnabled(False)
