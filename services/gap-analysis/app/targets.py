"""Working out someone's daily targets from their profile. Plain functions, no database.

Targets are worked out fresh for the date being looked at, because some things change over time:
age (from the date of birth) and the stage of a pregnancy (from the due date).

ENERGY (calories), the method NHMRC uses: resting energy x physical activity level (PAL)
  1. BMR (energy used at rest), from the Mifflin-St Jeor equation. It uses height, weight, age and
     sex, and reviews have found it the most accurate of the common equations for adults
     (Frankenfield et al. 2005, J Am Diet Assoc 105:775).
       men:   10 x weight(kg) + 6.25 x height(cm) - 5 x age + 5
       women: 10 x weight(kg) + 6.25 x height(cm) - 5 x age - 161
     In pregnancy NHMRC uses the weight from before the pregnancy.
  2. PAL from NHMRC's lifestyle table (the middle of each range), plus 0.3 for every 4 to 5
     sessions a week of 30-60 minutes of sport (NHMRC's own adjustment, shared out per session).
     Capped at 2.5, which NHMRC says is hard to keep up for long.
  3. Pregnancy and breastfeeding (NHMRC): 1st trimester nothing extra, 2nd +1.4 MJ a day,
     3rd +1.9 MJ, breastfeeding +2.0 MJ.
  4. Goal: lose = 500 kcal a day less, gain = 250 kcal more. Body fat holds about 7,700 kcal per kg,
     so that's roughly 0.5 kg a week down, or a slow 0.25 kg a week up. Never below BMR. No weight
     loss or gain targets during pregnancy or breastfeeding.

PROTEIN: at least the NHMRC RDI per kg of body weight for the person's age, sex and life stage.
  People who are losing weight, gaining or training regularly need more: 1.6 g/kg when losing or
  gaining (where extra protein stops helping muscle gain, Morton et al. 2018, Br J Sports Med
  52:376) and 1.4 g/kg when training 3+ times a week (the bottom of the 1.4-2.0 g/kg range in the
  ISSN position stand, Jager et al. 2017). Kept within NHMRC's healthy range of 15-25% of energy.
FAT: 30% of energy (NHMRC's healthy range is 20-35%). CARBS: whatever energy is left.
LIMITS: saturated fat under 10% of energy (NHMRC), free sugars under 10% of energy (WHO 2015),
  alcohol (NHMRC 2020 guidelines: adults at most 10 standard drinks of 10 g a week, none under 18
  or when pregnant or breastfeeding), caffeine (FSANZ: 400 mg for adults, 200 mg in pregnancy;
  EFSA 2015: 3 mg per kg for under 18s).
VITAMINS AND MINERALS: the NHMRC RDI or AI for the person's age, sex and life stage (from
  reference_intakes). Vegetarians and vegans absorb less iron and zinc from plants, so NHMRC says
  they need about 80% more iron and up to 50% more zinc.
"""
from datetime import date

KJ_PER_KCAL = 4.184
KCAL_PER_G = {"protein": 4, "carbs": 4, "fat": 9, "alcohol": 7}

# NHMRC's lifestyle table: (PAL, description shown to people)
LIFESTYLES = {
    "mostly_seated":    (1.45, "Seated most of the day, e.g. office work"),
    "seated_some_walking": (1.65, "Mostly seated with some walking and standing, e.g. students, drivers"),
    "standing_walking": (1.85, "Standing or walking most of the day, e.g. retail, hospitality, trades"),
    "heavy_work":       (2.2, "Heavy physical work, e.g. construction, farming"),
}
PAL_PER_EXERCISE_SESSION = 0.3 / 4.5     # NHMRC: add 0.3 for 4-5 sessions a week
MAX_PAL = 2.5

PREGNANCY_EXTRA_KJ = {1: 0, 2: 1400, 3: 1900}
BREASTFEEDING_EXTRA_KJ = 2000
GOAL_KCAL = {"lose": -500, "maintain": 0, "gain": 250}

PROTEIN_G_PER_KG_FOR_GOAL = {"lose": 1.6, "gain": 1.6}
PROTEIN_G_PER_KG_TRAINING = 1.4
TRAINING_SESSIONS = 3
PROTEIN_SHARE = (0.15, 0.25)             # NHMRC acceptable range, as a share of energy
FAT_SHARE = 0.30
SATURATED_FAT_MAX_SHARE = 0.10
FREE_SUGARS_MAX_SHARE = 0.10

ALCOHOL_ADULT_G_PER_DAY = round(10 * 10 / 7, 1)    # 10 standard drinks a week, averaged per day
CAFFEINE_ADULT_MG = 400
CAFFEINE_PREGNANT_MG = 200
CAFFEINE_UNDER_18_MG_PER_KG = 3

VEGETARIAN_FACTORS = {"iron": 1.8, "zinc": 1.5}

# Australian food data has no vitamin K or choline, so we can't track them properly
NOT_TRACKED = {"vitamin_k", "choline"}


# ---------------------------------------------------------------- the person on a given date

def age_on(date_of_birth: date, on: date) -> int:
    had_birthday = (on.month, on.day) >= (date_of_birth.month, date_of_birth.day)
    return on.year - date_of_birth.year - (0 if had_birthday else 1)


def pregnancy_week(due_date: date | None, on: date) -> int | None:
    """Weeks pregnant on `on` (a pregnancy is counted as 40 weeks), or None if not pregnant then."""
    if due_date is None or on >= due_date:
        return None
    return max(0, 40 - (due_date - on).days // 7)


def trimester(week: int) -> int:
    return 1 if week < 14 else 2 if week < 28 else 3


def life_stage(profile: dict, on: date) -> tuple[str, int | None]:
    """("pregnant", week), ("breastfeeding", None) or ("none", None)."""
    week = pregnancy_week(profile.get("due_date"), on)
    if week is not None:
        return "pregnant", week
    if profile.get("breastfeeding"):
        return "breastfeeding", None
    return "none", None


def bmr(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    """Mifflin-St Jeor basal metabolic rate, in kcal per day."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if sex == "male" else base - 161


def activity_level(profile: dict) -> float:
    pal = LIFESTYLES[profile["lifestyle"]][0] + PAL_PER_EXERCISE_SESSION * profile["exercise_sessions_per_week"]
    return round(min(pal, MAX_PAL), 2)


# ---------------------------------------------------------------- the targets

def row(key, amount, unit, source, upper_limit=None, aim=None) -> dict:
    return {"nutrient_key": key, "target_amount": amount, "upper_limit": upper_limit, "aim": aim,
            "unit": unit, "source": source}


def matching_references(references: list[dict], sex: str, age: int, stage: str) -> dict[str, dict]:
    """The NHMRC rows for this person, by nutrient. The pregnancy and breastfeeding tables stop at
    50, so an older mother uses the 31-50 row."""
    age_for_lookup = min(age, 50) if stage != "none" else age
    return {r["nutrient_key"]: r for r in references
            if r["sex"] == sex and r["life_stage"] == stage and r["age_min"] <= age_for_lookup <= r["age_max"]}


def build_targets(profile: dict, references: list[dict], on: date) -> dict:
    """Everyone's targets for the day `on`: energy, macros, limits, vitamins and minerals.

    `references` is every row of reference_intakes. Returns the targets plus a short summary of how
    they were worked out ("situation") and any notes to show the person.
    """
    sex, goal, diet = profile["sex"], profile["goal"], profile["diet"]
    age = age_on(profile["date_of_birth"], on)
    stage, week = life_stage(profile, on)
    notes = []

    # In the 1st trimester the protein needs (and energy) are the same as before pregnancy
    nhmrc = matching_references(references, sex, age, stage)
    if stage == "pregnant" and trimester(week) == 1:
        nhmrc["protein"] = matching_references(references, sex, age, "none")["protein"]

    # ---- energy
    weight_for_bmr = profile["weight_kg"]
    if stage == "pregnant" and profile.get("pre_pregnancy_weight_kg"):
        weight_for_bmr = profile["pre_pregnancy_weight_kg"]
    resting = bmr(sex, weight_for_bmr, profile["height_cm"], age)
    pal = activity_level(profile)
    extra_kj = PREGNANCY_EXTRA_KJ[trimester(week)] if stage == "pregnant" else \
        BREASTFEEDING_EXTRA_KJ if stage == "breastfeeding" else 0
    energy = resting * pal + extra_kj / KJ_PER_KCAL + GOAL_KCAL[goal]
    if energy < resting:
        energy = resting
        notes.append("Your calorie target has been raised to your resting energy needs. Eating less than that isn't recommended.")
    energy = round(energy / 10) * 10

    energy_source = f"Mifflin-St Jeor BMR {resting:.0f} kcal x activity level {pal} (NHMRC method)"
    if extra_kj:
        energy_source += f" + {extra_kj / 1000:g} MJ for {'pregnancy' if stage == 'pregnant' else 'breastfeeding'} (NHMRC)"
    if GOAL_KCAL[goal]:
        energy_source += f" {GOAL_KCAL[goal]:+d} kcal to {goal} weight"

    # ---- protein
    rdi_g_per_kg = float(nhmrc["protein"]["rni_or_ai"])
    g_per_kg, why = rdi_g_per_kg, "NHMRC RDI"
    if goal in PROTEIN_G_PER_KG_FOR_GOAL and PROTEIN_G_PER_KG_FOR_GOAL[goal] > g_per_kg:
        g_per_kg, why = PROTEIN_G_PER_KG_FOR_GOAL[goal], f"to keep or build muscle while you {goal} weight"
    elif profile["exercise_sessions_per_week"] >= TRAINING_SESSIONS and PROTEIN_G_PER_KG_TRAINING > g_per_kg:
        g_per_kg, why = PROTEIN_G_PER_KG_TRAINING, "for regular exercise"
    low, high = (energy * share / KCAL_PER_G["protein"] for share in PROTEIN_SHARE)
    protein = min(max(g_per_kg * profile["weight_kg"], low), high)
    protein = round(max(protein, rdi_g_per_kg * profile["weight_kg"]))
    protein_source = f"{g_per_kg:g} g per kg of body weight ({why}), kept within 15-25% of energy (NHMRC)"

    # ---- fat and carbs
    fat = round(energy * FAT_SHARE / KCAL_PER_G["fat"])
    carbs = max(0, round((energy - protein * KCAL_PER_G["protein"] - fat * KCAL_PER_G["fat"]) / KCAL_PER_G["carbs"]))

    targets = [
        row("energy", energy, "kcal", energy_source),
        row("protein", protein, "g", protein_source),
        row("fat", fat, "g", "30% of energy (NHMRC healthy range is 20-35%)"),
        row("carbs", carbs, "g", "the rest of the energy after protein and fat"),
        row("saturated_fat", None, "g", "less than 10% of energy (NHMRC)",
            upper_limit=round(energy * SATURATED_FAT_MAX_SHARE / KCAL_PER_G["fat"])),
        row("free_sugars", None, "g", "less than 10% of energy (WHO 2015 guideline)",
            upper_limit=round(energy * FREE_SUGARS_MAX_SHARE / KCAL_PER_G["carbs"])),
    ]

    # ---- alcohol and caffeine
    if age < 18 or stage != "none":
        alcohol_limit, why = 0, "NHMRC 2020: no alcohol " + ("under 18" if age < 18 else "when pregnant or breastfeeding")
    else:
        alcohol_limit, why = ALCOHOL_ADULT_G_PER_DAY, "NHMRC 2020: at most 10 standard drinks (10 g each) a week"
    targets.append(row("alcohol", None, "g", why, upper_limit=alcohol_limit))
    if stage == "pregnant":
        caffeine, why = CAFFEINE_PREGNANT_MG, "FSANZ: at most 200 mg a day in pregnancy"
    elif age < 18:
        caffeine, why = round(CAFFEINE_UNDER_18_MG_PER_KG * profile["weight_kg"]), "EFSA 2015: 3 mg per kg of body weight for under 18s"
    else:
        caffeine, why = CAFFEINE_ADULT_MG, "FSANZ: up to 400 mg a day is safe for adults"
    targets.append(row("caffeine", None, "mg", why, upper_limit=caffeine))

    # ---- vitamins, minerals, fibre and omega-3 from the NHMRC tables
    for key, ref in sorted(nhmrc.items()):
        if key == "protein" or key in NOT_TRACKED:
            continue
        amount = float(ref["rni_or_ai"]) if ref["rni_or_ai"] is not None else None
        source = f"NHMRC {ref['intake_type'] or 'value'}" + ("" if stage == "none" else f" for {stage.replace('_', ' ')}")
        upper = float(ref["upper_limit"]) if ref["upper_limit"] is not None else None
        if key in VEGETARIAN_FACTORS and diet in ("vegetarian", "vegan") and amount is not None:
            amount = round(amount * VEGETARIAN_FACTORS[key], 1)
            source += f", x {VEGETARIAN_FACTORS[key]:g} because the body absorbs less from plant foods (NHMRC)"
            if upper is not None and amount > upper:
                # e.g. iron in pregnancy: 27 x 1.8 = 48.6 mg, over the 45 mg upper limit
                amount = upper
                source += ", but no higher than the upper limit"
                notes.append(f"Your {key} needs are higher than food alone usually gives. "
                             "Ask your doctor whether you need a supplement.")
        if key == "sodium":
            source = "NHMRC: no single target; the limit is the UL (14-18) or the 2,000 mg suggested dietary target (adults)"
        targets.append(row(key, amount, ref["unit"], source, upper_limit=upper,
                           aim=float(ref["sdt"]) if ref.get("sdt") is not None else None))

    if diet == "vegan":
        notes.append("Vitamin B12 is only found in animal foods and fortified foods. Most vegans need fortified foods or a supplement.")
    if stage == "pregnant":
        notes.append("NHMRC also recommends a folic acid supplement before and during early pregnancy, and an "
                     "iodine supplement during pregnancy and breastfeeding. Check with your doctor or midwife.")

    carbs_share = 100 * carbs * KCAL_PER_G["carbs"] / energy
    if not 45 <= carbs_share <= 65:
        notes.append(f"Carbs come to {carbs_share:.0f}% of your energy, outside NHMRC's 45-65% range.")

    situation = {
        "age": age,
        "life_stage": stage,
        "pregnancy_week": week,
        "trimester": trimester(week) if week is not None else None,
        "bmr_kcal": round(resting),
        "activity_level": pal,
        "energy_kj": round(energy * KJ_PER_KCAL / 10) * 10,   # Australian labels use kJ
    }
    return {"situation": situation, "targets": targets, "notes": notes}
