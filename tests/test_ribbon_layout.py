from app.ui.ribbon.layout_logic import COLLAPSED, COMPACT, FULL, choose_modes

# Each group: widths for (FULL, COMPACT, COLLAPSED)
W = [(300, 200, 60), (250, 160, 60), (100, 80, 60)]


def test_everything_fits():
    assert choose_modes(W, [1, 2, 3], available=1000) == [FULL, FULL, FULL]


def test_least_important_group_shrinks_first_and_fully():
    # FULL total is 650. Group 2 (priority 3) goes COMPACT (630), then COLLAPSED (610).
    # Still over 600, so only then does group 1 (priority 2) start shrinking.
    assert choose_modes(W, [1, 2, 3], available=600) == [FULL, COMPACT, COLLAPSED]
    # With a bit more room, only the least important group had to shrink.
    assert choose_modes(W, [1, 2, 3], available=620) == [FULL, FULL, COLLAPSED]


def test_exact_fit_is_accepted():
    assert choose_modes(W, [1, 2, 3], available=650) == [FULL, FULL, FULL]


def test_gap_counts_toward_width():
    assert choose_modes(W, [1, 2, 3], available=650, gap=10) != [FULL, FULL, FULL]


def test_ties_shrink_rightmost_first():
    modes = choose_modes([(100, 50, 20), (100, 50, 20)], [1, 1], available=190)
    assert modes[1] > modes[0]


def test_too_narrow_collapses_everything():
    assert choose_modes(W, [1, 2, 3], available=10) == [COLLAPSED] * 3


def test_empty_ribbon():
    assert choose_modes([], [], available=100) == []
