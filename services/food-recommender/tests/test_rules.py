"""Tests for choosing foods. No database or other services needed. Amounts are per 100 g, and
the comments work out what's in one standard serve."""
from app import rules

OMNIVORE = {"diet": "omnivore", "life_stage": "none"}
NO_LIMITS: dict = {}
UNITS = {"iron": "mg", "magnesium": "mg", "copper": "mg"}


def food(name, adg_code, nutrients, kcal=100, prep_state=None, discretionary=False, category="", fdc_id=1):
    return {"fdc_id": fdc_id, "name": name, "category": category, "adg_code": adg_code,
            "discretionary": discretionary, "prep_state": prep_state, "kcal": kcal, "nutrients": nutrients}


# A serve of lentils is 75 g: 3 mg iron, 30 mg magnesium, 90 kcal
LENTILS = food("Lentil, brown, boiled", 204, {"iron": 4.0, "magnesium": 40}, kcal=120, prep_state="cooked")
# A serve of red meat is 65 g: 2.6 mg iron, 13 mg magnesium, 130 kcal
BEEF = food("Beef, rump steak, lean, grilled", 5011, {"iron": 4.0, "magnesium": 20}, kcal=200)
SALMON_SMOKED = food("Salmon, smoked", 505, {"iron": 0.8})
YOGHURT = food("Yoghurt, natural", 4026, {"magnesium": 15})
SOY_MILK = food("Soy beverage, calcium fortified", 4037, {"magnesium": 20})


# ---------------------------------------------------------------- what kind of food

def test_food_groups_come_from_the_first_digit_of_the_code():
    assert rules.food_group(301) == "fruit"
    assert rules.food_group(5011) == rules.food_group(508) == "lean meats, fish, eggs, nuts, seeds and tofu"
    assert rules.food_group(80) is None and rules.food_group(None) is None


def test_animal_sources():
    assert rules.animal_source(5011) == rules.animal_source(5041) == "meat"
    assert rules.animal_source(505) == "fish" and rules.animal_source(506) == "egg"
    assert rules.animal_source(4026) == "dairy"
    assert rules.animal_source(4037) is None          # calcium-enriched plant milk
    assert rules.animal_source(5072) is None          # tofu
    assert rules.animal_source(508) is None           # nuts and seeds


def test_raw_meat_dry_rice_and_raw_potato_need_cooking_but_raw_nuts_and_fruit_dont():
    assert rules.needs_cooking(food("Chicken, breast, raw", 5031, {}, prep_state="raw"))
    assert rules.needs_cooking(food("Rice, white, uncooked", 1022, {}))
    assert rules.needs_cooking(food("Lentil, dried", 204, {}))
    assert rules.needs_cooking(food("Potato, peeled, raw", 203, {}, prep_state="raw"))
    assert not rules.needs_cooking(LENTILS)
    assert not rules.needs_cooking(food("Almond, with skin, raw", 508, {}, prep_state="raw"))
    assert not rules.needs_cooking(food("Apple, raw", 301, {}, prep_state="raw"))
    assert not rules.needs_cooking(food("Spinach, raw", 201, {}, prep_state="raw"))


# ---------------------------------------------------------------- does it suit the person

def test_everyday_foods_pass():
    assert rules.why_not(LENTILS, OMNIVORE, NO_LIMITS, 2000) is None


def test_only_everyday_foods_with_a_standard_serve():
    assert rules.why_not({**LENTILS, "discretionary": True}, OMNIVORE, NO_LIMITS, 2000) == "a sometimes food"
    assert "standard serve" in rules.why_not({**LENTILS, "adg_code": 80}, OMNIVORE, NO_LIMITS, 2000)    # a mixed dish
    assert "standard serve" in rules.why_not({**LENTILS, "adg_code": 303}, OMNIVORE, NO_LIMITS, 2000)   # juice


def test_unusual_foods_are_left_out():
    infant = food("Infant cereal, rice, added Fe", 1024, {"iron": 20}, category="Infant cereals")
    emu_egg = food("Egg, emu, whole, cooked", 506, {"iron": 3}, category="Eggs, other")
    assert "buy" in rules.why_not(infant, OMNIVORE, NO_LIMITS, 2000)
    assert "buy" in rules.why_not(emu_egg, OMNIVORE, NO_LIMITS, 2000)


def test_ingredients_are_left_out_but_dried_seeds_are_fine():
    assert "ingredient" in rules.why_not(food("Mushroom, dried", 2051, {}), OMNIVORE, NO_LIMITS, 2000)
    assert "ingredient" in rules.why_not(food("Egg, chicken, yolk, cooked", 506, {}), OMNIVORE, NO_LIMITS, 2000)
    assert rules.why_not(food("Seed, chia, dried", 508, {}), OMNIVORE, NO_LIMITS, 2000) is None


def test_diets():
    vegetarian = {**OMNIVORE, "diet": "vegetarian"}
    vegan = {**OMNIVORE, "diet": "vegan"}
    assert "meat" in rules.why_not(BEEF, vegetarian, NO_LIMITS, 2000)
    assert rules.why_not(YOGHURT, vegetarian, NO_LIMITS, 2000) is None
    assert "dairy" in rules.why_not(YOGHURT, vegan, NO_LIMITS, 2000)
    assert rules.why_not(SOY_MILK, vegan, NO_LIMITS, 2000) is None


def test_pregnancy_leaves_out_what_fsanz_advises_against():
    pregnant = {**OMNIVORE, "life_stage": "pregnant"}
    assert "pregnancy" in rules.why_not(SALMON_SMOKED, pregnant, NO_LIMITS, 2000)
    assert "pregnancy" in rules.why_not(food("Shark (flake), grilled", 505, {}), pregnant, NO_LIMITS, 2000)
    assert rules.why_not(SALMON_SMOKED, OMNIVORE, NO_LIMITS, 2000) is None
    assert rules.why_not(BEEF, pregnant, NO_LIMITS, 2000) is None


def test_not_more_energy_than_is_left():
    assert rules.why_not(BEEF, OMNIVORE, NO_LIMITS, 100) == "more energy than you have left today"   # 130 kcal
    assert rules.why_not(BEEF, OMNIVORE, NO_LIMITS, 150) is None


def test_not_over_a_limit_today():
    bread = food("Bread, white", 1021, {"sodium": 1000})          # a 40 g slice has 400 mg
    assert "sodium" in rules.why_not(bread, OMNIVORE, {"sodium": {"amount": 1700, "upper_limit": 2000}}, 2000)
    assert rules.why_not(bread, OMNIVORE, {"sodium": {"amount": 1000, "upper_limit": 2000}}, 2000) is None


def test_once_over_a_limit_foods_with_only_a_little_are_still_fine():
    over = {"sodium": {"amount": 3000, "upper_limit": 2000}}
    banana = food("Banana, raw", 301, {"sodium": 1})               # 1.5 mg in 150 g
    bread = food("Bread, white", 1021, {"sodium": 1000})           # 400 mg in a 40 g slice
    assert rules.why_not(banana, OMNIVORE, over, 2000) is None
    assert "sodium" in rules.why_not(bread, OMNIVORE, over, 2000)   # more than 10% of the limit (200 mg)


def test_a_limit_of_none_still_allows_none():
    pregnant = {"alcohol": {"amount": 0, "upper_limit": 0}}
    assert "alcohol" in rules.why_not(food("Wine-poached pear", 301, {"alcohol": 1}), OMNIVORE, pregnant, 2000)


def test_why_nothing_fits_explains_the_day():
    over = {"sodium": {"amount": 9000, "upper_limit": 2000}}
    salty = [food("Bread, white", 1021, {"sodium": 1000}, fdc_id=i) for i in range(3)]
    assert rules.why_nothing_fits(salty, OMNIVORE, over, 1000) == (
        "Nothing fits today: most foods would take you over your limit for sodium today. Check back tomorrow.")
    filling = [food("Beef, grilled", 5011, {}, kcal=500)]          # 325 kcal a serve
    assert "used up today's energy" in rules.why_nothing_fits(filling, OMNIVORE, {}, 0)
    assert rules.why_nothing_fits([LENTILS], OMNIVORE, {}, 2000) is None


def test_the_vitamin_a_limit_only_counts_animal_foods():
    limit = {"vitamin_a": {"amount": 0, "upper_limit": 3000}}
    liver = food("Liver, lamb, fried", 5011, {"vitamin_a": 20000})   # 13,000 ug in 65 g
    carrot = food("Carrot, raw", 202, {"vitamin_a": 5000})           # 3,750 ug, but it's beta-carotene
    assert "vitamin A" in rules.why_not(liver, OMNIVORE, limit, 2000)
    assert rules.why_not(carrot, OMNIVORE, limit, 2000) is None


# ---------------------------------------------------------------- scoring and explaining

def test_each_gap_counts_up_to_100_percent():
    total, covers = rules.score(LENTILS, {"iron": 2.0, "magnesium": 100})
    # 3 mg iron is more than the 2 mg short (100%), and 30 mg magnesium is 30% of 100
    assert total == 1.3
    assert covers[0] == {"nutrient_key": "iron", "amount": 3.0, "pct_of_shortfall": 100}


def test_unknown_values_dont_count():
    total, covers = rules.score(LENTILS, {"copper": 0.5})      # these lentils have no copper value
    assert total == 0 and covers == []


def test_numbers_are_rounded_for_reading():
    assert rules.show_number(1790.4) == "1,790"
    assert rules.show_number(28.94) == "29"
    assert rules.show_number(6.62) == "6.6"
    assert rules.show_number(0.143) == "0.14"


def test_micrograms_are_written_with_the_mu_sign():
    egg = food("Egg, chicken, whole, boiled", 506, {"vitamin_d": 2.0})       # 2.4 ug in 2 eggs (120 g)
    _, covers = rules.score(egg, {"vitamin_d": 5.0})
    assert "2.4 µg of vitamin D" in rules.explain(egg, covers, {"vitamin_d": "ug"})


def test_explanation():
    _, covers = rules.score(LENTILS, {"iron": 10.0, "magnesium": 50})
    assert rules.explain(LENTILS, covers, UNITS) == (
        "A standard serve (75 g) gives 30 mg of magnesium (60% of what you're short each day) "
        "and 3 mg of iron (30%), for 90 kcal.")


def test_recommend_ranks_and_keeps_variety():
    foods = [
        BEEF,
        {**BEEF, "fdc_id": 2, "name": "Beef, mince, lean, cooked"},     # another beef: only the best is kept
        {**LENTILS, "fdc_id": 3},
        food("Spinach, boiled", 201, {"iron": 2.0, "magnesium": 80}, kcal=24, fdc_id=4),
        food("Rice, white, boiled", 1022, {"iron": 0.1}, fdc_id=5),     # under 10% of the shortfall
    ]
    picked = rules.recommend(foods, {"iron": 6.0, "magnesium": 100}, UNITS, OMNIVORE, NO_LIMITS, 2000, 10)
    # spinach 1.5/6 + 60/100 = 0.85, lentils 3/6 + 30/100 = 0.8, beef 2.6/6 + 13/100 = 0.56
    assert [p["name"] for p in picked] == ["Spinach, boiled", "Lentil, brown, boiled", "Beef, rump steak, lean, grilled"]
    assert picked[1]["serve_g"] == 75 and picked[1]["kcal"] == 90
    assert picked[1]["covers"][0]["unit"] == "mg"


def test_shortfalls_from_the_report():
    report = {"windows": [
        {"window_days": 7, "days_logged": 6, "top_gaps": ["iron"], "nutrients": [
            {"nutrient_key": "iron", "unit": "mg", "avg_intake": 9.5, "target_amount": 18, "pct_of_target": 52.8, "status": "gap"},
            {"nutrient_key": "zinc", "unit": "mg", "avg_intake": 9, "target_amount": 8, "status": "ok"}]},
    ]}
    shortfalls, window, gaps = rules.shortfalls_from_report(report)
    assert shortfalls == {"iron": 8.5} and window["days_logged"] == 6
    assert gaps[0]["shortfall"] == 8.5


def test_today_counts_everything_not_reached_yet():
    rows = [
        {"nutrient_key": "energy", "unit": "kcal", "amount": 800, "target_amount": 2000},     # a budget, not a gap
        {"nutrient_key": "iron", "unit": "mg", "amount": 6, "target_amount": 18},
        {"nutrient_key": "calcium", "unit": "mg", "amount": 1200, "target_amount": 1000},     # already reached
        {"nutrient_key": "vitamin_d", "unit": "ug", "amount": None, "target_amount": 5},      # nothing yet
        {"nutrient_key": "sodium", "unit": "mg", "amount": 900, "target_amount": None},       # only a limit
    ]
    shortfalls, top = rules.shortfalls_for_today(rows)
    assert shortfalls == {"iron": 12, "vitamin_d": 5}
    assert [g["nutrient_key"] for g in top] == ["vitamin_d", "iron"]      # furthest from the target first


def test_explanations_say_what_the_percentage_is_of():
    _, covers = rules.score(LENTILS, {"iron": 6.0})
    assert "(50% of what you still need today)" in rules.explain(LENTILS, covers, UNITS, "of what you still need today")


def test_only_the_top_nutrients_are_listed():
    many = food("Spinach, boiled", 201, {k: 10 for k in ["iron", "magnesium", "calcium", "zinc", "folate", "vitamin_c"]})
    shortfalls = {k: 10.0 for k in ["iron", "magnesium", "calcium", "zinc", "folate", "vitamin_c"]}
    total, covers = rules.score(many, shortfalls)
    picked = rules.recommend([many], shortfalls, UNITS, OMNIVORE, NO_LIMITS, 2000, 5)
    assert total == 4.5                                     # all six count towards the score (75% each)...
    assert len(picked[0]["covers"]) == rules.MAX_COVERS_SHOWN   # ...but only four are listed


def test_today_counts_macros_and_partly_known_nutrients():
    rows = [
        {"nutrient_key": "carbs", "unit": "g", "amount": 150, "target_amount": 310, "coverage_pct": 100.0},
        {"nutrient_key": "copper", "unit": "mg", "amount": 0.3, "target_amount": 1.2, "coverage_pct": 40.0},
    ]
    shortfalls, _ = rules.shortfalls_for_today(rows)
    # copper is worked out from the 40% of the food that has a value for it
    assert shortfalls == {"carbs": 160, "copper": 0.9}

