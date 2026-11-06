from app.domain.entry import split_quantity
from app.domain.quantity import Quantity as Q


def test_quantity_prefix():
    assert split_quantity("2.5*SUG") == (Q(2500), "SUG")
    assert split_quantity("  3 \u00d7 Lifebuoy small ") == (Q(3000), "Lifebuoy small")
    assert split_quantity("\u0662*\u0686\u06cc\u0646\u06cc") == (Q(2000), "\u0686\u06cc\u0646\u06cc")      # Urdu digit and Urdu name
    assert split_quantity("0.250*SUG") == (Q(250), "SUG")


def test_no_prefix_means_the_whole_text_is_the_query():
    for text in ("SUG", "8901030865278", "2x4", "5*", "*SUG", "0*SUG", "1,5*SUG", "-2*SUG", "1.2.3*X"):
        qty, query = split_quantity(text)
        assert qty is None and query == text.strip(), text
