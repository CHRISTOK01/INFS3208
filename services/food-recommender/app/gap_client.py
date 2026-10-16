"""Calls to the gap-analysis service, to find out what someone is short on and what they have left today."""
from datetime import date
from urllib.parse import quote

import httpx2

from app import auth, config


def get(path: str, user_id: str, day: date) -> dict:
    """GET one of gap-analysis's per-user endpoints, using our own short-lived service token.

    We've already checked the person is allowed to see this user's data. Raises httpx2.HTTPError if
    gap-analysis is down, too slow, or says no (for example 404 when there's no profile yet).
    """
    response = httpx2.get(
        f"{config.GAP_ANALYSIS_URL}/api/gaps/{path}/{quote(user_id, safe='')}",
        params={"date": day.isoformat()},
        headers={"Authorization": f"Bearer {auth.create_service_token()}"},
        timeout=config.GAP_ANALYSIS_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def get_report(user_id: str, day: date) -> dict:
    """Gaps over the 7 and 14 days before `day`."""
    return get("report", user_id, day)


def get_today(user_id: str, day: date) -> dict:
    """What's been eaten on `day`, the targets and limits, energy left, and the person's situation."""
    return get("today", user_id, day)
