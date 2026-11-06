from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidgetItem, QVBoxLayout

from app.domain.purchase import Purchase, PurchaseLine
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page


class PurchaseViewDialog(QDialog):
    """Read-only view of one saved purchase."""

    def __init__(self, i18n: I18n, purchase: Purchase, lines: list[PurchaseLine], parent=None) -> None:
        super().__init__(parent)
        tr = i18n.tr
        self.setWindowTitle(f"{tr('purchase.view.title')} #{purchase.id}")
        self.resize(820, 460)
        layout = QVBoxLayout(self)
        head = QLabel(" | ".join(filter(None, [
            purchase.purchase_date, purchase.supplier_name, purchase.invoice_no,
            f"{tr('purchases.col.total')}: {purchase.total.format()}",
            f"{tr('purchases.col.paid')}: {purchase.paid.format()}",
            f"{tr('purchases.col.due')}: {purchase.due.format()}",
        ])))
        head.setWordWrap(True)
        layout.addWidget(head)
        table = Page.make_table(6, selectable=False)
        table.setHorizontalHeaderLabels([
            tr("purchase.col.item"), tr("purchase.col.qty"), tr("purchase.col.unit_cost"),
            tr("purchase.col.line_total"), tr("purchase.col.expiry"), tr("purchase.col.avg"),
        ])
        table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            name = line.item_name_ur if (i18n.lang == "ur" and line.item_name_ur) else line.item_name_en
            values = [name, f"{line.qty.format()} {tr('unit.' + line.unit)}", line.unit_cost.format(),
                      line.line_total.format(), line.expiry_date or "-",
                      f"{line.avg_before.format()} \u2192 {line.avg_after.format()}"]
            for col, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if col in (1, 2, 3):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                table.setItem(row, col, cell)
        table.resizeColumnsToContents()
        layout.addWidget(table, 1)
        close = QPushButton(tr("lists.close"))
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
