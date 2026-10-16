"""Reading and cleaning the USDA FoodData Central CSV files.

This file only reads and tidies the data. It doesn't touch any database; load_usda.py does that.

A few quirks of the USDA files that this code deals with:
  - Nutrient IDs aren't the same in every release, so we find nutrients by NAME and UNIT
    (e.g. "Magnesium, Mg" in MG) instead of trusting fixed ID numbers.
  - FNDDS refers to nutrients by their old "nutrient number" (e.g. 304 for magnesium) rather than
    the ID column, so we check which of the two a file uses.
  - Some foods store calories under "Energy (Atwater ...)" instead of plain "Energy", so each
    nutrient has a list of fallbacks to try in order.
  - Amounts come in different units (G, MG, UG, IU). We convert everything to the unit
    nutrient-calc uses. If a value can't be converted exactly, we leave it as unknown.
  - Values that are impossible (like 150 g of protein in 100 g of food) are thrown away.
  - Foundation foods are missing many vitamins that SR Legacy has for the same food, so we fill
    those gaps from SR Legacy (see fill_from_sr_legacy).
"""
import csv
import random
import re
from pathlib import Path

# Our nutrient key -> its unit in nutrient-calc, and the USDA (name, unit) pairs to look for.
# The first pair a food has a value for is the one we use.
NUTRIENTS = {
    "energy":        ("kcal", [("Energy", "KCAL"),
                               ("Energy (Atwater Specific Factors)", "KCAL"),
                               ("Energy (Atwater General Factors)", "KCAL")]),
    "protein":       ("g",  [("Protein", "G")]),
    "carbs":         ("g",  [("Carbohydrate, by difference", "G"), ("Carbohydrate, by summation", "G")]),
    "fat":           ("g",  [("Total lipid (fat)", "G")]),
    "fibre":         ("g",  [("Fiber, total dietary", "G"), ("Total dietary fiber (AOAC 2011.25)", "G")]),
    "calcium":       ("mg", [("Calcium, Ca", "MG")]),
    "iron":          ("mg", [("Iron, Fe", "MG")]),
    "magnesium":     ("mg", [("Magnesium, Mg", "MG")]),
    "phosphorus":    ("mg", [("Phosphorus, P", "MG")]),
    "potassium":     ("mg", [("Potassium, K", "MG")]),
    "sodium":        ("mg", [("Sodium, Na", "MG")]),
    "zinc":          ("mg", [("Zinc, Zn", "MG")]),
    "copper":        ("mg", [("Copper, Cu", "MG")]),
    "manganese":     ("mg", [("Manganese, Mn", "MG")]),
    "selenium":      ("ug", [("Selenium, Se", "UG")]),
    "iodine":        ("ug", [("Iodine, I", "UG")]),
    # Vitamin A in IU can't be turned into RAE exactly, so we only accept RAE
    "vitamin_a":     ("ug", [("Vitamin A, RAE", "UG")]),
    "vitamin_c":     ("mg", [("Vitamin C, total ascorbic acid", "MG")]),
    # Vitamin D in IU converts exactly: 40 IU = 1 microgram
    "vitamin_d":     ("ug", [("Vitamin D (D2 + D3)", "UG"),
                             ("Vitamin D (D2 + D3), International Units", "IU")]),
    "vitamin_e":     ("mg", [("Vitamin E (alpha-tocopherol)", "MG")]),
    "vitamin_k":     ("ug", [("Vitamin K (phylloquinone)", "UG")]),
    "thiamin":       ("mg", [("Thiamin", "MG")]),
    "riboflavin":    ("mg", [("Riboflavin", "MG")]),
    "niacin":        ("mg", [("Niacin", "MG")]),
    "pantothenic":   ("mg", [("Pantothenic acid", "MG")]),
    "vitamin_b6":    ("mg", [("Vitamin B-6", "MG")]),
    # Folate DFE counts added folic acid as worth more. If a food only has "Folate, total" we use
    # that instead. It's the same number for foods without added folic acid (most whole foods).
    "folate":        ("ug", [("Folate, DFE", "UG"), ("Folate, total", "UG")]),
    "vitamin_b12":   ("ug", [("Vitamin B-12", "UG")]),
    "choline":       ("mg", [("Choline, total", "MG")]),
    "saturated_fat": ("g",  [("Fatty acids, total saturated", "G")]),
    # Older and newer releases spell this one differently
    "sugars":        ("g",  [("Total Sugars", "G"), ("Sugars, Total", "G")]),
    "caffeine":      ("mg", [("Caffeine", "MG")]),
    "alcohol":       ("g",  [("Alcohol, ethyl", "G")]),
    # USDA doesn't have these two as single values, so they only come from the Australian data
    "free_sugars":   ("g",  []),
    "omega3_lc":     ("mg", []),
}

MACROS = ["energy", "protein", "carbs", "fat", "fibre"]
# Things we track mainly to warn about having too much (or, for omega-3, too little)
OTHER = ["saturated_fat", "sugars", "free_sugars", "omega3_lc", "caffeine", "alcohol"]
VITAMINS_AND_MINERALS = [k for k in NUTRIENTS if k not in MACROS + OTHER]

# A generic food counts as having "complete micronutrient data" if we know at least this many
# of its vitamins and minerals. Branded foods are always "label data only".
FULL_MICROS_THRESHOLD = 15

# How each USDA data type shows up in search (lower comes first)
# Australian foods come first, because MacroScope is for people in Australia
SEARCH_RANK = {"ausnut_food": 1, "foundation_food": 2, "sr_legacy_food": 3, "survey_fndds_food": 4, "branded_food": 5}

GRAMS_PER_UNIT = {"G": 1.0, "MG": 1e-3, "UG": 1e-6}
VITAMIN_D_UG_PER_IU = 0.025

RAW_WORDS = re.compile(r"\braw\b", re.I)
COOKED_WORDS = re.compile(
    r"\b(cooked|boiled|baked|roasted|fried|grilled|steamed|braised|broiled|stewed|"
    r"microwaved|scrambled|poached|toasted|sauteed|simmered)\b", re.I)


# ---------------------------------------------------------------- small helpers (unit tested)

def convert(amount: float, usda_unit: str, our_unit: str, key: str) -> float | None:
    """Convert an amount from a USDA unit into ours. Returns None if it can't be done exactly."""
    usda_unit, our_unit = usda_unit.upper(), our_unit.upper()
    if usda_unit == "IU":
        if key == "vitamin_d" and our_unit == "UG":
            return amount * VITAMIN_D_UG_PER_IU
        return None
    if usda_unit == our_unit:
        return amount
    if usda_unit in GRAMS_PER_UNIT and our_unit in GRAMS_PER_UNIT:
        return amount * GRAMS_PER_UNIT[usda_unit] / GRAMS_PER_UNIT[our_unit]
    return None


def is_plausible(key: str, our_unit: str, amount: float) -> bool:
    """Throw away values that can't be right for 100 g of food."""
    if amount < 0:
        return False
    if key == "energy":
        return amount <= 900          # pure fat is about 900 kcal per 100 g, nothing has more
    return amount * GRAMS_PER_UNIT[our_unit.upper()] <= 100   # can't have over 100 g of anything in 100 g


def prep_state(name: str) -> str | None:
    """'raw' or 'cooked' if the food's name says so, otherwise None."""
    if RAW_WORDS.search(name):
        return "raw"
    if COOKED_WORDS.search(name):
        return "cooked"
    return None


def portion_text(amount: str, unit_name: str, modifier: str, description: str) -> str:
    """Turn a USDA portion row into something readable, like "1 cup, chopped" or "2 tablespoon".

    FNDDS fills in `description` ("1 cup"). The other data sets split it across amount, unit and
    modifier, where the unit is often just "undetermined".
    """
    if description.strip():
        return description.strip()
    parts = []
    if amount.strip():
        number = float(amount)
        parts.append(f"{number:g}")           # 1.0 -> "1", 0.5 -> "0.5"
    if unit_name and unit_name != "undetermined":
        parts.append(unit_name)
    if modifier.strip():
        parts.append(modifier.strip())
    return " ".join(parts)


def tidy_name(name: str) -> str:
    """Branded names are often in capitals ("CHEDDAR CHEESE"). Make them easier to read."""
    name = " ".join(name.split())
    return name.title() if name.isupper() else name


# ---------------------------------------------------------------- reading the CSV files

def read_csv(path: Path):
    """Go through a CSV file one row at a time, as dicts. Fine for the multi-GB files too."""
    with open(path, encoding="utf-8", newline="") as fh:
        yield from csv.DictReader(fh)


def nutrient_lookup(folder: Path) -> dict[str, tuple[str, int, str]]:
    """Work out which USDA nutrients we want from this data set.

    Returns {the reference used in food_nutrient.csv: (our key, fallback position, USDA unit)}.
    """
    rows = list(read_csv(folder / "nutrient.csv"))

    # Does food_nutrient.csv refer to nutrients by "id" or by "nutrient_nbr"? Check the first rows.
    ids = {r["id"] for r in rows}
    sample = [r["nutrient_id"] for _, r in zip(range(2000), read_csv(folder / "food_nutrient.csv"))]
    by_number = sum(s in ids for s in sample) < len(sample) / 2
    ref_column = "nutrient_nbr" if by_number else "id"

    lookup = {}
    for key, (_, candidates) in NUTRIENTS.items():
        for position, (name, unit) in enumerate(candidates):
            for r in rows:
                if r["name"].lower() == name.lower() and r["unit_name"].upper() == unit.upper():
                    ref = r[ref_column].split(".")[0]     # nutrient_nbr can look like "304.0"
                    lookup[ref] = (key, position, unit)
    return lookup


def read_nutrients(folder: Path, fdc_ids: set[int]) -> dict[int, dict[str, float]]:
    """Get {fdc_id: {our key: amount per 100 g, in our unit}} for the given foods.

    If a food has several possible sources for a nutrient (like "Energy" and "Energy (Atwater...)"),
    we keep the one that comes first in NUTRIENTS. Missing nutrients are simply not included.
    """
    lookup = nutrient_lookup(folder)
    best: dict[int, dict[str, tuple[int, float]]] = {}
    for r in read_csv(folder / "food_nutrient.csv"):
        match = lookup.get(r["nutrient_id"])
        if match is None or not r["amount"]:
            continue
        fdc_id = int(r["fdc_id"])
        if fdc_id not in fdc_ids:
            continue
        key, position, usda_unit = match
        our_unit = NUTRIENTS[key][0]
        amount = convert(float(r["amount"]), usda_unit, our_unit, key)
        if amount is None or not is_plausible(key, our_unit, amount):
            continue
        current = best.setdefault(fdc_id, {}).get(key)
        if current is None or position < current[0]:
            best[fdc_id][key] = (position, round(amount, 4))
    return {fdc_id: {k: v for k, (_, v) in values.items()} for fdc_id, values in best.items()}


def read_portions(folder: Path, fdc_ids: set[int]) -> dict[int, list[tuple[str, float]]]:
    """Get {fdc_id: [(description, grams), ...]} for household measures like "1 cup"."""
    path = folder / "food_portion.csv"
    if not path.exists():
        return {}
    units = {r["id"]: r["name"] for r in read_csv(folder / "measure_unit.csv")}
    portions: dict[int, list[tuple[str, float]]] = {}
    for r in read_csv(path):
        if not r["fdc_id"]:
            continue   # Foundation has a few hundred stray rows that don't belong to any food
        fdc_id = int(r["fdc_id"])
        grams = float(r["gram_weight"] or 0)
        if fdc_id not in fdc_ids or grams <= 0:
            continue
        text = portion_text(r["amount"], units.get(r["measure_unit_id"], ""), r["modifier"], r["portion_description"])
        if not text or text.lower() == "quantity not specified":
            continue
        existing = portions.setdefault(fdc_id, [])
        if text not in [t for t, _ in existing]:     # the same portion is sometimes listed twice
            existing.append((text, round(grams, 3)))
    return portions


def read_categories(folder: Path) -> dict[str, str]:
    """Food category names by ID. FNDDS uses its own "WWEIA" category list."""
    if (folder / "food_category.csv").exists():
        return {r["id"]: r["description"] for r in read_csv(folder / "food_category.csv")}
    if (folder / "wweia_food_category.csv").exists():
        return {r["wweia_food_category"]: r["wweia_food_category_description"]
                for r in read_csv(folder / "wweia_food_category.csv")}
    return {}


def has_full_micros(data_type: str, nutrients: dict) -> bool:
    """Do we know enough of this food's vitamins and minerals to call its data complete?"""
    known_micros = sum(k in nutrients for k in VITAMINS_AND_MINERALS)
    return data_type != "branded_food" and known_micros >= FULL_MICROS_THRESHOLD


def make_food(fdc_id, name, data_type, category, barcode, nutrients, portions, serving_g):
    """One cleaned-up food, ready to be loaded."""
    return {
        "fdc_id": fdc_id,
        "name": name,
        "data_type": data_type,
        "search_rank": SEARCH_RANK[data_type],
        "category": category,
        "barcode": barcode,
        "prep_state": prep_state(name),
        "has_full_micros": has_full_micros(data_type, nutrients),
        "nutrients": nutrients,
        "portions": portions,
        "typical_serving_g": serving_g,
        # Only AUSNUT has these (see ausnut.py), so they start empty
        "adg_code": None,
        "adg_name": None,
        "discretionary": None,
    }


def read_generic(folder: Path, data_type: str) -> list[dict]:
    """Read one of the generic data sets (Foundation, SR Legacy or FNDDS).

    Foundation's food.csv also contains thousands of lab sample records, so we keep only the rows
    whose data_type is the one we asked for.
    """
    foods = {int(r["fdc_id"]): r for r in read_csv(folder / "food.csv") if r["data_type"] == data_type}
    ids = set(foods)
    nutrients = read_nutrients(folder, ids)
    portions = read_portions(folder, ids)
    categories = read_categories(folder)

    result = []
    for fdc_id, r in foods.items():
        if nutrients.get(fdc_id, {}).get("energy") is None:
            continue   # calories unknown, so the food isn't much use for logging (0 kcal is fine, e.g. water)
        food_portions = portions.get(fdc_id, [])
        result.append(make_food(
            fdc_id, tidy_name(r["description"]), data_type,
            categories.get(r["food_category_id"]), None,
            nutrients[fdc_id], food_portions,
            food_portions[0][1] if food_portions else 100.0,
        ))
    return result


# ---------------------------------------------------------------- filling gaps in Foundation foods

def sr_legacy_links(data_dir: Path) -> dict[int, int]:
    """Which SR Legacy food is the same as each Foundation food: {Foundation fdc_id: SR Legacy fdc_id}.

    USDA gives foods in both data sets an "NDB number". A Foundation food with the same NDB number as
    an SR Legacy food is the same food (USDA measured it again more recently).
    """
    sr_by_ndb = {r["NDB_number"]: int(r["fdc_id"]) for r in read_csv(data_dir / "sr_legacy" / "sr_legacy_food.csv")}
    return {int(r["fdc_id"]): sr_by_ndb[r["NDB_number"]]
            for r in read_csv(data_dir / "foundation" / "foundation_food.csv")
            if r["NDB_number"] in sr_by_ndb}


def fill_from_sr_legacy(foundation: list[dict], sr_legacy: list[dict], links: dict[int, int]) -> int:
    """Fill in nutrients a Foundation food is missing, using USDA's SR Legacy values for the same food.

    Foundation foods are newer, but USDA only measured some nutrients for them. Cooked chicken
    breast, for example, has no fibre, vitamin A, C, D or K, or choline in Foundation, while the
    SR Legacy entry for the same chicken has all of them. We only fill gaps: a value Foundation
    does have is never replaced. Returns how many values were filled in.
    """
    sr_by_id = {f["fdc_id"]: f for f in sr_legacy}
    filled = 0
    for food in foundation:
        sr_food = sr_by_id.get(links.get(food["fdc_id"]))
        if sr_food is None:
            continue
        for key, amount in sr_food["nutrients"].items():
            if key not in food["nutrients"]:
                food["nutrients"][key] = amount
                filled += 1
        food["has_full_micros"] = has_full_micros(food["data_type"], food["nutrients"])
    return filled


# ---------------------------------------------------------------- Branded foods (a subset)

EXCLUDED_BRANDED_CATEGORIES = re.compile(r"supplement|vitamins", re.I)
GRAM_UNITS = {"g", "grm", "gm"}
REQUIRED_FOR_BRANDED = ["energy", "protein", "carbs", "fat"]
MIN_BRANDED_NUTRIENTS = 8


def read_branded(folder: Path, how_many: int, seed: int = 42) -> list[dict]:
    """Pick a random but repeatable selection of `how_many` Branded foods, and read them.

    Only products that are good to log by weight are considered:
      - they have a barcode and aren't discontinued
      - their serving size is in grams (nutrients for "ml" products are per 100 ml, which
        would give wrong numbers when we count in grams)
      - they aren't supplements or vitamins
      - they have calories, protein, carbs and fat, and at least 8 of our nutrients overall
    The same product often appears several times (USDA re-publishes it with updates), so we keep
    only the newest version of each barcode. Using a fixed random seed means every run picks
    exactly the same foods.
    """
    print("    choosing products from branded_food.csv ...", flush=True)
    newest_by_barcode: dict[str, int] = {}
    for r in read_csv(folder / "branded_food.csv"):
        barcode = r["gtin_upc"].strip()
        if (not barcode.isdigit() or r["discontinued_date"]
                or r["serving_size_unit"].strip().lower() not in GRAM_UNITS
                or EXCLUDED_BRANDED_CATEGORIES.search(r["branded_food_category"])):
            continue
        fdc_id = int(r["fdc_id"])
        if fdc_id > newest_by_barcode.get(barcode, 0):
            newest_by_barcode[barcode] = fdc_id
    candidates = set(newest_by_barcode.values())
    print(f"    {len(candidates):,} candidate products, reading their nutrients ...", flush=True)

    nutrients = read_nutrients(folder, candidates)
    good = sorted(
        fdc_id for fdc_id, values in nutrients.items()
        if all(k in values for k in REQUIRED_FOR_BRANDED) and len(values) >= MIN_BRANDED_NUTRIENTS
    )
    chosen = set(random.Random(seed).sample(good, min(how_many, len(good))))
    print(f"    {len(good):,} have enough nutrient data, picked {len(chosen):,}", flush=True)

    details = {}
    for r in read_csv(folder / "branded_food.csv"):
        if int(r["fdc_id"]) in chosen:
            details[int(r["fdc_id"])] = r

    result = []
    for r in read_csv(folder / "food.csv"):
        fdc_id = int(r["fdc_id"])
        if fdc_id not in chosen:
            continue
        d = details[fdc_id]
        brand = tidy_name(d["brand_name"] or d["brand_owner"] or "")
        name = tidy_name(r["description"]) + (f" ({brand})" if brand else "")
        serving_g = float(d["serving_size"] or 0)
        portions = []
        if serving_g > 0:
            label = d["household_serving_fulltext"].strip().lower()
            portions.append((f"1 serving ({label})" if label else "1 serving", round(serving_g, 3)))
        result.append(make_food(
            fdc_id, name, "branded_food", d["branded_food_category"] or None,
            d["gtin_upc"].strip(), nutrients[fdc_id], portions,
            serving_g if serving_g > 0 else 100.0,
        ))
    return result
