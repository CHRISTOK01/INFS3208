"""Calls to the nutrient-calc service.

We always send a WHOLE day's food, not just the meal that changed. nutrient-calc recalculates
the day from scratch, so sending the same day twice gives the same result and nothing is ever
counted twice.
"""
from datetime import date
from urllib.parse import quote

import httpx2

from app import auth, config


def send_day(user_id: str, day: date, items: list[dict]):
    """Send one user's food for one day to nutrient-calc.

    items is a list of {"fdc_id": ..., "grams": ...}. An empty list tells nutrient-calc the day
    has no food any more. Raises httpx2.HTTPError if nutrient-calc is down, too slow, or says no.
    """
    # A short-lived token that says "this is meal-logging", so nutrient-calc lets us
    # update any user's totals
    token = auth.create_service_token()
    response = httpx2.put(
        # quote() makes sure the user's ID is safe to put in a web address
        f"{config.NUTRIENT_CALC_URL}/api/nutrients/daily/{quote(user_id, safe='')}/{day.isoformat()}",
        json={"items": [{"fdc_id": i["fdc_id"], "grams": float(i["grams"])} for i in items]},
        headers={"Authorization": f"Bearer {token}"},
        timeout=config.NUTRIENT_CALC_TIMEOUT,
    )
    response.raise_for_status()  # turns a 4xx or 5xx reply into an error
