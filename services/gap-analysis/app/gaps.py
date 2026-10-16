"""Finding gaps: comparing what someone ate over the last 7 or 14 days with their targets.
Plain functions, no database, so they're easy to test.

The rules:
  - Fibre, vitamins, minerals and omega-3 are checked against their targets, and things with only
    a limit (sodium, saturated fat, free sugars, alcohol, caffeine) against that limit. Calories and
    macros are a daily budget (see today_vs_targets), not something you're "short" on over a fortnight.
  - Every day with food logged counts. Days with nothing logged don't, because not logging isn't
    the same as not eating.
  - We need at least 3 days with data for a nutrient. With fewer, it's "unknown".
  - Some foods don't have a value for every nutrient. A day where we know a nutrient for at least
    80% of the food (by weight) gives a real total for that day. On other days, the total only
    covers some of the food, so the real amount is at least that much, maybe more.
  - "gap"     the average is below 70% of the target. NHMRC targets are set high enough to cover
              nearly everyone, so being a little under isn't a worry. Well under, day after day, is.
  - "excess"  the average is above the upper limit, where there is one.
  - "ok"      anything else. Also "ok" when we only have partial totals but they already reach 70%
              of the target: the foods we're missing values for can only add to that.
  - "unknown" not enough data to say, or no target and no upper limit to compare with.
"""
MACRO_KEYS = {"energy", "protein", "carbs", "fat"}
MIN_COVERAGE_PCT = 80
MIN_DAYS = 3
GAP_BELOW_PCT = 70
TOP_GAPS = 5


def day_amounts(days: list[dict], key: str) -> tuple[list[float], list[float]]:
    """The nutrient's daily totals, split in two.

    full      days where we know it for at least 80% of the food, so the total is close to real
    at_least  every day where we know it for some of the food (the total is a minimum)
    """
    full, at_least = [], []
    for day in days:
        value = day["nutrients"].get(key)
        if value is None or value["amount"] is None:
            continue
        at_least.append(value["amount"])
        if value["coverage_pct"] >= MIN_COVERAGE_PCT:
            full.append(value["amount"])
    return full, at_least


def check_nutrient(target: dict, days: list[dict]) -> dict:
    """Work out one nutrient's average, how many days met the target, and its status."""
    key, unit = target["nutrient_key"], target["unit"]
    goal, limit = target["target_amount"], target["upper_limit"]
    full, at_least = day_amounts(days, key)

    # Use the real totals if there are enough of them. If not, use the partial ones as a minimum.
    is_minimum = len(full) < MIN_DAYS
    amounts = at_least if is_minimum else full

    result = {
        "nutrient_key": key,
        "unit": unit,
        "target_amount": goal,
        "upper_limit": limit,
        "days_with_data": len(amounts),
        "avg_intake": None,
        "pct_of_target": None,
        "is_minimum": is_minimum,   # true when the average only counts some of the food
        "days_met": 0,
    }
    if len(amounts) < MIN_DAYS:
        return {**result, "status": "unknown",
                "reason": f"only {len(amounts)} day(s) with data, need {MIN_DAYS}"}

    avg = sum(amounts) / len(amounts)
    result["avg_intake"] = round(avg, 2)
    if goal:
        result["pct_of_target"] = round(100 * avg / goal, 1)
        result["days_met"] = sum(1 for a in amounts if a >= goal)

    if limit is not None and avg > limit:
        reason = "the advice is to have none" if limit == 0 else f"average is above the upper limit of {limit:g} {unit}"
        return {**result, "status": "excess", "reason": reason}
    if not goal:
        if limit is not None and not is_minimum:
            return {**result, "status": "ok", "reason": None}
        return {**result, "status": "unknown", "reason": "no target to compare with"}
    if result["pct_of_target"] >= GAP_BELOW_PCT:
        return {**result, "status": "ok", "reason": None}
    if is_minimum:
        # Below 70%, but some foods had no value for this nutrient, so the real amount may be higher
        return {**result, "status": "unknown",
                "reason": "some of the food logged has no value for this nutrient, so we can't tell"}
    return {**result, "status": "gap", "reason": f"average is under {GAP_BELOW_PCT}% of the target"}


def analyse(targets: list[dict], days: list[dict], window_days: int) -> dict:
    """Check every nutrient over one window. `days` should only hold the days inside the window."""
    nutrients = [
        check_nutrient(t, days)
        for t in targets
        if t["nutrient_key"] not in MACRO_KEYS
    ]
    gaps = sorted((n for n in nutrients if n["status"] == "gap"), key=lambda n: n["pct_of_target"])
    return {
        "window_days": window_days,
        "days_logged": len(days),
        "top_gaps": [n["nutrient_key"] for n in gaps[:TOP_GAPS]],   # the biggest gaps first
        "excesses": [n["nutrient_key"] for n in nutrients if n["status"] == "excess"],
        "nutrients": nutrients,
    }


def today_vs_targets(targets: list[dict], day: dict | None) -> dict:
    """One day's intake against every target, plus how much energy and macros are left.

    `day` is that day's totals from nutrient-calc, or None if nothing has been logged yet.
    """
    rows = []
    remaining = {}
    for t in targets:
        key, goal = t["nutrient_key"], t["target_amount"]
        value = day["nutrients"].get(key) if day else None
        amount = value["amount"] if value else None
        rows.append({
            "nutrient_key": key,
            "unit": t["unit"],
            "amount": amount,
            "target_amount": goal,
            "upper_limit": t["upper_limit"],
            "pct_of_target": round(100 * amount / goal, 1) if amount is not None and goal else None,
            "coverage_pct": value["coverage_pct"] if value else None,
        })
        if key in MACRO_KEYS and goal is not None:
            remaining[key] = round(max(0, goal - (amount or 0)), 1)
    return {"nutrients": rows, "remaining": remaining}
