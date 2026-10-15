"""The nutrient maths.

These are plain functions with no database involved, which makes them easy to test.

How we handle missing data: if a food has no value for a nutrient, we don't know how much of it
that food adds. We never pretend that's zero. Instead:
  amount        the total of the values we do know (None if we didn't know any of them)
  is_complete   True only if every food had a value
  coverage_pct  how much of the food, by weight, had a value (0 to 100)

Why coverage_pct? Many packaged (Branded) foods only list a few nutrients on the label, so
one muesli bar can make a whole day's magnesium "incomplete". Coverage tells you how much that
matters: if we know the magnesium for 95% of what you ate, the total is close to the truth.
If we only know it for 20%, the total could be far too low.
"""


def scale(amount_per_100g: float, grams: float) -> float:
    """How much of a nutrient is in `grams` of a food, given how much is in 100 g."""
    return amount_per_100g * grams / 100


def sum_nutrients(
    items: list[tuple[int, float]],
    food_values: dict[int, dict[int, float]],
    nutrient_ids: list[int],
) -> dict[int, dict]:
    """Add up each nutrient across a list of (fdc_id, grams) items.

    food_values looks like {fdc_id: {nutrient_id: amount per 100 g}}. If a nutrient is
    missing for a food, that means we don't know it.

    Returns {nutrient_id: {"amount": float or None, "is_complete": bool, "coverage_pct": float or None}}.
    coverage_pct is None when there are no items, because there's nothing to cover.
    """
    total_grams = sum(grams for _, grams in items)
    totals = {}
    for nutrient_id in nutrient_ids:
        amount = 0.0
        known = 0
        known_grams = 0.0
        for fdc_id, grams in items:
            per_100g = food_values.get(fdc_id, {}).get(nutrient_id)
            if per_100g is None:
                continue  # we don't know this one, so leave it out rather than adding 0
            amount += scale(per_100g, grams)
            known += 1
            known_grams += grams

        coverage = round(100 * known_grams / total_grams, 1) if items else None
        if items and known == 0:
            totals[nutrient_id] = {"amount": None, "is_complete": False, "coverage_pct": 0.0}
        else:
            totals[nutrient_id] = {
                "amount": round(amount, 4),
                "is_complete": known == len(items),
                "coverage_pct": coverage,
            }
    return totals
