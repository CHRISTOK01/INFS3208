"""Tests for the small food rules (portions, labels, search words, barcodes). No database needed."""
import re

import pytest
from pydantic import ValidationError

from app import foods
from app.routes_meals import ItemIn


def test_portion_to_grams():
    assert foods.to_grams(30, 1) == 30        # 1 cup of spinach
    assert foods.to_grams(30, 2) == 60        # 2 cups
    assert foods.to_grams(118, 0.5) == 59     # half a medium banana
    assert foods.to_grams(30.5, 3) == 91.5


def test_confidence_labels():
    assert foods.confidence_label("branded_food", False) == "label data only"
    assert foods.confidence_label("branded_food", True) == "label data only"
    assert foods.confidence_label("foundation_food", True) == "complete micronutrient data"
    assert foods.confidence_label("ausnut_food", True) == "complete micronutrient data"
    assert foods.confidence_label("sr_legacy_food", False) == "partial micronutrient data"


def test_search_words():
    assert foods.search_words("Chicken breast") == ["chicken", "breast"]
    assert foods.search_words("milk, whole") == ["milk", "whole"]
    assert foods.search_words("a b  egg egg") == ["egg"]                 # single letters and repeats dropped
    assert foods.search_words("one two three four five six") == ["one", "two", "three", "four", "five"]


def test_plural_endings_are_cut_so_both_forms_match():
    assert foods.stem("bananas") == "banana"
    assert foods.stem("strawberries") == "strawberr"      # in "strawberry" and "strawberries"
    assert foods.stem("tomatoes") == "tomato"
    assert foods.stem("peaches") == "peach"
    assert foods.stem("hummus") == "hummu"                # still in "hummus"
    assert foods.stem("glass") == "glass" and foods.stem("egg") == "egg"


def test_cooking_words_become_a_cooked_preference():
    search = foods.understand_search("rice white boiled", None)
    assert search.words == ["rice", "white"] and search.state == "cooked" and search.cooking_word == "boiled"
    assert search.all_words == ["rice", "white", "boiled"]


def test_raw_becomes_a_raw_preference_and_state_setting_wins():
    assert foods.understand_search("bananas raw", None).state == "raw"
    assert foods.understand_search("chicken grilled", "raw").state == "raw"


def test_a_search_of_only_a_cooking_word_keeps_it():
    search = foods.understand_search("fried", None)
    assert search.words == ["fried"] and search.cooking_word is None


def test_main_entry_pattern():
    pattern = re.compile(foods.main_entry_pattern(["banana"]), re.I)
    assert pattern.search("Banana, cavendish, peeled, raw") and pattern.search("Bananas, raw")
    assert not pattern.search("Banana chip") and not pattern.search("Eggplant, raw")
    assert re.search(foods.main_entry_pattern(["peanut", "butter"]), "peanut butter, smooth")
    assert not re.search(foods.main_entry_pattern(["egg"]), "eggplant, raw")


def test_like_pattern_escapes_special_characters():
    assert foods.like_pattern("milk") == "%milk%"
    assert foods.like_pattern("100%") == "%100\\%%"
    assert foods.like_pattern("a_b") == "%a\\_b%"


def test_starts_with_pattern():
    assert foods.starts_with_pattern("milk") == "milk%"


def test_duplicate_names_are_dropped():
    rows = [{"fdc_id": 1, "name": "Bananas, raw"}, {"fdc_id": 2, "name": "bananas, RAW"}, {"fdc_id": 3, "name": "Milk"}]
    assert [r["fdc_id"] for r in foods.first_of_each_name(rows)] == [1, 3]


def test_barcodes_match_with_or_without_leading_zeros():
    assert foods.normalise_barcode("0000020048556") == "20048556"
    assert foods.normalise_barcode(" 20048556 ") == "20048556"


def test_item_needs_grams_or_a_portion():
    assert ItemIn(fdc_id=1, grams=100).grams == 100
    assert ItemIn(fdc_id=1, portion_id=5, quantity=2).portion_id == 5
    with pytest.raises(ValidationError):
        ItemIn(fdc_id=1)                                  # neither
    with pytest.raises(ValidationError):
        ItemIn(fdc_id=1, grams=100, portion_id=5)         # both
    with pytest.raises(ValidationError):
        ItemIn(fdc_id=1, grams=0)                         # grams must be more than 0
