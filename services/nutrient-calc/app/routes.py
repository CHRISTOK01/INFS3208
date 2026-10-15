"""The nutrient-calc API. Everything here is served under /api/nutrients (see main.py)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from pydantic import BaseModel, Field

from app import calc, repo
from app.auth import check_user_access, current_claims
from app.db import get_conn

router = APIRouter(tags=["nutrients"])

MAX_RANGE_DAYS = 92


class FoodItem(BaseModel):
    fdc_id: int = Field(gt=0)
    grams: float = Field(gt=0, le=5000)


class ItemList(BaseModel):
    items: list[FoodItem] = Field(default_factory=list, max_length=500)


def calculate_items(conn: Connection, items: list[FoodItem]) -> tuple[dict, dict]:
    """Work out the nutrient totals for some food.

    Returns two things: the body we send back to the caller, and the raw totals (by nutrient ID)
    that we save as the day's totals.
    """
    nutrients = repo.get_nutrients(conn)
    food_values = repo.get_food_nutrients(conn, list({i.fdc_id for i in items}))
    totals = calc.sum_nutrients(
        [(i.fdc_id, i.grams) for i in items], food_values, [n["id"] for n in nutrients]
    )
    body = {
        "nutrients": [{**n, **totals[n["id"]]} for n in nutrients],
        # Foods we have no data for at all, so all of their values count as unknown
        "unknown_foods": sorted({i.fdc_id for i in items} - food_values.keys()),
    }
    return body, totals


# ---------------------------------------------------------------- reference data (no login needed)

@router.get("/nutrients")
def list_nutrients(conn: Connection = Depends(get_conn)):
    """List the nutrients MacroScope tracks, with their units."""
    return repo.get_nutrients(conn)


@router.get("/foods/{fdc_id}")
def food_profile(fdc_id: int, conn: Connection = Depends(get_conn)):
    """Show what's in 100 g of one food. An amount of null means we don't know it."""
    values = repo.get_food_nutrients(conn, [fdc_id]).get(fdc_id)
    if values is None:
        raise HTTPException(404, f"No nutrient data for food {fdc_id}")
    return {
        "fdc_id": fdc_id,
        "per_100g": [{**n, "amount": values.get(n["id"])} for n in repo.get_nutrients(conn)],
    }


# ---------------------------------------------------------------- calculations (login needed)

@router.post("/calculate")
def calculate(body: ItemList, claims: dict = Depends(current_claims), conn: Connection = Depends(get_conn)):
    """Add up the nutrients for a list of foods and amounts. Nothing gets saved."""
    result, _ = calculate_items(conn, body.items)
    return result


@router.put("/daily/{user_id}/{day}")
def replace_day(
    user_id: int,
    day: date,
    body: ItemList,
    claims: dict = Depends(current_claims),
    conn: Connection = Depends(get_conn),
):
    """Recalculate one day's totals from everything the user ate that day.

    meal-logging always sends the whole day, not just the meal that was added. That means if this
    call is retried, or replayed later to catch up, the result is still right and nothing is
    counted twice. If the list is empty, nothing is logged for that day any more, so its totals
    are removed.
    """
    check_user_access(claims, user_id)
    result, totals = calculate_items(conn, body.items)
    if body.items:
        repo.upsert_daily_totals(conn, user_id, day, totals, len(body.items))
    else:
        repo.delete_daily_totals(conn, user_id, day)
    return {"user_id": user_id, "date": day, "item_count": len(body.items), **result}


@router.get("/daily/{user_id}")
def get_daily(
    user_id: int,
    start: date,
    end: date,
    claims: dict = Depends(current_claims),
    conn: Connection = Depends(get_conn),
):
    """Get the daily totals between two dates. Days with nothing logged are left out."""
    check_user_access(claims, user_id)
    if start > end:
        raise HTTPException(422, "start must be on or before end")
    if (end - start).days >= MAX_RANGE_DAYS:
        raise HTTPException(422, f"Date range is limited to {MAX_RANGE_DAYS} days")
    return {"user_id": user_id, "start": start, "end": end, "days": repo.get_daily_totals(conn, user_id, start, end)}
