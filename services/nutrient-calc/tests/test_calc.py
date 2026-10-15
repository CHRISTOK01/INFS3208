"""Tests for the nutrient maths. No database needed."""
import pytest

from app.calc import scale, sum_nutrients

ENERGY, IRON, VIT_D = 1, 11, 32

# Two made-up foods (amounts per 100 g). Food 200 has no vitamin D value, so we don't know it.
FOODS = {
    100: {ENERGY: 200.0, IRON: 2.0, VIT_D: 1.5},
    200: {ENERGY: 50.0, IRON: 1.0},
}


def test_scale_is_linear_in_grams():
    assert scale(200.0, 100) == 200.0
    assert scale(200.0, 50) == 100.0
    assert scale(2.5, 250) == pytest.approx(6.25)


def test_sums_known_values_across_items():
    totals = sum_nutrients([(100, 150), (200, 200)], FOODS, [ENERGY, IRON])
    assert totals[ENERGY] == {"amount": 400.0, "is_complete": True, "coverage_pct": 100.0}   # 300 + 100
    assert totals[IRON] == {"amount": 5.0, "is_complete": True, "coverage_pct": 100.0}       # 3 + 2


def test_unknown_value_is_not_counted_as_zero():
    totals = sum_nutrients([(100, 100), (200, 100)], FOODS, [VIT_D])
    # Only food 100 has vitamin D, so we get part of the total, marked as incomplete.
    # We know it for 100 g out of 200 g eaten, so coverage is 50%.
    assert totals[VIT_D] == {"amount": 1.5, "is_complete": False, "coverage_pct": 50.0}


def test_all_unknown_gives_none_not_zero():
    totals = sum_nutrients([(200, 100)], FOODS, [VIT_D])
    assert totals[VIT_D] == {"amount": None, "is_complete": False, "coverage_pct": 0.0}


def test_food_with_no_data_at_all_is_unknown():
    totals = sum_nutrients([(999, 100)], FOODS, [ENERGY])
    assert totals[ENERGY] == {"amount": None, "is_complete": False, "coverage_pct": 0.0}


def test_empty_item_list_is_zero_and_complete():
    totals = sum_nutrients([], FOODS, [ENERGY, IRON])
    assert totals[ENERGY] == {"amount": 0.0, "is_complete": True, "coverage_pct": None}


def test_same_food_twice_adds_up():
    totals = sum_nutrients([(100, 50), (100, 50)], FOODS, [ENERGY])
    assert totals[ENERGY]["amount"] == 200.0


def test_coverage_is_by_weight_not_by_item_count():
    # 450 g of a food with vitamin D, plus a 50 g snack without it. Half the items are missing
    # vitamin D, but 90% of the food by weight has it, so the total is close to the truth.
    totals = sum_nutrients([(100, 450), (200, 50)], FOODS, [VIT_D])
    assert totals[VIT_D]["is_complete"] is False
    assert totals[VIT_D]["coverage_pct"] == 90.0
    assert totals[VIT_D]["amount"] == pytest.approx(6.75)
