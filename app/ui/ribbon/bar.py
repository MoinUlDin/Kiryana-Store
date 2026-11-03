from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QTabBar, QToolButton, QVBoxLayout, QWidget

from app.ui.glyphs import glyph_icon
from app.ui.i18n.manager import I18n
from app.ui.ribbon.quick_access import QuickAccessBar
from app.ui.ribbon.tab import RibbonTab


class RibbonBar(QWidget):
    """Quick-access strip, File button + tab strip, and the ribbon body.
    Double-click a tab (or press Ctrl+F1) to collapse or pin the body."""

    file_requested = pyqtSignal()

    def __init__(self, i18n: I18n, parent=None) -> None:
        super().__init__(parent)
        self._i18n = i18n
        self._collapsed = False
        self._temp_open = False
        self._tabs: list[tuple[str, RibbonTab]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.quick_access = QuickAccessBar(self)
        root.addWidget(self.quick_access)

        header = QWidget(self)
        header.setObjectName("RibbonHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        self.file_button = QToolButton(header)
        self.file_button.setObjectName("FileButton")
        self.file_button.clicked.connect(self.file_requested)
        header_layout.addWidget(self.file_button)
        self.tab_bar = QTabBar(header)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.tabBarClicked.connect(self._on_tab_clicked)
        self.tab_bar.installEventFilter(self)
        header_layout.addWidget(self.tab_bar)
        header_layout.addStretch(1)
        self.collapse_button = QToolButton(header)  # visible alternative to double-click / Ctrl+F1
        self.collapse_button.setObjectName("RibbonCollapse")
        self.collapse_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.collapse_button.clicked.connect(self.toggle_collapsed)
        header_layout.addWidget(self.collapse_button)
        root.addWidget(header)

        self.body = QStackedWidget(self)
        self.body.setObjectName("RibbonBody")
        root.addWidget(self.body)

    # ---- building -----------------------------------------------------
    def add_tab(self, tab: RibbonTab, title_key: str) -> None:
        self._tabs.append((title_key, tab))
        self.body.addWidget(tab)
        self.tab_bar.addTab("")
        for group in tab.groups:
            group.activated.connect(self._after_action)

    def retranslate(self) -> None:
        tr = self._i18n.tr
        self.file_button.setText(tr("file.button"))
        self.quick_access.set_title(tr("app.title"))
        self._update_collapse_button()
        for index, (title_key, tab) in enumerate(self._tabs):
            self.tab_bar.setTabText(index, tr(title_key))
            tab.retranslate(tr)
        self.relayout()

    def refresh_visibility(self) -> None:
        """Call after permissions or translations change: hides empty groups and tabs."""
        first_visible = None
        for index, (_key, tab) in enumerate(self._tabs):
            shown = tab.update_visibility()
            self.tab_bar.setTabVisible(index, shown)
            if shown and first_visible is None:
                first_visible = index
        current = self.tab_bar.currentIndex()
        if first_visible is not None and not self.tab_bar.isTabVisible(current):
            self.tab_bar.setCurrentIndex(first_visible)
        self.relayout()

    # ---- behaviour ----------------------------------------------------
    def relayout(self) -> None:
        tab = self.body.currentWidget()
        if isinstance(tab, RibbonTab):
            tab.relayout(self.width())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.relayout()

    def _on_tab_changed(self, index: int) -> None:
        if 0 <= index < self.body.count():
            self.body.setCurrentIndex(index)
            self.relayout()

    def _on_tab_clicked(self, index: int) -> None:
        if self._collapsed:
            show = not (self.body.isVisible() and index == self.tab_bar.currentIndex())
            self.body.setVisible(show)
            self._temp_open = show
            self.relayout()

    def _after_action(self) -> None:
        if self._collapsed and self._temp_open:
            self.body.setVisible(False)
            self._temp_open = False

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self._temp_open = False
        self.body.setVisible(not collapsed)
        self._update_collapse_button()
        self.relayout()

    def _update_collapse_button(self) -> None:
        glyph = "\uE70D" if not self._collapsed else "\uE70E"  # chevron down = collapse, up = pin
        self.collapse_button.setIcon(glyph_icon(glyph, 16, "#FFFFFF"))
        self.collapse_button.setToolTip(self._i18n.tr("ribbon.expand" if self._collapsed else "ribbon.collapse"))

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.tab_bar and event.type() == QEvent.Type.MouseButtonDblClick:
            self.toggle_collapsed()
            return True
        return super().eventFilter(obj, event)
