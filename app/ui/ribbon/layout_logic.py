"""Responsive group-collapsing rules for the ribbon (pure Python, unit-tested)."""
from __future__ import annotations

from typing import Sequence

FULL, COMPACT, COLLAPSED = 0, 1, 2


def choose_modes(
    widths: Sequence[Sequence[int]],
    priorities: Sequence[int],
    available: int,
    gap: int = 0,
) -> list[int]:
    """Pick a display mode for every group so the row fits in `available` pixels.

    widths[i][mode] is group i's width in that mode. Groups with the highest
    priority number are shrunk first (rightmost first on ties); each group is
    taken all the way down to COLLAPSED before the next one is touched, like Word.
    If even everything collapsed does not fit, all groups end up COLLAPSED.
    """
    count = len(widths)
    modes = [FULL] * count

    def total() -> int:
        return sum(widths[i][modes[i]] for i in range(count)) + gap * max(count - 1, 0)

    while total() > available:
        candidates = [i for i in range(count) if modes[i] < COLLAPSED]
        if not candidates:
            break
        victim = max(candidates, key=lambda i: (priorities[i], i))
        modes[victim] += 1
    return modes
