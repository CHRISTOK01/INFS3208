"""Tests for finding gaps and excesses. No database needed."""
from app.gaps import analyse, check_nutrient, today_vs_targets

MAGNESIUM = {"nutrient_key": "magnesium", "target_amount": 310, "upper_limit": None, "unit": "mg"}
IRON = {"nutrient_key": "iron", "target_amount": 18, "upper_limit": 45, "unit": "mg"}
SODIUM = {"nutrient_key": "sodium", "target_amount": None, "upper_limit": None, "unit": "mg"}
IODINE = {"nutrient_key": "iodine", "target_amount": 150, "upper_limit": 1100, "unit": "ug"}
ENERGY = {"nutrient_key": "energy", "target_amount": 2000, "upper_limit": None, "unit": "kcal"}


def day(**nutrients):
    """A day as nutrient-calc sends it. Pass amount, or (amount, coverage_pct)."""
    values = {}
    for key, value in nutrients.items():
        amount, coverage = value if isinstance(value, tuple) else (value, 100.0)
        values[key] = {"amount": amount, "is_complete": coverage == 100, "coverage_pct": coverage}
    return {"date": "2026-03-01", "nutrients": values}


def test_well_under_target_is_a_gap():
    result = check_nutrient(MAGNESIUM, [day(magnesium=150), day(magnesium=160), day(magnesium=155)])
    assert result["status"] == "gap"
    assert result["avg_intake"] == 155 and result["pct_of_target"] == 50
    assert result["days_met"] == 0


def test_a_little_under_target_is_ok():
    result = check_nutrient(MAGNESIUM, [day(magnesium=250), day(magnesium=300), day(magnesium=320)])
    assert result["status"] == "ok"        # average 290 mg is 93.5% of 310
    assert result["days_met"] == 1          # only the 320 mg day met the target


def test_above_the_upper_limit_is_an_excess():
    result = check_nutrient(IRON, [day(iron=50), day(iron=60), day(iron=55)])
    assert result["status"] == "excess"


def test_low_coverage_days_that_look_low_are_unknown_not_a_gap():
    # Two good days and two days where we only know magnesium for half the food. The half-known
    # days look low, but the missing foods might have had plenty, so we can't call it a gap.
    days = [day(magnesium=300), day(magnesium=320), day(magnesium=(40, 50.0)), day(magnesium=(30, 45.0))]
    result = check_nutrient(MAGNESIUM, days)
    assert result["is_minimum"] and result["days_with_data"] == 4
    assert result["status"] == "unknown"


def test_low_coverage_days_that_already_reach_the_target_are_ok():
    # We only know vitamin C for some of the food, but even that is over the target,
    # and the foods we're missing can only add to it.
    vitamin_c = {"nutrient_key": "vitamin_c", "target_amount": 45, "upper_limit": None, "unit": "mg"}
    days = [day(vitamin_c=(60, 70.0)), day(vitamin_c=(50, 60.0)), day(vitamin_c=(80, 75.0))]
    result = check_nutrient(vitamin_c, days)
    assert result["is_minimum"] and result["avg_intake"] == 63.33
    assert result["status"] == "ok"


def test_unknown_amounts_are_never_counted_as_zero():
    days = [day(magnesium=300), day(magnesium=310), day(magnesium=320), day(magnesium=(None, 0.0))]
    result = check_nutrient(MAGNESIUM, days)
    assert result["days_with_data"] == 3 and result["avg_intake"] == 310
    assert result["status"] == "ok"


def test_no_reference_value_means_unknown_not_ok():
    result = check_nutrient(SODIUM, [day(sodium=2000), day(sodium=2100), day(sodium=1900)])
    assert result["status"] == "unknown" and result["avg_intake"] == 2000


def test_sodium_is_checked_against_its_upper_limit():
    sodium = {**SODIUM, "upper_limit": 2000}
    assert check_nutrient(sodium, [day(sodium=1500), day(sodium=1800), day(sodium=1700)])["status"] == "ok"
    assert check_nutrient(sodium, [day(sodium=2500), day(sodium=2800), day(sodium=2600)])["status"] == "excess"


def test_report_skips_macros_and_lists_the_biggest_gaps_first():
    days = [day(magnesium=100, iron=10, iodine=10, energy=1500)] * 3
    report = analyse([MAGNESIUM, IRON, IODINE, ENERGY], days, 7)
    assert [n["nutrient_key"] for n in report["nutrients"]] == ["magnesium", "iron", "iodine"]
    assert report["top_gaps"] == ["iodine", "magnesium", "iron"]      # 7% of target, then 32%, then 56%
    assert report["days_logged"] == 3


def test_any_alcohol_is_too_much_when_the_limit_is_zero():
    alcohol = {"nutrient_key": "alcohol", "target_amount": None, "upper_limit": 0, "unit": "g"}
    result = check_nutrient(alcohol, [day(alcohol=0), day(alcohol=0), day(alcohol=10)])
    assert result["status"] == "excess" and result["reason"] == "the advice is to have none"


def test_every_logged_day_counts():
    full = day(energy=1800, magnesium=300)
    breakfast_only = day(energy=400, magnesium=40)
    report = analyse([ENERGY, MAGNESIUM], [full, full, full, breakfast_only], 7)
    assert report["days_logged"] == 4
    assert report["nutrients"][0]["days_with_data"] == 4
    assert report["nutrients"][0]["avg_intake"] == 235


def test_today_shows_what_is_left_of_the_budget():
    result = today_vs_targets([ENERGY, MAGNESIUM], day(energy=1500, magnesium=200))
    assert result["remaining"] == {"energy": 500}
    rows = {r["nutrient_key"]: r for r in result["nutrients"]}
    assert rows["magnesium"]["pct_of_target"] == 64.5


def test_today_with_nothing_logged():
    result = today_vs_targets([ENERGY], None)
    assert result["remaining"] == {"energy": 2000}
    assert result["nutrients"][0]["amount"] is None
