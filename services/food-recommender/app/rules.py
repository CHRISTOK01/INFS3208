"""Choosing foods to fill someone's gaps. Plain functions, no database, so they're easy to test.

How it works:
  1. Start from what gap-analysis says the person is short on over the last 14 days, and how much
     short they are each day (the "shortfall": target minus their average).
  2. Only Australian (AUSNUT) foods are considered, because FSANZ tags each one with its Australian
     Dietary Guidelines food group and says whether it's a "discretionary" (sometimes) food. We only
     suggest everyday foods the guidelines give a "standard serve" for, like 75 g of vegetables or
     65 g of cooked red meat. So no mixed dishes, juice, flour or oils, just simple foods you can
     add to a meal.
  3. Foods are skipped if they don't suit the person: meat and fish for vegetarians (and eggs and
     dairy for vegans), foods FSANZ says to avoid in pregnancy, anything that would take them over
     a limit today (like sodium or caffeine), and anything with more energy than they have left.
     Someone who's already over a limit can still have foods with only a little of it.
  4. Each food is scored on one standard serve: for each gap, how much of the daily shortfall the
     serve makes up (at most 100%), added together. So a food that covers two gaps beats one that
     covers one, and nothing gets extra credit for going way past what's needed.
  5. The best go first, with a bit of variety: one food per kind of food (so not five cuts of beef)
     and no more than three from each food group.
"""
import re
from collections import Counter

# The five food groups. An AUSNUT dietary guidelines code starts with the group's number,
# e.g. 301 "Fresh/canned fruit" or 5011 "Unprocessed meat".
FOOD_GROUPS = {
    "1": "grain foods",
    "2": "vegetables and legumes",
    "3": "fruit",
    "4": "milk, yoghurt, cheese and alternatives",
    "5": "lean meats, fish, eggs, nuts, seeds and tofu",
}

# The Australian Dietary Guidelines' standard serves, in grams, for each AUSNUT code we suggest.
#   https://www.eatforhealth.gov.au/food-essentials/how-much-do-we-need-each-day/serve-sizes
# Codes that aren't here aren't suggested: mixed dishes, oils, flour, milk powder, custard, and the
# foods the guidelines say to have "only occasionally" (juice and dried fruit).
STANDARD_SERVES = {
    # vegetables: about 75 g (1/2 cup cooked, 1 cup salad, 1/2 a medium potato)
    201: 75, 202: 75, 203: 75, 204: 75, 2051: 75,
    # fruit: about 150 g (1 medium apple or banana, 1 cup diced)
    301: 150,
    # grain foods
    1011: 40, 1021: 40,       # 1 slice of bread or 1/2 a roll
    1012: 100, 1022: 100,     # 1/2 cup cooked rice, pasta, noodles or quinoa (75-120 g, so the middle)
    1014: 30, 1024: 30,       # 2/3 cup breakfast cereal flakes
    1015: 35, 1025: 35,       # 3 crispbreads
    1016: 60, 1026: 60,       # 1 crumpet
    1027: 35,                 # 1 small English muffin or scone
    # lean meats and alternatives
    5011: 65, 5012: 65, 5021: 65, 5022: 65,   # cooked lean red meat
    5031: 80, 5032: 80, 5041: 80,             # cooked poultry
    505: 100,                 # cooked fish fillet
    506: 120,                 # 2 large eggs
    508: 30,                  # nuts and seeds
    5072: 170,                # tofu
    # milk, yoghurt, cheese and alternatives
    4021: 250, 4031: 250,     # 1 cup of milk
    4027: 250, 4037: 250,     # 1 cup of calcium-enriched plant milk
    4032: 120,                # 1/2 cup evaporated milk
    4011: 40,                 # 2 slices of hard cheese
    4025: 120, 4035: 120,     # 1/2 cup ricotta
    4026: 200, 4036: 200,     # 3/4 cup yoghurt
}
NUTS_AND_SEEDS = 508                  # eaten raw, unlike the rest of their group
STARCHY_VEG_AND_LEGUMES = {203, 204}  # potatoes, cassava, beans, lentils: cooked before eating
PLANT_MILKS = {4027, 4037}            # soy, oat, rice milk and so on

# AUSNUT also has foods for babies and toddlers, medical drinks, and foods most people can't buy
# (wild-harvested and game foods, emu eggs). They're real foods, but odd to suggest.
UNUSUAL = re.compile(r"infant|toddler|breast milk|supplementary|wild|game|reptile|insect|^eggs, other|^herbs",
                     re.IGNORECASE)
# Ingredients and concentrated forms nobody eats a whole standard serve of: 75 g of dried mushroom
# or garlic, 120 g of egg yolk (about 7 yolks), 100 g of wheat germ. (Dried seeds are fine.)
INGREDIENT_WORDS = re.compile(
    r"\b(dried|sundried|dehydrated|powder|paste|peel|germ|breadcrumbs?|grated|yolk|skin|garlic|ginger|"
    r"chilli|popcorn|truffles?|infant|toddler|babyccino)\b",
    re.IGNORECASE,
)
NEEDS_COOKING_WORDS = re.compile(r"\b(uncooked|unprepared|dry|dried)\b", re.IGNORECASE)

# Foods FSANZ advises against in pregnancy. Listeria: soft and semi-soft cheeses, pate, cold
# smoked seafood, raw sprouts and rockmelon. Mercury: shark (flake), billfish (swordfish, broadbill,
# marlin), orange roughy and catfish, which FSANZ limits to one serve a week or fortnight with no
# other fish, so we just leave them out.
#   https://www.foodstandards.gov.au/consumer/prevention-of-foodborne-illness/bacteria-foodborne-illness/listeria
#   https://www.foodstandards.gov.au/consumer/chemicals/mercury
PREGNANCY_AVOID = re.compile(
    r"\b(brie|camembert|ricotta|feta|blue|pate|pâté|smoked|sprouts?|rockmelon|"
    r"shark|flake|swordfish|broadbill|marlin|orange roughy|catfish)\b",
    re.IGNORECASE,
)

# A serve has to make up at least this much of one shortfall to be worth suggesting
MIN_FILL = 0.10
MAX_PER_GROUP = 3
# If someone has already eaten their energy for the day, we still show foods up to this many kcal
# (most fruit and vegetables), rather than nothing at all
MIN_ENERGY_BUDGET_KCAL = 150
# A serve can't take today's total over a limit. But once someone is already over (a salty lunch,
# say), nearly every food has a little sodium, so that rule would leave nothing at all. So a serve
# with no more than this share of the daily limit is always allowed: plain fruit and vegetables, not
# salty ones. A limit of 0 (like alcohol in pregnancy) still allows none.
LIMIT_ALLOWANCE = 0.10

NAMES = {
    "fibre": "fibre", "calcium": "calcium", "iodine": "iodine", "iron": "iron", "magnesium": "magnesium",
    "phosphorus": "phosphorus", "potassium": "potassium", "selenium": "selenium", "zinc": "zinc",
    "copper": "copper", "manganese": "manganese", "vitamin_a": "vitamin A", "thiamin": "thiamin (B1)",
    "riboflavin": "riboflavin (B2)", "niacin": "niacin (B3)", "pantothenic": "pantothenic acid (B5)",
    "vitamin_b6": "vitamin B6", "folate": "folate", "vitamin_b12": "vitamin B12", "vitamin_c": "vitamin C",
    "vitamin_d": "vitamin D", "vitamin_e": "vitamin E", "omega3_lc": "long-chain omega-3",
    "sodium": "sodium", "saturated_fat": "saturated fat", "free_sugars": "free sugars",
    "alcohol": "alcohol", "caffeine": "caffeine",
}


def nice_name(key: str) -> str:
    return NAMES.get(key, key.replace("_", " "))


# ---------------------------------------------------------------- what kind of food is it

def food_group(adg_code: int | None) -> str | None:
    """Which of the five food groups an AUSNUT food is in, or None if it isn't in one."""
    if adg_code is None:
        return None
    return FOOD_GROUPS.get(str(adg_code)[0])


def animal_source(adg_code: int) -> str | None:
    """"meat", "fish", "egg" or "dairy" if the food comes from an animal, worked out from its code."""
    if adg_code // 10 in (501, 502, 503, 504):     # meat and poultry, lean or fatty, processed or not
        return "meat"
    if adg_code == 505:
        return "fish"
    if adg_code == 506:
        return "egg"
    if 4000 <= adg_code < 5000 and adg_code not in PLANT_MILKS:
        return "dairy"
    return None


DIET_LEAVES_OUT = {
    "omnivore": set(),
    "vegetarian": {"meat", "fish"},
    "vegan": {"meat", "fish", "egg", "dairy"},
}


def main_food(name: str) -> str:
    """The part of the name before the first comma: "Beef, rump steak, grilled" -> "beef"."""
    return name.split(",")[0].strip().lower()


def needs_cooking(food: dict) -> bool:
    """True for the raw or dry form of something you'd normally cook, like raw chicken, dry rice,
    dried lentils or raw potato. Raw fruit, vegetables, nuts and seeds are fine as they are."""
    code = food["adg_code"]
    raw_or_dry = food["prep_state"] == "raw" or bool(NEEDS_COOKING_WORDS.search(food["name"]))
    if str(code)[0] in "15" and code != NUTS_AND_SEEDS:
        return raw_or_dry
    if code in STARCHY_VEG_AND_LEGUMES:
        return raw_or_dry and food["prep_state"] != "cooked"
    return False


# ---------------------------------------------------------------- does it suit this person today

def why_not(food: dict, situation: dict, today: dict[str, dict], energy_budget: float) -> str | None:
    """The reason a food isn't suggested, or None if it's fine.

    `today` is {nutrient_key: {"amount": eaten so far today or None, "upper_limit": ...}} and
    `energy_budget` is how many kcal we're happy for one serve to have.
    """
    code = food["adg_code"]
    if food["discretionary"]:
        return "a sometimes food"
    if code not in STANDARD_SERVES:
        return "the dietary guidelines don't give it a standard serve"
    if UNUSUAL.search(food.get("category") or ""):
        return "not something most people can buy or would eat"
    if code != NUTS_AND_SEEDS and INGREDIENT_WORDS.search(food["name"]):
        return "an ingredient, not something you'd eat a whole serve of"
    if needs_cooking(food):
        return "the raw or dry form of a food you'd cook"
    source = animal_source(code)
    if source in DIET_LEAVES_OUT.get(situation.get("diet") or "omnivore", set()):
        return f"has {source}, which your diet leaves out"
    if situation.get("life_stage") == "pregnant" and PREGNANCY_AVOID.search(food["name"]):
        return "FSANZ advises avoiding it in pregnancy"

    grams = STANDARD_SERVES[code]
    if food["kcal"] is not None and food["kcal"] * grams / 100 > energy_budget:
        return "more energy than you have left today"
    for key, row in today.items():
        limit = row.get("upper_limit")
        per_100g = food["nutrients"].get(key)
        if limit is None or per_100g is None:
            continue
        if key == "vitamin_a" and source is None:
            # The upper limit is for retinol, which only comes from animal foods. Plant foods have
            # beta-carotene instead, which has no upper limit.
            continue
        allowed = max(limit - (row.get("amount") or 0), LIMIT_ALLOWANCE * limit)
        if per_100g * grams / 100 > allowed:
            return f"would take you over your limit for {nice_name(key)} today"
    return None


# ---------------------------------------------------------------- scoring and explaining

def score(food: dict, shortfalls: dict[str, float]) -> tuple[float, list[dict]]:
    """How much of the shortfalls one standard serve makes up (each counted up to 100%), and the details.

    If a food has no value for a nutrient (only possible for copper, manganese and pantothenic
    acid), it just doesn't count towards that one. Unknown is never treated as zero, or as plenty.
    """
    grams = STANDARD_SERVES[food["adg_code"]]
    total, covers = 0.0, []
    for key, short in shortfalls.items():
        per_100g = food["nutrients"].get(key)
        if per_100g is None or short <= 0:
            continue
        amount = per_100g * grams / 100
        fill = min(amount / short, 1.0)
        if fill > 0:
            total += fill
            covers.append({"nutrient_key": key, "amount": round(amount, 2), "pct_of_shortfall": round(100 * fill)})
    covers.sort(key=lambda c: -c["pct_of_shortfall"])
    return round(total, 3), covers


def serve_kcal(food: dict) -> int | None:
    if food["kcal"] is None:
        return None
    return round(food["kcal"] * STANDARD_SERVES[food["adg_code"]] / 100)


def show_number(x: float) -> str:
    """Round for reading: 1790.4 -> "1,790", 28.94 -> "29", 6.62 -> "6.6", 0.143 -> "0.14"."""
    if x >= 10:
        return f"{round(x):,}"
    return f"{x:.2g}"


def explain(food: dict, covers: list[dict], units: dict[str, str]) -> str:
    """Something like "A standard serve (75 g) gives 2.5 mg of iron (31% of what you're short each
    day) and 36 mg of magnesium (24%), for 87 kcal."."""
    parts = []
    for i, c in enumerate(covers):
        text = f"{show_number(c['amount'])} {units.get(c['nutrient_key'], '')} of {nice_name(c['nutrient_key'])}"
        text += f" ({c['pct_of_shortfall']}% of what you're short each day)" if i == 0 else f" ({c['pct_of_shortfall']}%)"
        parts.append(text)
    listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    kcal = serve_kcal(food)
    energy = f", for {kcal} kcal" if kcal is not None else ""
    return f"A standard serve ({STANDARD_SERVES[food['adg_code']]} g) gives {listed}{energy}."


def energy_budget(energy_left: float | None) -> float:
    """How many kcal one serve may have: what's left today, but never less than 150."""
    return max(energy_left, MIN_ENERGY_BUDGET_KCAL) if energy_left is not None else float("inf")


def why_nothing_fits(foods: list[dict], situation: dict, today: dict[str, dict], energy_left: float | None) -> str | None:
    """When nothing gets suggested, a sentence giving the most common reason that's about today
    (energy or a limit), so the website can say something more useful than "no foods fit"."""
    reasons = Counter(why_not(f, situation, today, energy_budget(energy_left)) for f in foods)
    about_today = [(count, reason) for reason, count in reasons.items() if reason and reason.endswith("today")]
    if not about_today:
        return None
    reason = max(about_today)[1]
    if reason.startswith("more energy"):
        return "Nothing fits today: you've used up today's energy. Check back tomorrow."
    return f"Nothing fits today: most foods {reason}. Check back tomorrow."



def recommend(foods: list[dict], shortfalls: dict[str, float], units: dict[str, str],
              situation: dict, today: dict[str, dict], energy_left: float | None, limit: int) -> list[dict]:
    """Pick the best `limit` foods for these shortfalls (see the top of this file for the rules)."""
    budget = energy_budget(energy_left)
    scored = []
    for food in foods:
        if why_not(food, situation, today, budget):
            continue
        total, covers = score(food, shortfalls)
        if not covers or covers[0]["pct_of_shortfall"] < 100 * MIN_FILL:
            continue
        scored.append((total, -(serve_kcal(food) or 0), food, covers))
    # Highest score first. If two score the same, the one with less energy goes first.
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)

    picked, seen_foods, per_group = [], set(), {}
    for total, _, food, covers in scored:
        group = food_group(food["adg_code"])
        if main_food(food["name"]) in seen_foods or per_group.get(group, 0) >= MAX_PER_GROUP:
            continue
        seen_foods.add(main_food(food["name"]))
        per_group[group] = per_group.get(group, 0) + 1
        picked.append({
            "fdc_id": food["fdc_id"],
            "name": food["name"],
            "food_group": group,
            "serve_g": STANDARD_SERVES[food["adg_code"]],
            "kcal": serve_kcal(food),
            "score": total,
            "covers": [{**c, "unit": units.get(c["nutrient_key"])} for c in covers],
            "why": explain(food, covers, units),
        })
        if len(picked) == limit:
            break
    return picked


def shortfalls_from_report(report: dict, window_days: int = 14) -> tuple[dict[str, float], dict, list[dict]]:
    """The gaps from gap-analysis's report: {nutrient: how much short per day}, the window used, and
    the gap rows (biggest first)."""
    window = next((w for w in report["windows"] if w["window_days"] == window_days), report["windows"][-1])
    rows = {n["nutrient_key"]: n for n in window["nutrients"]}
    gaps = []
    for key in window["top_gaps"]:
        n = rows[key]
        short = round(n["target_amount"] - n["avg_intake"], 2)
        gaps.append({"nutrient_key": key, "unit": n["unit"], "avg_intake": n["avg_intake"],
                     "target_amount": n["target_amount"], "shortfall": short})
    return {g["nutrient_key"]: g["shortfall"] for g in gaps}, window, gaps
