from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidgetItem, QVBoxLayout

from app.domain.cart import Cart
from app.domain.entry import split_quantity
from app.domain.item import Item
from app.domain.money import Money
from app.domain.pricing import Discount
from app.domain.quantity import Quantity
from app.domain.sale import CheckoutInput, SaleLineInput
from app.domain.user import User
from app.security.passwords import ValidationError
from app.services.container import Services
from app.ui.dialogs.confirm import confirm
from app.ui.dialogs.discount_dialog import DiscountDialog
from app.ui.dialogs.item_picker import ItemPickerDialog
from app.ui.dialogs.payment_dialog import PaymentDialog
from app.ui.dialogs.quantity_amount_dialog import QuantityAmountDialog
from app.ui.dialogs.sale_dialogs import HeldBillsDialog, MiscItemDialog, QuickFixDialog, StockShortDialog
from app.ui.errors import error_text
from app.ui.i18n.manager import I18n
from app.ui.pages.base import Page


class SalePage(Page):
    """The billing screen. Everything the cashier does lives here and is reachable from the keyboard:
    scan or type in the box, Enter adds the item; F12 pays."""

    title_key = "sale.title"

    def __init__(self, i18n: I18n, services: Services, user: User, parent=None) -> None:
        super().__init__(i18n, parent)
        self.services = services
        self.user = user
        self.cart = Cart()
        self._title.hide()

        self._code = QLineEdit()
        self._code.setObjectName("SaleCode")
        self._code.returnPressed.connect(self._on_code)
        self.layout_.addWidget(self._code)

        self._table = self.make_table(6)
        self._table.itemSelectionChanged.connect(lambda: None)
        self._table.doubleClicked.connect(lambda _i: self._edit_quantity())
        self._table.itemActivated.connect(lambda _i: self._edit_quantity())
        self._table.setColumnWidth(1, 320)
        self.layout_.addWidget(self._table, 1)
        self.last_order = None
        for key, handler in (("Del", self._remove_selected), ("+", lambda: self._bump(1)), ("-", lambda: self._bump(-1))):
            shortcut = QShortcut(QKeySequence(key), self._table, activated=handler)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)

        bottom = QHBoxLayout()
        grid = QGridLayout()
        self._buttons: dict[str, QPushButton] = {}
        layout_spec = (("edit", self._edit_quantity, 0, 0), ("discount", self._on_line_discount, 0, 1),
                       ("bill_discount", self._on_bill_discount, 0, 2), ("remove", self._remove_selected, 1, 0),
                       ("misc", self._on_misc, 1, 1), ("new", self._new_bill, 1, 2),
                       ("hold", self._hold, 2, 0), ("resume", self._resume, 2, 1))
        for key, handler, row, col in layout_spec:
            button = QPushButton()
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # focus stays in the scan box
            button.clicked.connect(handler)
            self._buttons[key] = button
            grid.addWidget(button, row, col)
        bottom.addLayout(grid, 1)

        totals = QVBoxLayout()
        self._subtotal, self._discount, self._rounding_label = QLabel(), QLabel(), QLabel()
        for label in (self._subtotal, self._discount, self._rounding_label):
            label.setObjectName("SaleNote")
            totals.addWidget(label)
        self._grand = QLabel()
        self._grand.setObjectName("GrandTotal")
        self._grand.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        totals.addWidget(self._grand)
        self._change = QLabel()
        self._change.setObjectName("ChangeLabel")
        self._change.setAlignment(Qt.AlignmentFlag.AlignRight)
        totals.addWidget(self._change)
        self._checkout_button = QPushButton()
        self._checkout_button.setObjectName("CheckoutButton")
        self._checkout_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._checkout_button.clicked.connect(self._checkout)
        totals.addWidget(self._checkout_button)
        bottom.addLayout(totals, 1)
        self.layout_.addLayout(bottom)
        self.layout_.addWidget(self.note)
        self.retranslate()

    # ------------------------------------------------------------------ text and display
    def retranslate(self) -> None:
        super().retranslate()
        tr = self.i18n.tr
        self._code.setPlaceholderText(tr("sale.code_placeholder"))
        for key, text in (("edit", "sale.btn.edit"), ("discount", "sale.btn.discount"), ("bill_discount", "sale.btn.bill_discount"),
                          ("remove", "sale.btn.remove"), ("misc", "sale.btn.misc"), ("new", "sale.btn.new"),
                          ("hold", "sale.btn.hold"), ("resume", "sale.btn.resume")):
            self._buttons[key].setText(tr(text))
        self._checkout_button.setText(tr("sale.btn.checkout"))
        self._table.setHorizontalHeaderLabels([tr("sale.col.no"), tr("purchase.col.item"), tr("purchase.col.qty"),
                                               tr("sale.col.price"), tr("sale.col.discount"), tr("sale.col.total")])
        self._refresh()

    def _rounding(self) -> str:
        return self.services.sales_settings.rounding()

    def _refresh(self, select: int | None = None) -> None:
        tr = self.i18n.tr
        if self.cart.prune_invalid_discounts():
            self.say(tr("sale.discount_removed"), error=True)
        totals = self.cart.totals(self._rounding())
        self._table.setRowCount(len(self.cart.lines))
        for row, (line, amounts) in enumerate(zip(self.cart.lines, totals.lines)):
            if line.discount is None:
                discount_text = "-"
            elif line.discount.percent is not None:
                discount_text = f"{line.discount.percent.normalize():f}%  ({amounts.discount.format()})"
            else:
                discount_text = amounts.discount.format()
            qty_text = f"{line.qty.format()} {tr('unit.' + line.unit)}"
            if line.mode == "amount":
                qty_text += "  *"
            values = [str(row + 1), line.display_name(self.i18n.lang), qty_text, line.unit_price.format(),
                      discount_text, (amounts.gross - amounts.discount).format()]
            for col, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if col in (2, 3, 4, 5):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                self._table.setItem(row, col, cell)
        if select is not None and 0 <= select < len(self.cart.lines):
            self._table.selectRow(select)
            self._table.scrollToItem(self._table.item(select, 0))
        self._subtotal.setText(f"{tr('sale.subtotal')}: {totals.subtotal.format()}   ({tr('sale.lines', count=len(self.cart.lines))})")
        self._discount.setText(f"{tr('sale.discount')}: -{totals.total_discount.format()}" if totals.total_discount.paisa else "")
        self._rounding_label.setText(f"{tr('sale.rounding')}: {totals.rounding.format()}" if totals.rounding.paisa else "")
        self._grand.setText(f"{tr('sale.total')}  {totals.payable.format()}")
        if not self.cart.is_empty:
            self._change.setText("")
        self._code.setFocus()

    def _selected_index(self) -> int | None:
        row = self._table.currentRow()
        return row if 0 <= row < len(self.cart.lines) else None

    def _need_line(self) -> int | None:
        index = self._selected_index()
        if index is None:
            self.say(self.i18n.tr("sale.select_line"), error=True)
        return index

    # ------------------------------------------------------------------ ribbon actions
    def handle_action(self, action_id: str) -> None:
        {
            "new_bill": self._new_bill, "hold_bill": self._hold, "resume_bill": self._resume,
            "find_item": self._find_item, "discount": self._line_discount, "bill_discount": self._bill_discount,
            "misc_item": self._misc, "checkout": self._checkout,
        }.get(action_id, lambda: None)()
        self._code.setFocus()

    # ------------------------------------------------------------------ adding items
    def _on_code(self) -> None:
        text = self._code.text().strip()
        self._code.clear()
        if not text:
            if not self.cart.is_empty:
                self._checkout()      # Enter on an empty box with items in the cart pays, like a till
            return
        exact = self.services.items.find_by_code(text)       # a code that really exists always wins
        qty, query = (None, text) if exact else split_quantity(text)
        self._add_by_query(qty, query)

    def _add_by_query(self, qty: Quantity | None, query: str) -> None:
        item = self.services.items.find_by_code(query)
        if item is None:
            matches = self.services.items.search(query, limit=50)
            if len(matches) == 1:
                item = matches[0]
            elif matches:
                picker = ItemPickerDialog(self.i18n, self.services, self, initial_text=query)
                if picker.exec():
                    item = picker.chosen
            else:
                self.say(self.i18n.tr("sale.not_found", text=query), error=True)
                return
        if item is not None:
            self._add_item(item, qty)

    def _find_item(self) -> None:
        picker = ItemPickerDialog(self.i18n, self.services, self)
        if picker.exec() and picker.chosen is not None:
            self._add_item(picker.chosen, None)

    def _add_item(self, item: Item, qty: Quantity | None) -> None:
        tr = self.i18n.tr
        fresh = self.services.items.get(item.id)
        if fresh is None or not fresh.is_active:
            self.say(tr("sale.inactive", name=item.display_name(self.i18n.lang)), error=True)
            return
        item = fresh
        mode, amount = "qty", None
        if qty is None:
            if item.allow_fraction:      # kg / litre items: ask how much (weighed quantity or an amount of money)
                dialog = QuantityAmountDialog(self.i18n, item.display_name(self.i18n.lang), item.unit, item.sale,
                                              allow_fraction=True, allow_amount=True, stock=item.stock, parent=self)
                if not dialog.exec():
                    return
                qty, mode, amount = dialog.qty, dialog.mode, dialog.amount
            else:
                qty = Quantity(1000)
        elif not item.allow_fraction and not qty.is_whole:
            self.say(tr("error.fraction_not_allowed"), error=True)
            return
        if not self._ensure_stock(item, self.cart.item_qty(item.id) + qty):
            return
        index = self.cart.add_item(item, qty, mode, amount)
        self._refresh(select=index)
        self.say(tr("sale.added", name=item.display_name(self.i18n.lang)))

    def _ensure_stock(self, item: Item, needed: Quantity) -> bool:
        """The shop never sells what the system says it does not have. If the shelf really has it, the count is fixed here."""
        tr = self.i18n.tr
        fresh = self.services.items.get(item.id) or item
        if needed <= fresh.stock:
            return True
        name = fresh.display_name(self.i18n.lang)
        short = StockShortDialog(self.i18n, name, fresh.stock.format(), needed.format(), self)
        if not short.exec() or not short.fix_requested:
            return False
        if not self.guard("stock.quickfix", tr("short.fix")):
            return False

        def submit(counted: Quantity, note: str | None) -> str | None:
            try:
                self.services.stock.quick_fix(self.user, fresh.id, counted, note)
            except (ValueError, PermissionError) as exc:
                return error_text(self.i18n, exc)
            return None

        if not QuickFixDialog(self.i18n, name, fresh.unit, fresh.stock, submit, self).exec():
            return False
        self.say(tr("fix.done"))
        return needed <= (self.services.items.get(item.id) or item).stock

    # ------------------------------------------------------------------ changing lines
    def _edit_quantity(self) -> None:
        index = self._need_line()
        if index is None:
            return
        line = self.cart.lines[index]
        item = None
        if not line.is_misc:
            item = self.services.items.get(line.item_id)
            if item is None or not item.is_active:
                self.say(self.i18n.tr("sale.inactive", name=line.display_name(self.i18n.lang)), error=True)
                return
        fraction = bool(item and item.allow_fraction)
        dialog = QuantityAmountDialog(self.i18n, line.display_name(self.i18n.lang), line.unit, line.unit_price,
                                      allow_fraction=fraction, allow_amount=fraction, stock=item.stock if item else None,
                                      initial_qty=line.qty, initial_mode=line.mode, initial_amount=line.amount, parent=self)
        if not dialog.exec():
            return
        if item is not None and not self._ensure_stock(item, self.cart.item_qty(item.id) - line.qty + dialog.qty):
            return
        self.cart.set_quantity(index, dialog.qty, dialog.mode, dialog.amount)
        self._refresh(select=index)

    def _remove_selected(self) -> None:
        index = self._need_line()
        if index is not None:
            self.cart.remove(index)
            self._refresh(select=min(index, len(self.cart.lines) - 1))

    def _bump(self, delta: int) -> None:
        """+ and - on a selected whole-number line."""
        index = self._selected_index()
        if index is None:
            return
        line = self.cart.lines[index]
        item = None if line.is_misc else self.services.items.get(line.item_id)
        if (item is not None and item.allow_fraction) or line.mode == "amount":
            return
        new_qty = Quantity(line.qty.milli + delta * 1000)
        if new_qty.milli <= 0:
            return
        if item is not None and not self._ensure_stock(item, self.cart.item_qty(item.id) + Quantity(delta * 1000)):
            return
        self.cart.set_quantity(index, new_qty)
        self._refresh(select=index)

    # ------------------------------------------------------------------ discounts and misc items
    def _on_line_discount(self) -> None:
        if self.guard("sales.discount", self.i18n.tr("sale.btn.discount")):
            self._line_discount()

    def _on_bill_discount(self) -> None:
        if self.guard("sales.discount", self.i18n.tr("sale.btn.bill_discount")):
            self._bill_discount()

    def _line_discount(self) -> None:
        index = self._need_line()
        if index is None:
            return
        line = self.cart.lines[index]
        dialog = DiscountDialog(self.i18n, self.i18n.tr("sale.btn.discount"), line.gross, line.discount, self)
        if dialog.exec():
            self._apply_discount(lambda d: self.cart.set_line_discount(index, d), lambda: line.discount, dialog.discount)

    def _bill_discount(self) -> None:
        if self.cart.is_empty:
            self.say(self.i18n.tr("sale.empty"), error=True)
            return
        totals = self.cart.totals(self._rounding())
        base = totals.subtotal - totals.item_discount
        dialog = DiscountDialog(self.i18n, self.i18n.tr("sale.btn.bill_discount"), base, self.cart.bill_discount, self)
        if dialog.exec():
            def setter(d):
                self.cart.bill_discount = d
            self._apply_discount(setter, lambda: self.cart.bill_discount, dialog.discount)

    def _apply_discount(self, setter, getter, new: Discount | None) -> None:
        """Try the discount; undo it if it breaks the bill or goes over the limit without permission."""
        previous = getter()
        setter(new)
        try:
            totals = self.cart.totals(self._rounding())
        except ValidationError as exc:
            setter(previous)
            self.say(error_text(self.i18n, exc), error=True)
            return
        limit = self.services.sales_settings.discount_limit_percent()
        if totals.discount_percent > limit and not self.guard(
                "sales.discount.unlimited", self.i18n.tr("sale.discount_over", limit=f"{limit.normalize():f}")):
            setter(previous)
            return
        self._refresh()

    def _on_misc(self) -> None:
        if self.guard("sales.misc", self.i18n.tr("sale.btn.misc")):
            self._misc()

    def _misc(self) -> None:
        dialog = MiscItemDialog(self.i18n, self)
        if dialog.exec():
            index = self.cart.add_misc(dialog.name, dialog.price, dialog.qty)
            self._refresh(select=index)

    # ------------------------------------------------------------------ bills: new, hold, resume
    def _new_bill(self) -> None:
        if not self.cart.is_empty:
            if not confirm(self.i18n, self, self.i18n.tr("sale.btn.new"), self.i18n.tr("sale.new_confirm")):
                return
            self.cart.clear()
            self._change.setText("")
            self._refresh()
        self._code.setFocus()

    def _hold_label(self) -> str:
        first = self.cart.lines[0].display_name(self.i18n.lang) if self.cart.lines else ""
        return f"{datetime.now().strftime('%H:%M')}  {first}".strip()

    def _hold(self) -> None:
        if self.cart.is_empty:
            self.say(self.i18n.tr("sale.empty"), error=True)
            return
        self.services.held.hold(self.user, self.cart, self._hold_label())
        self.cart = Cart()
        self._change.setText("")
        self._refresh()
        self.say(self.i18n.tr("sale.held"))

    def auto_hold(self) -> None:
        """Called when the user signs out or closes the app with items still in the bill: park them, lose nothing."""
        if not self.cart.is_empty:
            try:
                self.services.held.hold(self.user, self.cart, "auto " + self._hold_label())
            except (ValueError, ValidationError):
                pass

    def _resume(self) -> None:
        dialog = HeldBillsDialog(self.i18n, self.services, self.user, self)
        if not dialog.exec() or dialog.chosen_id is None:
            return
        if not self.cart.is_empty:
            self._hold()     # park the bill in progress first
        cart, dropped = self.services.held.resume(self.user, dialog.chosen_id)
        self.cart = cart
        self._change.setText("")
        self._refresh(select=0 if cart.lines else None)
        tr = self.i18n.tr
        if dropped:
            self.say(tr("sale.resumed_dropped", names=", ".join(dropped)), error=True)
        else:
            self.say(tr("sale.resumed"))

    # ------------------------------------------------------------------ checkout
    def _reprice(self) -> bool:
        """Prices may have changed since an item was added (or while a bill was held). Bring the cart up to date."""
        changed = False
        for line in list(self.cart.lines):
            if line.is_misc:
                continue
            item = self.services.items.get(line.item_id)
            if item is None or not item.is_active:
                self.cart.lines.remove(line)
                changed = True
            elif item.sale != line.unit_price:
                line.unit_price = item.sale
                if line.mode == "amount" and line.amount is not None and item.sale.paisa > 0:
                    line.qty = Quantity.for_amount(line.amount, item.sale)
                changed = True
        return changed

    def _checkout(self) -> None:
        tr = self.i18n.tr
        if self.cart.is_empty:
            self.say(tr("sale.empty"), error=True)
            return
        if self._reprice():
            self._refresh()
            self.say(tr("sale.repriced"), error=True)
            return    # the cashier sees the new total before taking money
        totals = self.cart.totals(self._rounding())
        payments, change = [], Money(0)
        if totals.payable.paisa > 0:
            dialog = PaymentDialog(self.i18n, totals.payable, self)
            if not dialog.exec():
                return
            payments, change = dialog.payments, dialog.change
        lines = [
            SaleLineInput(qty=l.qty, misc_name=l.name_en, misc_price=l.unit_price, discount=l.discount) if l.is_misc
            else SaleLineInput(qty=l.qty, item_id=l.item_id, mode=l.mode, amount=l.amount, discount=l.discount)
            for l in self.cart.lines
        ]
        try:
            order = self.services.sales.checkout(self.user, CheckoutInput(lines, payments, self.cart.bill_discount))
        except ValidationError as exc:
            if exc.code == "error.sale_stock_short":
                item = self.services.items.get(exc.params["item_id"])
                if item is not None:
                    self._ensure_stock(item, self.cart.item_qty(item.id))
            self.say(error_text(self.i18n, exc), error=True)
            return
        self.cart = Cart()
        self._refresh()
        self._change.setText(tr("sale.change", change=change.format()) if change.paisa > 0 else "")
        self.say(tr("sale.saved", bill=order.bill_no, total=order.payable.format()))
        self.last_order = order     # Phase 5 prints this
