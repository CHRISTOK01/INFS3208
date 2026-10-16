"""Reading the Australian food data: FSANZ's AUSNUT 2023, plus three nutrients from AFCD Release 3.

AUSNUT 2023 is the food list FSANZ made for the 2023 National Nutrition and Physical Activity Study.
It has 3,741 foods as Australians eat them, and every food has a value for every one of its 58
nutrients (FSANZ filled any gaps from lab analysis, labels, recipes or overseas data). That makes it
much better for MacroScope than the USDA data: the foods are Australian (Australian bread has
iodised salt and folic acid, US rice has added iron, and so on) and nothing is missing.

AUSNUT doesn't have copper, manganese or pantothenic acid. The Australian Food Composition Database
(AFCD) does for about a thousand of the same foods, and both use the same "public food key"
(like F002258), so we take those three from AFCD where it has them.

Neither has vitamin K or choline, so for Australian foods those stay unknown.

Each AUSNUT food is stored under its 8-digit AUSNUT survey ID (like 12101005). USDA IDs only go
up to about 3 million, so the two can never clash.
"""
from pathlib import Path

import openpyxl

import usda

KJ_PER_KCAL = 4.184

# Our nutrient key -> the AUSNUT column it comes from. The units already match ours (g, mg, ug),
# except energy, which AUSNUT gives in kJ.
AUSNUT_COLUMNS = {
    "energy":        "Energy with dietary fibre (kJ)",
    "protein":       "Protein (g)",
    "carbs":         "Available carbohydrate, with sugar alcohols (g)",
    "fat":           "Total fat (g)",
    "fibre":         "Dietary fibre (g)",
    "calcium":       "Calcium (Ca) (mg)",
    "iodine":        "Iodine (I) (ug)",
    "iron":          "Iron (Fe) (mg)",
    "magnesium":     "Magnesium (Mg) (mg)",
    "phosphorus":    "Phosphorus (P) (mg)",
    "potassium":     "Potassium (K) (mg)",
    "selenium":      "Selenium (Se) (ug)",
    "sodium":        "Sodium (Na) (mg)",
    "zinc":          "Zinc (Zn) (mg)",
    "vitamin_a":     "Vitamin A retinol equivalents (ug)",
    "thiamin":       "Thiamin (B1) (mg)",
    "riboflavin":    "Riboflavin (B2) (mg)",
    # NHMRC's niacin targets are in niacin equivalents (which count niacin made from protein)
    "niacin":        "Niacin derived equivalents (mg)",
    "vitamin_b6":    "Pyridoxine (B6) (mg)",
    "folate":        "Dietary folate equivalents (ug)",
    "vitamin_b12":   "Cobalamin (B12) (ug)",
    "vitamin_c":     "Vitamin C (mg)",
    "vitamin_d":     "Vitamin D3 equivalents (ug)",
    "vitamin_e":     "Vitamin E (mg)",
    "saturated_fat": "Total saturated fat (g)",
    "sugars":        "Total sugars (g)",
    "free_sugars":   "Free sugars (g)",
    "omega3_lc":     "Total long chain omega 3 fatty acids (mg)",
    "caffeine":      "Caffeine (mg)",
    "alcohol":       "Alcohol (g)",
}

# The three we take from AFCD. AFCD's column names have the unit on a second line, so we match the start.
AFCD_COLUMNS = {
    "copper":      "Copper (Cu)",
    "manganese":   "Manganese (Mn)",
    "pantothenic": "Pantothenic acid (B5)",
}

DETAILS_FILE = "AUSNUT 2023 - Food details.xlsx"
NUTRIENTS_FILE = "AUSNUT 2023 - Food nutrient profiles.xlsx"
MEASURES_FILE = "AUSNUT 2023 - Food measures.xlsx"
AFCD_FILE = "AFCD Release 3 - Nutrient profiles.xlsx"

CUP_ML = 250   # an Australian metric cup


# ---------------------------------------------------------------- small helpers (unit tested)

def clean(text) -> str:
    """Excel cells can be None, numbers, or text with stray spaces and line breaks."""
    return " ".join(str(text).split()) if text is not None else ""


def measure_text(quantity, descriptors: list, volume_ml) -> str:
    """Turn an AUSNUT measure into something readable, like "1 slice, regular" or "1 can (375 ml)".

    The 4th descriptor is usually a brand or example product, so it goes in brackets at the end.
    """
    words = [clean(d) for d in descriptors[:3] if clean(d)]
    text = f"{float(quantity or 1):g} {', '.join(words)}"
    if volume_ml:
        text += f" ({float(volume_ml):g} ml)"
    brand = clean(descriptors[3]) if len(descriptors) > 3 else ""
    if brand:
        text += f" ({brand})"
    return text


def density_portion(grams_per_ml: float, note: str) -> tuple[str, float]:
    """AUSNUT gives a density (grams per ml) for many foods instead of a cup weight. Turn it into a cup."""
    text = f"1 cup ({CUP_ML} ml)" + (f", {note}" if note else "")
    return text, round(grams_per_ml * CUP_ML, 3)


# ---------------------------------------------------------------- reading the Excel files

def sheet_rows(path: Path, sheet: str, first_header: str):
    """All the rows of a sheet below its header row (the one whose first cell is `first_header`).
    The files have a title and blank rows above the real header."""
    ws = openpyxl.load_workbook(path, read_only=True)[sheet]
    rows = ws.iter_rows(values_only=True)
    for row in rows:
        if clean(row[0]) == first_header:
            header = [clean(c) for c in row]
            break
    else:
        raise ValueError(f"no '{first_header}' header row in {path.name}")
    return header, [r for r in rows if r and r[0] is not None]


def adg_details(code, name, flag) -> dict:
    """The dietary guidelines details from one row of the food details file."""
    return {
        "adg_code": int(code) if code not in (None, "") else None,
        "adg_name": clean(name) or None,
        "discretionary": clean(flag).lower() == "discretionary" if clean(flag) else None,
    }


def read_afcd_extras(folder: Path) -> dict[str, dict[str, float]]:
    """{public food key: {"copper": .., "manganese": .., "pantothenic": ..}} for the values AFCD has."""
    header, rows = sheet_rows(folder / AFCD_FILE, "All solids & liquids per 100 g", "Public Food Key")
    columns = {key: next(i for i, h in enumerate(header) if h.startswith(name)) for key, name in AFCD_COLUMNS.items()}
    extras = {}
    for r in rows:
        values = {key: float(r[i]) for key, i in columns.items() if r[i] not in (None, "")}
        if values:
            extras[clean(r[0])] = values
    return extras


def read_portions(folder: Path) -> dict[int, list[tuple[str, float]]]:
    """{survey ID: [(description, grams), ...]}. Density rows become a 1-cup portion, unless the food
    already has a cup measure of its own."""
    header, rows = sheet_rows(folder / MEASURES_FILE, "AUSNUT 2023", "Survey ID")
    col = {name: header.index(name) for name in
           ["Quantity", "Descriptor 1", "Descriptor 2", "Descriptor 3", "Descriptor 4", "Gram amount", "Volume"]}
    portions: dict[int, list[tuple[str, float]]] = {}
    densities: dict[int, list[tuple[float, str]]] = {}
    for r in rows:
        food_id, grams = int(r[0]), r[col["Gram amount"]]
        if not grams or float(grams) <= 0:
            continue
        kind = clean(r[col["Descriptor 1"]])
        if kind == "density":
            densities.setdefault(food_id, []).append((float(grams), clean(r[col["Descriptor 2"]])))
            continue
        descriptors = [r[col[f"Descriptor {n}"]] for n in (1, 2, 3, 4)]
        text = measure_text(r[col["Quantity"]], descriptors, r[col["Volume"]])
        existing = portions.setdefault(food_id, [])
        if text not in [t for t, _ in existing]:
            existing.append((text, round(float(grams), 3)))

    for food_id, rows_for_food in densities.items():
        existing = portions.setdefault(food_id, [])
        if any(text.startswith("1 cup") for text, _ in existing):
            continue
        for grams_per_ml, note in rows_for_food:
            existing.append(density_portion(grams_per_ml, note))
    return portions


def read_foods(folder: Path) -> list[dict]:
    """Read every AUSNUT food, with its nutrients (per 100 g) and portions, ready to be loaded."""
    header, rows = sheet_rows(folder / NUTRIENTS_FILE, "Food nutrient profiles", "Survey ID")
    columns = {key: header.index(name) for key, name in AUSNUT_COLUMNS.items()}
    key_col, name_col = header.index("Public food key"), header.index("Food name")

    # The food group (like "Breads, and bread rolls") is in the details file
    d_header, d_rows = sheet_rows(folder / DETAILS_FILE, "Food details", "Survey ID")
    group_col = d_header.index("2023 Food and dietary supplement classification") + 1   # the name is next to the code
    # FSANZ also tags each food with its Australian Dietary Guidelines food group (a code like 301
    # for "Fresh/canned fruit") and whether it's a "discretionary" (sometimes) food. The recommender
    # uses these so it only suggests everyday foods.
    adg_col = d_header.index("2023 Australian Dietary Guidelines classification")
    flag_col = d_header.index("Discretionary food classification")
    groups, guidelines = {}, {}
    for r in d_rows:
        groups[int(r[0])] = clean(r[group_col]) or None
        guidelines[int(r[0])] = adg_details(r[adg_col], r[adg_col + 1], r[flag_col])

    extras = read_afcd_extras(folder)
    portions = read_portions(folder)

    foods = []
    for r in rows:
        food_id = int(r[0])
        nutrients = {}
        for key, i in columns.items():
            if r[i] in (None, ""):
                continue
            amount = float(r[i]) / KJ_PER_KCAL if key == "energy" else float(r[i])
            unit = usda.NUTRIENTS[key][0]
            if usda.is_plausible(key, unit, amount):
                nutrients[key] = round(amount, 4)
        nutrients.update(extras.get(clean(r[key_col]), {}))
        if "energy" not in nutrients:
            continue
        food_portions = portions.get(food_id, [])
        # The first measure that isn't just a density is the most typical serving
        serving = next((g for text, g in food_portions if not text.startswith("1 cup (")), 100.0)
        food = usda.make_food(food_id, clean(r[name_col]), "ausnut_food", groups.get(food_id),
                              None, nutrients, food_portions, serving)
        food.update(guidelines.get(food_id, {}))
        foods.append(food)
    return foods
