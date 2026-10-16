"""Logging meals. Served under /api/meals/meals (you need to be logged in).

After every change, the whole day is sent to nutrient-calc (see sync.py). If nutrient-calc is
down, the meal is still saved and the reply says calc_status "pending".
"""
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection
from pydantic import BaseModel, Field, model_validator

from app import auth, foods, repo, sync
from app.db import get_conn

router = APIRouter(prefix="/meals", tags=["meals"])

MAX_RANGE_DAYS = 92
MAX_GRAMS = 5000


class ItemIn(BaseModel):
    """One food in a meal. Give EITHER grams, OR a portion_id (from GET /foods/{fdc_id}) and how many."""
    fdc_id: int = Field(gt=0)
    grams: float | None = Field(default=None, gt=0, le=MAX_GRAMS)
    portion_id: int | None = None
    quantity: float = Field(default=1, gt=0, le=50)
    state: Literal["raw", "cooked"] | None = None

    @model_validator(mode="after")
    def grams_or_portion(self):
        if (self.grams is None) == (self.portion_id is None):
            raise ValueError("Give either grams or a portion_id, but not both")
        return self


class MealIn(BaseModel):
    meal_date: date
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    items: list[ItemIn] = Field(min_length=1, max_length=50)


class ItemsIn(BaseModel):
    items: list[ItemIn] = Field(min_length=1, max_length=50)


# ---------------------------------------------------------------- helpers

def prepare_items(conn: Connection, items: list[ItemIn]) -> list[dict]:
    """Check the foods exist and turn every item into grams, ready to save.

    If the item doesn't say raw or cooked, we use whatever the food itself says (if anything).
    """
    known_foods = repo.get_foods(conn, [i.fdc_id for i in items])
    portions = repo.get_portions_by_id(conn, [i.portion_id for i in items if i.portion_id is not None])

    prepared = []
    for item in items:
        food = known_foods.get(item.fdc_id)
        if food is None:
            raise HTTPException(404, f"No food with id {item.fdc_id}")

        if item.portion_id is None:
            grams, portion_desc = item.grams, None
        else:
            portion = portions.get(item.portion_id)
            if portion is None or portion["fdc_id"] != item.fdc_id:
                raise HTTPException(422, f"Portion {item.portion_id} doesn't belong to food {item.fdc_id}")
            grams = foods.to_grams(float(portion["gram_weight"]), item.quantity)
            portion_desc = f"{item.quantity:g} x {portion['description']}"
            if grams > MAX_GRAMS:
                raise HTTPException(422, f"That's {grams} g, which is more than the {MAX_GRAMS} g limit")

        prepared.append({
            "fdc_id": item.fdc_id,
            "grams": grams,
            "state": item.state or food["prep_state"],
            "portion_desc": portion_desc,
        })
    return prepared


def commit_and_sync(conn: Connection, user_id: str, day: date) -> bool:
    """Finish a change to a day: put the day on the pending list, save everything, then send
    the day to nutrient-calc. Call repo.lock_day() BEFORE making the change.

    Returns True if nutrient-calc has the new totals, False if the day is still pending.
    """
    repo.mark_day_pending(conn, user_id, day)
    conn.commit()  # the meal is now safely saved, whatever happens with nutrient-calc
    return sync.sync_day(conn, user_id, day)


def meals_reply(conn: Connection, meals: list[dict]) -> list[dict]:
    """Add each meal's items to it. calc_status is 'pending' if any item hasn't been counted yet."""
    items = repo.get_items_for_meals(conn, [m["id"] for m in meals])
    replies = []
    for meal in meals:
        meal_items = [i for i in items if i["meal_id"] == meal["id"]]
        pending = any(i["calc_status"] == "pending" for i in meal_items)
        replies.append({**meal, "calc_status": "pending" if pending else "done", "items": meal_items})
    return replies


def get_own_meal(conn: Connection, user_id: str, meal_id: int) -> dict:
    meal = repo.get_meal(conn, user_id, meal_id)
    if meal is None:
        raise HTTPException(404, f"Meal {meal_id} not found")
    return meal


def save_meal(conn: Connection, user_id: str, meal_date: date, meal_type: str, items: list[dict]) -> dict:
    """Save a new meal and send its day to nutrient-calc. Used by POST /meals and by recipes."""
    repo.lock_day(conn, user_id, meal_date)
    meal_id = repo.create_meal(conn, user_id, meal_date, meal_type)
    repo.add_meal_items(conn, meal_id, items)
    commit_and_sync(conn, user_id, meal_date)
    return meals_reply(conn, [get_own_meal(conn, user_id, meal_id)])[0]


# ---------------------------------------------------------------- endpoints

@router.post("", status_code=201)
def create_meal(body: MealIn, user_id: str = Depends(auth.current_user_id), conn: Connection = Depends(get_conn)):
    """Log a meal. Each item is given in grams, or as a household portion that we turn into grams."""
    items = prepare_items(conn, body.items)
    return save_meal(conn, user_id, body.meal_date, body.meal_type, items)


@router.get("")
def list_meals(
    start: date,
    end: date | None = None,
    user_id: str = Depends(auth.current_user_id),
    conn: Connection = Depends(get_conn),
):
    """Your meals from start to end (or just on start, if there's no end)."""
    end = end or start
    if start > end:
        raise HTTPException(422, "start must be on or before end")
    if end - start >= timedelta(days=MAX_RANGE_DAYS):
        raise HTTPException(422, f"Date range is limited to {MAX_RANGE_DAYS} days")
    return meals_reply(conn, repo.get_meals(conn, user_id, start, end))


@router.post("/recalculate-pending")
def recalculate_pending(claims: dict = Depends(auth.current_claims), conn: Connection = Depends(get_conn)):
    """Send any days that couldn't reach nutrient-calc earlier.

    A user catches up their own days. Our own services (role "service") catch up everyone's.
    """
    user_id = None if claims.get("role") == "service" else claims["sub"]
    return sync.recalculate_pending(conn, user_id)


@router.get("/{meal_id}")
def get_meal(meal_id: int, user_id: str = Depends(auth.current_user_id), conn: Connection = Depends(get_conn)):
    return meals_reply(conn, [get_own_meal(conn, user_id, meal_id)])[0]


@router.post("/{meal_id}/items", status_code=201)
def add_items(
    meal_id: int, body: ItemsIn, user_id: str = Depends(auth.current_user_id), conn: Connection = Depends(get_conn)
):
    """Add more food to a meal you've already logged."""
    meal = get_own_meal(conn, user_id, meal_id)
    items = prepare_items(conn, body.items)
    repo.lock_day(conn, user_id, meal["meal_date"])
    repo.add_meal_items(conn, meal_id, items)
    commit_and_sync(conn, user_id, meal["meal_date"])
    return meals_reply(conn, [meal])[0]


@router.delete("/{meal_id}")
def delete_meal(meal_id: int, user_id: str = Depends(auth.current_user_id), conn: Connection = Depends(get_conn)):
    """Delete a whole meal and everything in it."""
    meal = get_own_meal(conn, user_id, meal_id)
    repo.lock_day(conn, user_id, meal["meal_date"])
    repo.delete_meal(conn, meal_id)
    updated = commit_and_sync(conn, user_id, meal["meal_date"])
    return {"deleted": meal_id, "calc_status": "done" if updated else "pending"}


@router.delete("/{meal_id}/items/{item_id}")
def delete_item(
    meal_id: int, item_id: int, user_id: str = Depends(auth.current_user_id), conn: Connection = Depends(get_conn)
):
    """Take one food out of a meal."""
    meal = get_own_meal(conn, user_id, meal_id)
    repo.lock_day(conn, user_id, meal["meal_date"])
    if not repo.delete_meal_item(conn, meal_id, item_id):
        raise HTTPException(404, f"Item {item_id} isn't in meal {meal_id}")
    commit_and_sync(conn, user_id, meal["meal_date"])
    return meals_reply(conn, [meal])[0]
