from __future__ import annotations

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLayout, QSizePolicy, QWidget

from app.ui.ribbon.group import RibbonGroup
from app.ui.ribbon.layout_logic import choose_modes

MARGIN = 4
GAP = 3  # separator + spacing between two groups


class RibbonTab(QWidget):
    def __init__(self, key: str, parent=None) -> None:
        super().__init__(parent)
        self.key = key
        self.groups: list[RibbonGroup] = []
        # ROOT CAUSE of the "ribbon never collapses" bug: a layout's default size constraint
        # turns the sum of its children's minimum widths into the widget's real minimum width,
        # so the window could never get narrower than the groups and the collapsing rules
        # never ran. The tab must be allowed to be narrower than its content.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._layout = QHBoxLayout(self)
        self._layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self._layout.setContentsMargins(MARGIN, 2, MARGIN, 2)
        self._layout.setSpacing(1)
        self._layout.addStretch(1)

    def add_group(self, group: RibbonGroup) -> None:
        if self.groups:
            sep = QFrame(self)
            sep.setObjectName("RibbonSep")
            self._layout.insertWidget(self._layout.count() - 1, sep)
        self._layout.insertWidget(self._layout.count() - 1, group)
        self.groups.append(group)

    def retranslate(self, tr) -> None:
        for group in self.groups:
            group.retranslate(tr)

    def relayout(self, available_width: int) -> None:
        """Choose a mode for each group so everything fits `available_width`."""
        if not self.groups:
            return
        usable = available_width - 2 * MARGIN
        modes = choose_modes(
            [g.widths for g in self.groups], [g.priority for g in self.groups], usable, gap=GAP
        )
        for group, mode in zip(self.groups, modes):
            group.set_mode(mode)

    def minimumSizeHint(self) -> QSize:
        # Never force the window wider; groups collapse instead.
        return QSize(0, self.sizeHint().height())
