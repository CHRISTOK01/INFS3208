"""The food-recommender API, served under /api/recommend (see main.py)."""
import logging
from datetime import date
from typing import Literal

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from app import config, gap_client, repo, rules
from app.auth import check_user_access, current_claims
from app.db import get_conn

log = logging.getLogger(config.SERVICE_NAME)
router = APIRouter(tags=["recommend"])


def ask_gap_analysis(call, user_id: str, day: date) -> dict:
    """Call gap-analysis, turning its errors into ones that make sense to the person."""
    try:
        return call(user_id, day)
    except httpx2.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(404, "No profile yet. Fill in your details first, then we can suggest foods.")
        log.warning("gap-analysis said %s", exc.response.status_code)
        # Pass on gap-analysis's own explanation if it gave one (like "nutrient-calc is unavailable")
        try:
            detail = exc.response.json()["detail"]
        except (ValueError, KeyError, TypeError):
            detail = "Can't work out your gaps right now (gap-analysis had a problem), please retry"
        raise HTTPException(503, detail)
    except httpx2.HTTPError as exc:
        log.warning("gap-analysis unavailable: %s", exc)
        raise HTTPException(503, "Can't work out your gaps right now (gap-analysis is unavailable), please retry")


@router.get("/foods/{user_id}")
def suggest_foods(
    user_id: str,
    day: date = Query(alias="date"),        # ?date=2026-10-16, the person's own today
    period: Literal["today", "week"] = "today",
    nutrient: str | None = Query(default=None, description="just find foods rich in this one, e.g. iron"),
    limit: int = Query(default=8, ge=1, le=20),
    claims: dict = Depends(current_claims),
    conn: Connection = Depends(get_conn),
):
    """Foods that fit what this person has left today, each with a plain explanation.

    period=today (the default): foods that fill the most of what's still needed to reach today's
    targets. period=week: foods for what they've been short on over the last 7 days. With
    ?nutrient=iron it finds good sources of iron instead (the "shortfall" is the whole daily target).
    """
    check_user_access(claims, user_id)
    today = ask_gap_analysis(gap_client.get_today, user_id, day)
    targets = {n["nutrient_key"]: n for n in today["nutrients"]}
    units = {key: n["unit"] for key, n in targets.items()}

    if nutrient:
        target = targets.get(nutrient, {}).get("target_amount")
        if not target:
            raise HTTPException(400, f"{nutrient} has no daily target to aim for, so we can't suggest foods for it")
        shortfalls, gaps, based_on = {nutrient: target}, [], {"nutrient": nutrient}
        of_what = "of your daily target"
    elif period == "today":
        shortfalls, gaps = rules.shortfalls_for_today(today["nutrients"])
        based_on = {"period": "today"}
        of_what = "of what you still need today"
    else:
        report = ask_gap_analysis(gap_client.get_report, user_id, day)
        shortfalls, window, gaps = rules.shortfalls_from_report(report)
        based_on = {"period": "week", "window_days": window["window_days"], "days_logged": window.get("days_logged"),
                    "stale": report.get("stale", False)}
        of_what = "of what you're short each day"

    energy_left = today["remaining"].get("energy")
    result = {"user_id": user_id, "date": day, "based_on": based_on, "gaps": gaps,
              "energy_left_kcal": energy_left, "suggestions": [], "notes": []}
    if not shortfalls:
        result["notes"].append(
            "You've reached every target for today. Nice work!" if based_on.get("period") == "today"
            else "No gaps in the last 7 days, so there's nothing to catch up on. "
                 "Gaps need at least 3 days of logging to show up.")
        return result

    foods = repo.candidate_foods(conn, list(shortfalls))
    result["suggestions"] = rules.recommend(foods, shortfalls, units, today["situation"], targets, energy_left, limit, of_what)
    result["notes"] = notes_for(today["situation"], shortfalls)
    if not result["suggestions"]:
        reason = rules.why_nothing_fits(foods, today["situation"], targets, energy_left)
        result["notes"].insert(0, reason or "No everyday foods have enough of this to suggest.")
    return result


def notes_for(situation: dict, shortfalls: dict) -> list[str]:
    notes = ["Suggestions are everyday Australian foods (FSANZ AUSNUT 2023) from the five food groups."]
    if situation.get("diet") in ("vegetarian", "vegan"):
        notes.append(f"Foods your {situation['diet']} diet leaves out aren't suggested.")
    if situation.get("life_stage") == "pregnant":
        notes.append("Foods FSANZ advises avoiding in pregnancy (because of listeria or mercury) aren't suggested.")
    partial = [rules.nice_name(k) for k in shortfalls if k in ("copper", "manganese", "pantothenic")]
    if partial:
        notes.append(f"Only some Australian foods have a value for {', '.join(partial)}, so good sources may be missing.")
    return notes
