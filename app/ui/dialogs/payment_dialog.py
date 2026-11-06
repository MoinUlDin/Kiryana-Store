from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from app.domain.money import Money
from app.domain.parsing import parse_money
from app.domain.sale import PaymentInput
from app.security.passwords import ValidationError
from app.ui.i18n.manager import I18n


class PaymentDialog(QDialog):
    """Cash (with change), card and mobile wallet, in any mix. After accept(): .payments and .change.
    The payments always add up to the bill exactly; cash received above what is due becomes change."""

    def __init__(self, i18n: I18n, payable: Money, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self._payable = payable
        self.payments: list[PaymentInput] = []
        self.change = Money(0)
        tr = i18n.tr
        self.setWindowTitle(tr("pay.title"))
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(QLabel(tr("pay.payable")))
        total = QLabel(payable.format())
        total.setObjectName("GrandTotal")
        layout.addWidget(total)

        form = QFormLayout()
        self._cash = QLineEdit()
        self._cash.setPlaceholderText(tr("pay.exact"))
        self._card = QLineEdit()
        self._wallet = QLineEdit()
        form.addRow(tr("pay.cash_given"), self._cash)
        form.addRow(tr("pay.card"), self._card)
        form.addRow(tr("pay.wallet"), self._wallet)
        layout.addLayout(form)

        self._info = QLabel()
        self._info.setObjectName("ChangeLabel")
        layout.addWidget(self._info)
        self._error = QLabel()
        self._error.setObjectName("ErrorLabel")
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton(tr("dialog.cancel"))
        cancel.clicked.connect(self.reject)
        self._ok = QPushButton(tr("pay.confirm"))
        self._ok.setObjectName("CheckoutButton")
        self._ok.setDefault(True)
        self._ok.clicked.connect(self._confirm)
        row.addWidget(cancel)
        row.addWidget(self._ok)
        layout.addLayout(row)

        for field in (self._cash, self._card, self._wallet):
            field.textChanged.connect(self._update)
            field.returnPressed.connect(self._confirm)
        self._update()
        self._cash.setFocus()

    def _amounts(self) -> tuple[Money, Money, Money]:
        """(cash due, card, wallet). Raises ValidationError for unreadable numbers or card+wallet over the total."""
        card = parse_money(self._card.text(), allow_empty=True)
        wallet = parse_money(self._wallet.text(), allow_empty=True)
        cash_due = self._payable - card - wallet
        if cash_due.paisa < 0:
            raise ValidationError("pay.too_much")
        return cash_due, card, wallet

    def _update(self, *_args) -> None:
        tr = self.i18n.tr
        self._error.setText("")
        self._info.setText("")
        self._ok.setEnabled(False)
        try:
            cash_due, _card, _wallet = self._amounts()
            given = parse_money(self._cash.text(), allow_empty=True) if self._cash.text().strip() else cash_due
        except ValidationError as exc:
            self._error.setText(tr(exc.code if exc.code.startswith("pay.") else "error.price_invalid"))
            return
        if given < cash_due:
            self._info.setText(tr("pay.short", amount=(cash_due - given).format()))
            return
        self._info.setText(f"{tr('pay.change')}: {(given - cash_due).format()}")
        self._ok.setEnabled(True)

    def _confirm(self) -> None:
        if not self._ok.isEnabled():
            return
        cash_due, card, wallet = self._amounts()
        given = parse_money(self._cash.text(), allow_empty=True) if self._cash.text().strip() else cash_due
        self.payments = [PaymentInput(method, amount) for method, amount in
                         (("cash", cash_due), ("card", card), ("wallet", wallet)) if amount.paisa > 0]
        self.change = given - cash_due
        self.accept()
