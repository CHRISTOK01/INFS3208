"""The gap-analysis API. Everything here is served under /api/gaps (see main.py).

Every endpoint has the user's Google ID in the path, like nutrient-calc. People can only use
their own ID. Our own services (like food-recommender) can ask about anyone.
"""
import logging
from datetime import date, timedelta
from typing import Literal

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection
from pydantic import BaseModel, Field, model_validator

from app import config, gaps, nutrient_client, repo, targets
from app.auth import check_user_access, current_claims
from app.db import get_conn

log = logging.getLogger(config.SERVICE_NAME)
router = APIRouter(tags=["gaps"])

# The report looks at the last 7 days: long enough to see a pattern, short enough to act on this
# week. (Each day on its own is handled by /today.) It's a tuple so more windows can be added.
WINDOWS = (7,)


class Profile(BaseModel):
    """What we ask people when they sign up. Sex is only used to look up the right targets,
    because the NHMRC tables (and the calorie equation) are split into male and female."""
    sex: Literal["male", "female"]
    date_of_birth: date
    height_cm: float = Field(ge=100, le=250)
    weight_kg: float = Field(ge=25, le=350)
    lifestyle: Literal["mostly_seated", "seated_some_walking", "standing_walking", "heavy_work"]
    # sessions of 30-60 minutes of sport or hard exercise
    exercise_sessions_per_week: int = Field(ge=0, le=14)
    goal: Literal["lose", "maintain", "gain"]
    diet: Literal["omnivore", "vegetarian", "vegan"] = "omnivore"
    due_date: date | None = None                     # only if pregnant
    pre_pregnancy_weight_kg: float | None = Field(default=None, ge=25, le=350)
    breastfeeding: bool = False

    @model_validator(mode="after")
    def check_it_makes_sense(self):
        today = date.today()
        if not 14 <= targets.age_on(self.date_of_birth, today) <= 120:
            raise ValueError("MacroScope is for people aged 14 and over (the NHMRC tables we use start at 14)")
        if self.sex == "male" and (self.due_date or self.breastfeeding):
            raise ValueError("pregnancy and breastfeeding targets come from the NHMRC tables for women")
        if self.due_date and not today < self.due_date <= today + timedelta(weeks=42):
            raise ValueError("the due date should be in the next 42 weeks")
        if self.pre_pregnancy_weight_kg and not self.due_date:
            raise ValueError("pre-pregnancy weight is only needed with a due date")
        if (self.due_date or self.breastfeeding) and self.goal != "maintain":
            raise ValueError("we don't set weight loss or gain targets during pregnancy or breastfeeding; "
                             "please talk to your doctor or midwife about that")
        return self


# ---------------------------------------------------------------- helpers

def user_targets(conn: Connection, claims: dict, user_id: str, on: date) -> dict:
    """Check the caller may see this user, then work out the user's targets for the day `on`."""
    check_user_access(claims, user_id)
    profile = repo.get_profile(conn, user_id)
    if profile is None:
        raise HTTPException(404, "No profile yet. Fill in your details first (PUT /api/gaps/profile/{user_id}).")
    return targets.build_targets(profile, repo.get_reference_intakes(conn), on)


def fetch_days(user_id: str, start: date, end: date) -> list[dict]:
    try:
        return nutrient_client.get_days(user_id, start, end)
    except httpx2.HTTPError as exc:
        log.warning("nutrient-calc unavailable: %s", exc)
        raise HTTPException(503, "Can't get your food totals right now (nutrient-calc is unavailable), please retry")


def stale_report(conn: Connection, user_id: str, day: date, target_rows: list[dict]) -> dict:
    """The last saved report, for when nutrient-calc is down. Marked "stale" so the website can say so."""
    rows = repo.get_gap_results(conn, user_id)
    if not rows:
        raise HTTPException(503, "Can't work out your gaps right now (nutrient-calc is unavailable), please retry")
    by_key = {t["nutrient_key"]: t for t in target_rows}
    windows = []
    for size in WINDOWS:
        nutrients = [{**r, "unit": by_key.get(r["nutrient_key"], {}).get("unit"),
                      "upper_limit": by_key.get(r["nutrient_key"], {}).get("upper_limit")}
                     for r in rows if r["window_days"] == size]
        gap_rows = sorted((n for n in nutrients if n["status"] == "gap"), key=lambda n: n["pct_of_target"])
        windows.append({
            "window_days": size,
            "top_gaps": [n["nutrient_key"] for n in gap_rows[:gaps.TOP_GAPS]],
            "excesses": [n["nutrient_key"] for n in nutrients if n["status"] == "excess"],
            "nutrients": nutrients,
        })
    return {"user_id": user_id, "date": day, "stale": True, "computed_at": rows[0]["computed_at"], "windows": windows}


# ---------------------------------------------------------------- profile and targets

@router.get("/profile-options")
def profile_options():
    """The choices for the sign-up form, with a plain description of each lifestyle."""
    return {
        "lifestyle": [{"value": key, "description": text} for key, (_, text) in targets.LIFESTYLES.items()],
        "exercise_sessions_per_week": "How many times a week do you do 30-60 minutes of sport or hard exercise?",
        "goal": ["lose", "maintain", "gain"],
        "diet": ["omnivore", "vegetarian", "vegan"],
    }


@router.put("/profile/{user_id}")
def save_profile(user_id: str, body: Profile, claims: dict = Depends(current_claims), conn: Connection = Depends(get_conn)):
    """Save someone's details, and send back the targets they lead to (for today)."""
    check_user_access(claims, user_id)
    profile = repo.save_profile(conn, user_id, body.model_dump())
    return {"profile": profile, **targets.build_targets(profile, repo.get_reference_intakes(conn), date.today())}


@router.get("/profile/{user_id}")
def get_profile(user_id: str, claims: dict = Depends(current_claims), conn: Connection = Depends(get_conn)):
    check_user_access(claims, user_id)
    profile = repo.get_profile(conn, user_id)
    if profile is None:
        raise HTTPException(404, "No profile yet")
    return profile


@router.get("/targets/{user_id}")
def get_targets(
    user_id: str,
    day: date | None = Query(default=None, alias="date"),
    claims: dict = Depends(current_claims),
    conn: Connection = Depends(get_conn),
):
    """Everything this person should aim for on a day (today if no date is given), where each
    number came from, and a summary of how they were worked out."""
    return user_targets(conn, claims, user_id, day or date.today())


# ---------------------------------------------------------------- comparing food with targets

@router.get("/today/{user_id}")
def today(
    user_id: str,
    day: date = Query(alias="date"),   # ?date=2026-10-16 in the web address
    claims: dict = Depends(current_claims),
    conn: Connection = Depends(get_conn),
):
    """One day's intake against the targets, and how much energy and macros are left.

    The website sends its own date, because "today" depends on where the person is. The
    situation (age, diet, pregnancy and so on) is included for food-recommender.
    """
    worked_out = user_targets(conn, claims, user_id, day)
    days = fetch_days(user_id, day, day)
    result = gaps.today_vs_targets(worked_out["targets"], days[0] if days else None)
    return {"user_id": user_id, "date": day, "situation": worked_out["situation"], **result}


@router.get("/report/{user_id}")
def report(
    user_id: str,
    day: date = Query(alias="date"),   # usually today's date
    claims: dict = Depends(current_claims),
    conn: Connection = Depends(get_conn),
):
    """Gaps and excesses over the last 7 days.

    The window covers the full days BEFORE `day`, so a half-logged today doesn't make it look
    like you're short on everything. If nutrient-calc is down, you get the last saved report,
    marked "stale".
    """
    # The targets as they were on the last day of the windows
    target_rows = user_targets(conn, claims, user_id, day - timedelta(days=1))["targets"]
    try:
        days = nutrient_client.get_days(user_id, day - timedelta(days=max(WINDOWS)), day - timedelta(days=1))
    except httpx2.HTTPError as exc:
        log.warning("nutrient-calc unavailable, sending the last saved report: %s", exc)
        return stale_report(conn, user_id, day, target_rows)

    windows = []
    for size in WINDOWS:
        first_day = (day - timedelta(days=size)).isoformat()
        in_window = [d for d in days if str(d["date"]) >= first_day]   # dates come back as "YYYY-MM-DD"
        windows.append({
            "start": first_day,
            "end": (day - timedelta(days=1)).isoformat(),
            **gaps.analyse(target_rows, in_window, size),
        })
    repo.save_gap_results(conn, user_id, windows)
    return {"user_id": user_id, "date": day, "stale": False, "windows": windows}
