"""Calls to the nutrient-calc service, to get a user's daily totals."""
from datetime import date
from urllib.parse import quote

import httpx2

from app import auth, config


def get_days(user_id: str, start: date, end: date) -> list[dict]:
    """The user's daily totals from start to end (only days with food logged).

    We've already checked the person is allowed to see this user's data, so we ask nutrient-calc
    with our own short-lived service token. Raises httpx2.HTTPError if nutrient-calc is down,
    too slow, or says no.
    """
    response = httpx2.get(
        f"{config.NUTRIENT_CALC_URL}/api/nutrients/daily/{quote(user_id, safe='')}",
        params={"start": start.isoformat(), "end": end.isoformat()},
        headers={"Authorization": f"Bearer {auth.create_service_token()}"},
        timeout=config.NUTRIENT_CALC_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["days"]
