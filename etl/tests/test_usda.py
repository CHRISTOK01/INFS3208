"""Tests for the USDA cleaning rules. They use tiny made-up CSV files, not the real data."""
import csv

import pytest

import usda


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


# ---------------------------------------------------------------- unit conversion

def test_same_unit_is_unchanged():
    assert usda.convert(12.5, "MG", "mg", "iron") == 12.5


def test_grams_to_milligrams_and_micrograms():
    assert usda.convert(1.5, "G", "mg", "calcium") == 1500
    assert usda.convert(2, "MG", "ug", "selenium") == pytest.approx(2000)


def test_vitamin_d_iu_converts_exactly():
    assert usda.convert(400, "IU", "ug", "vitamin_d") == pytest.approx(10)   # 40 IU = 1 microgram


def test_vitamin_a_iu_is_left_unknown():
    assert usda.convert(1000, "IU", "ug", "vitamin_a") is None


# ---------------------------------------------------------------- sanity checks

def test_impossible_values_are_rejected():
    assert not usda.is_plausible("protein", "g", 150)       # more than 100 g in 100 g of food
    assert not usda.is_plausible("energy", "kcal", 1200)    # more than pure fat
    assert not usda.is_plausible("iron", "mg", -1)
    assert usda.is_plausible("sodium", "mg", 38_000)        # table salt really is ~38 g per 100 g


# ---------------------------------------------------------------- names and portions

@pytest.mark.parametrize("name, expected", [
    ("Spinach, raw", "raw"),
    ("Chicken, broilers or fryers, breast, meat only, cooked, roasted", "cooked"),
    ("Egg, whole, fried", "cooked"),
    ("Milk, whole", None),
])
def test_prep_state(name, expected):
    assert usda.prep_state(name) == expected


def test_portion_text_uses_description_when_given():
    assert usda.portion_text("", "undetermined", "10205", "1 cup") == "1 cup"


def test_portion_text_builds_from_parts():
    assert usda.portion_text("2.0", "tablespoon", "", "") == "2 tablespoon"
    assert usda.portion_text("1", "undetermined", "cup, chopped", "") == "1 cup, chopped"


def test_tidy_name_only_changes_all_capitals():
    assert usda.tidy_name("CHEDDAR CHEESE") == "Cheddar Cheese"
    assert usda.tidy_name("Apples, raw") == "Apples, raw"


# ---------------------------------------------------------------- reading nutrients

def test_reads_nutrients_by_id_with_fallback_and_unknowns(tmp_path):
    write_csv(tmp_path / "nutrient.csv", ["id", "name", "unit_name", "nutrient_nbr", "rank"], [
        ["1008", "Energy", "KCAL", "208", "1"],
        ["2048", "Energy (Atwater Specific Factors)", "KCAL", "958", "2"],
        ["1090", "Magnesium, Mg", "MG", "304", "3"],
    ])
    write_csv(tmp_path / "food_nutrient.csv", ["id", "fdc_id", "nutrient_id", "amount"], [
        ["1", "100", "2048", "52"],     # food 100 only has Atwater energy -> used as the fallback
        ["2", "200", "1008", "40"],     # food 200 has both -> plain "Energy" wins
        ["3", "200", "2048", "41"],
        ["4", "200", "1090", "12"],
    ])
    values = usda.read_nutrients(tmp_path, {100, 200})
    assert values[100] == {"energy": 52}               # no magnesium value -> simply not there (unknown)
    assert values[200] == {"energy": 40, "magnesium": 12}


def test_reads_fndds_style_nutrient_numbers(tmp_path):
    # FNDDS's food_nutrient.csv uses the nutrient NUMBER (304), not the ID (1090)
    write_csv(tmp_path / "nutrient.csv", ["id", "name", "unit_name", "nutrient_nbr", "rank"], [
        ["1090", "Magnesium, Mg", "MG", "304", "1"],
    ])
    write_csv(tmp_path / "food_nutrient.csv", ["id", "fdc_id", "nutrient_id", "amount"], [
        ["1", "300", "304", "25"],
    ])
    assert usda.read_nutrients(tmp_path, {300}) == {300: {"magnesium": 25}}
