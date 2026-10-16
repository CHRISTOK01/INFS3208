"""Tests for working out targets from a profile. No database needed. The expected numbers were
worked out by hand from the rules in app/targets.py (the working is in the comments)."""
from datetime import date, timedelta

import pytest

from app.routes import Profile
from app.targets import LIFESTYLES, activity_level, age_on, bmr, build_targets, pregnancy_week

ON = date(2026, 6, 1)


def ref(key, amount, unit="mg", sex="female", stage="none", upper=None, sdt=None, ages=((14, 18), (19, 30), (31, 50), (51, 70), (71, 120))):
    """Make reference_intakes rows (the same amount for every age band, to keep the tests short)."""
    return [{"nutrient_key": key, "sex": sex, "age_min": lo, "age_max": hi, "life_stage": stage,
             "intake_type": "RDI", "rni_or_ai": amount, "upper_limit": upper, "sdt": sdt, "unit": unit}
            for lo, hi in ages]


REFERENCES = (
    ref("protein", 0.84, "g/kg", sex="male") + ref("protein", 0.75, "g/kg")
    + ref("protein", 1.0, "g/kg", stage="pregnant") + ref("protein", 1.1, "g/kg", stage="breastfeeding")
    + ref("iron", 8, sex="male", upper=45) + ref("iron", 18, upper=45)
    + ref("iron", 27, stage="pregnant", upper=45) + ref("iron", 9, stage="breastfeeding", upper=45)
    + ref("zinc", 14, sex="male") + ref("zinc", 8) + ref("zinc", 11, stage="pregnant") + ref("zinc", 12, stage="breastfeeding")
    + ref("fibre", 30, "g", sex="male", sdt=38) + ref("fibre", 25, "g", sdt=28)
    + ref("fibre", 28, "g", stage="pregnant") + ref("fibre", 30, "g", stage="breastfeeding")
    + ref("sodium", None, sex="male", upper=2000) + ref("sodium", None, upper=2000)
    + ref("sodium", None, stage="pregnant", upper=2000) + ref("sodium", None, stage="breastfeeding", upper=2000)
    + ref("vitamin_k", 70, "ug", sex="male") + ref("vitamin_k", 60, "ug")
)

MAN = {"sex": "male", "date_of_birth": date(1996, 1, 1), "height_cm": 180, "weight_kg": 80,
       "lifestyle": "standing_walking", "exercise_sessions_per_week": 0, "goal": "maintain", "diet": "omnivore",
       "due_date": None, "pre_pregnancy_weight_kg": None, "breastfeeding": False}
WOMAN = {**MAN, "sex": "female", "date_of_birth": date(1996, 1, 1), "height_cm": 165, "weight_kg": 60,
         "lifestyle": "seated_some_walking"}


def targets_for(profile, on=ON):
    result = build_targets(profile, REFERENCES, on)
    return {t["nutrient_key"]: t for t in result["targets"]}, result


# ---------------------------------------------------------------- the person

def test_age_moves_on_at_the_birthday():
    assert age_on(date(2000, 6, 2), date(2026, 6, 1)) == 25
    assert age_on(date(2000, 6, 1), date(2026, 6, 1)) == 26


def test_pregnancy_week_from_the_due_date():
    assert pregnancy_week(ON + timedelta(weeks=20), ON) == 20      # 20 weeks to go = week 20 of 40
    assert pregnancy_week(ON - timedelta(days=1), ON) is None      # the due date has passed
    assert pregnancy_week(None, ON) is None


def test_bmr_mifflin_st_jeor():
    assert bmr("male", 80, 180, 30) == 1780          # 800 + 1125 - 150 + 5
    assert bmr("female", 60, 165, 30) == 1320.25     # 600 + 1031.25 - 150 - 161


def test_activity_level_adds_exercise_and_is_capped():
    assert activity_level({"lifestyle": "seated_some_walking", "exercise_sessions_per_week": 0}) == 1.65
    # 4.5 sessions add NHMRC's 0.3, so 3 sessions add 0.2
    assert activity_level({"lifestyle": "seated_some_walking", "exercise_sessions_per_week": 3}) == 1.85
    assert activity_level({"lifestyle": "heavy_work", "exercise_sessions_per_week": 14}) == 2.5


def test_the_form_offers_the_same_lifestyles_as_the_maths():
    assert set(Profile.model_fields["lifestyle"].annotation.__args__) == set(LIFESTYLES)


# ---------------------------------------------------------------- energy and macros

def test_energy_for_a_man_who_stands_at_work():
    rows, result = targets_for(MAN)
    assert result["situation"]["age"] == 30
    assert rows["energy"]["target_amount"] == 3290     # 1780 x 1.85 = 3293
    assert result["situation"]["energy_kj"] == 13770   # 3290 x 4.184


def test_macros_add_up_to_the_energy():
    rows, _ = targets_for(MAN)
    energy, protein, fat, carbs = (rows[k]["target_amount"] for k in ("energy", "protein", "fat", "carbs"))
    assert fat == 110                                  # 30% of 3290 / 9
    # Protein: the RDI is 0.84 x 80 = 67 g, but at least 15% of energy is 3290 x 0.15 / 4 = 123 g
    assert protein == 123
    assert abs(protein * 4 + fat * 9 + carbs * 4 - energy) <= 4


def test_losing_weight_takes_500_kcal_off_and_raises_protein():
    rows, _ = targets_for({**MAN, "goal": "lose"})
    assert rows["energy"]["target_amount"] == 2790     # 3293 - 500
    assert rows["protein"]["target_amount"] == 128     # 1.6 x 80 kg
    assert "lose" in rows["protein"]["source"]


def test_regular_training_means_more_protein():
    rows, _ = targets_for({**WOMAN, "weight_kg": 75, "lifestyle": "mostly_seated", "exercise_sessions_per_week": 3})
    # Energy: (750 + 1031.25 - 150 - 161) x (1.45 + 0.2) = 2426 -> 2430 kcal, so 15-25% is 91 to 152 g.
    # 1.4 g x 75 kg = 105 g sits inside that, and is more than the RDI (0.75 x 75 = 56 g).
    assert rows["protein"]["target_amount"] == 105


def test_never_below_resting_energy():
    small = {**WOMAN, "date_of_birth": date(1966, 1, 1), "height_cm": 150, "weight_kg": 45,
             "lifestyle": "mostly_seated", "goal": "lose"}
    rows, result = targets_for(small)
    # BMR = 450 + 937.5 - 300 - 161 = 926.5. x 1.45 - 500 = 843, which is less, so it's raised to 930
    assert rows["energy"]["target_amount"] == 930
    assert any("resting energy" in note for note in result["notes"])


# ---------------------------------------------------------------- pregnancy and breastfeeding

PREGNANT = {**WOMAN, "weight_kg": 70, "pre_pregnancy_weight_kg": 62}


def test_second_trimester_adds_energy_and_uses_pregnancy_values():
    rows, result = targets_for({**PREGNANT, "due_date": ON + timedelta(weeks=20)})
    assert result["situation"]["trimester"] == 2 and result["situation"]["pregnancy_week"] == 20
    # BMR from the pre-pregnancy weight: 620 + 1031.25 - 150 - 161 = 1340.25
    # x 1.65 = 2211.4, + 1.4 MJ (334.6 kcal) = 2546 -> 2550
    assert rows["energy"]["target_amount"] == 2550
    assert rows["iron"]["target_amount"] == 27
    assert rows["alcohol"]["upper_limit"] == 0
    assert rows["caffeine"]["upper_limit"] == 200
    assert any("folic acid" in note for note in result["notes"])


def test_first_trimester_needs_no_extra_energy_or_protein():
    rows, result = targets_for({**PREGNANT, "due_date": ON + timedelta(weeks=30)})
    assert result["situation"]["trimester"] == 1
    assert rows["energy"]["target_amount"] == 2210     # 1340.25 x 1.65 = 2211
    assert rows["iron"]["target_amount"] == 27         # the vitamin and mineral needs change straight away


def test_breastfeeding_adds_2_mj():
    rows, result = targets_for({**WOMAN, "breastfeeding": True})
    # 1320.25 x 1.65 = 2178.4, + 2 MJ (478 kcal) = 2656 -> 2660
    assert rows["energy"]["target_amount"] == 2660
    assert rows["iron"]["target_amount"] == 9
    assert result["situation"]["life_stage"] == "breastfeeding"


# ---------------------------------------------------------------- diet, age and the rest

def test_vegetarians_need_more_iron_and_zinc():
    rows, _ = targets_for({**WOMAN, "diet": "vegetarian"})
    assert rows["iron"]["target_amount"] == 32.4       # 18 x 1.8
    assert rows["zinc"]["target_amount"] == 12         # 8 x 1.5


def test_a_vegetarian_target_never_goes_over_the_upper_limit():
    rows, result = targets_for({**PREGNANT, "diet": "vegetarian", "due_date": ON + timedelta(weeks=20)})
    assert rows["iron"]["target_amount"] == 45         # 27 x 1.8 = 48.6, but the upper limit is 45
    assert any("supplement" in note for note in result["notes"])


def test_vegans_get_a_b12_note():
    _, result = targets_for({**WOMAN, "diet": "vegan"})
    assert any("B12" in note for note in result["notes"])


def test_teenagers_get_no_alcohol_and_less_caffeine():
    rows, _ = targets_for({**MAN, "date_of_birth": date(2010, 1, 1), "weight_kg": 60})
    assert rows["alcohol"]["upper_limit"] == 0
    assert rows["caffeine"]["upper_limit"] == 180      # 3 mg x 60 kg


def test_adult_limits():
    rows, _ = targets_for(MAN)
    assert rows["alcohol"]["upper_limit"] == 14.3      # 10 standard drinks of 10 g a week, per day
    assert rows["caffeine"]["upper_limit"] == 400
    assert rows["saturated_fat"]["upper_limit"] == 37  # 10% of 3290 kcal / 9
    assert rows["free_sugars"]["upper_limit"] == 82    # 10% of 3290 kcal / 4


def test_sodium_has_a_limit_not_a_target_and_fibre_has_an_aim():
    rows, _ = targets_for(WOMAN)
    assert rows["sodium"]["target_amount"] is None and rows["sodium"]["upper_limit"] == 2000
    assert rows["fibre"]["target_amount"] == 25 and rows["fibre"]["aim"] == 28


def test_nutrients_without_australian_data_are_left_out():
    rows, _ = targets_for(WOMAN)
    assert "vitamin_k" not in rows


@pytest.mark.parametrize("key", ["energy", "protein", "iron", "alcohol", "caffeine", "sodium"])
def test_every_target_says_where_it_came_from(key):
    rows, _ = targets_for(WOMAN)
    assert rows[key]["source"]
