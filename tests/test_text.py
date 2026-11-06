from app.domain.quantity import Quantity
from app.domain.text import normalize_search
import pytest


def test_english_is_lowercased_and_trimmed():
    assert normalize_search("  Basmati   RICE ") == "basmati rice"
    assert normalize_search(None) == "" and normalize_search("") == ""


def test_urdu_letter_variants_match():
    # Arabic yeh/kaf typed on an Arabic keyboard must match the Urdu forms
    assert normalize_search("كتاب") == normalize_search("کتاب")
    assert normalize_search("چيني") == normalize_search("چینی")


def test_diacritics_and_digits_are_normalised():
    assert normalize_search("چینِی") == normalize_search("چینی")
    assert normalize_search("٥ کلو") == "5 کلو"
    assert normalize_search("۱۲") == "12"


def test_small_unit_quantities():
    assert Quantity.from_small_unit("250") == Quantity(250)       # 250 g of a kg item
    assert Quantity.from_small_unit(20).format() == "0.02"
    with pytest.raises(ValueError):
        Quantity.from_small_unit("0.5")
    with pytest.raises(TypeError):
        Quantity.from_small_unit(2.5)
