"""Tests for reading the Australian (AUSNUT) data. Only the small helpers; no Excel files needed."""
import ausnut
import usda


def test_measure_text_with_size_and_brand():
    text = ausnut.measure_text(1, ["slice", "thick", None, "Abbotts Village"], 0)
    assert text == "1 slice, thick (Abbotts Village)"


def test_measure_text_shows_volume():
    assert ausnut.measure_text(1, ["can", None, None, None], 375) == "1 can (375 ml)"


def test_density_becomes_a_cup():
    # Cooked rice at 0.8 g per ml weighs 200 g per 250 ml cup
    assert ausnut.density_portion(0.8, "cooked") == ("1 cup (250 ml), cooked", 200.0)


def test_australian_foods_come_first_in_search():
    assert usda.SEARCH_RANK["ausnut_food"] < min(v for k, v in usda.SEARCH_RANK.items() if k != "ausnut_food")


def test_new_nutrients_dont_count_as_vitamins_or_minerals():
    for key in ["caffeine", "alcohol", "free_sugars", "omega3_lc"]:
        assert key not in usda.VITAMINS_AND_MINERALS
