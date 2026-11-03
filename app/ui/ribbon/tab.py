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
        self._separators: list[QFrame | None] = []
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
        sep = None
        if self.groups:
            sep = QFrame(self)
            sep.setObjectName("RibbonSep")
            self._layout.insertWidget(self._layout.count() - 1, sep)
        self._layout.insertWidget(self._layout.count() - 1, group)
        self.groups.append(group)
        self._separators.append(sep)

    def update_visibility(self) -> bool:
        """Hide groups whose buttons are all hidden (e.g. by permissions) and the separators
        around them. Returns True if anything on this tab is visible."""
        any_before = False
        for group, sep in zip(self.groups, self._separators):
            show = group.has_visible_actions()
            group.setVisible(show)
            if sep is not None:
                sep.setVisible(show and any_before)
            any_before = any_before or show
        return any_before

    def retranslate(self, tr) -> None:
        for group in self.groups:
            group.retranslate(tr)

    def relayout(self, available_width: int) -> None:
        """Choose a mode for each group so everything fits `available_width`."""
        shown = [g for g in self.groups if not g.isHidden()]
        if not shown:
            return
        usable = available_width - 2 * MARGIN
        modes = choose_modes([g.widths for g in shown], [g.priority for g in shown], usable, gap=GAP)
        for group, mode in zip(shown, modes):
            group.set_mode(mode)

    def minimumSizeHint(self) -> QSize:
        # Never force the window wider; groups collapse instead.
        return QSize(0, self.sizeHint().height())
