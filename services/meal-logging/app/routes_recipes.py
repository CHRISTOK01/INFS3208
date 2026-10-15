"""Saved recipes: a named list of foods you can log again in one click.
Served under /api/meals/recipes (you need to be logged in)."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from pydantic import BaseModel, Field

from app import auth, repo
from app.db import get_conn
from app.routes_meals import ItemIn, prepare_items, save_meal

router = APIRouter(prefix="/recipes", tags=["recipes"])


class RecipeIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    items: list[ItemIn] = Field(min_length=1, max_length=50)


class LogRecipe(BaseModel):
    meal_date: date
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]


def recipes_reply(conn: Connection, recipes: list[dict]) -> list[dict]:
    items = repo.get_items_for_recipes(conn, [r["id"] for r in recipes])
    return [{**r, "items": [i for i in items if i["recipe_id"] == r["id"]]} for r in recipes]


def get_own_recipe(conn: Connection, user_id: int, recipe_id: int) -> dict:
    recipe = repo.get_recipe(conn, user_id, recipe_id)
    if recipe is None:
        raise HTTPException(404, f"Recipe {recipe_id} not found")
    return recipe


@router.post("", status_code=201)
def create_recipe(body: RecipeIn, user_id: int = Depends(auth.current_user_id), conn: Connection = Depends(get_conn)):
    """Save a list of foods under a name. Portions are turned into grams, just like for meals."""
    items = prepare_items(conn, body.items)
    recipe_id = repo.create_recipe(conn, user_id, body.name, items)
    return recipes_reply(conn, [get_own_recipe(conn, user_id, recipe_id)])[0]


@router.get("")
def list_recipes(user_id: int = Depends(auth.current_user_id), conn: Connection = Depends(get_conn)):
    return recipes_reply(conn, repo.get_recipes(conn, user_id))


@router.delete("/{recipe_id}")
def delete_recipe(recipe_id: int, user_id: int = Depends(auth.current_user_id), conn: Connection = Depends(get_conn)):
    get_own_recipe(conn, user_id, recipe_id)
    repo.delete_recipe(conn, recipe_id)
    return {"deleted": recipe_id}


@router.post("/{recipe_id}/log", status_code=201)
def log_recipe(
    recipe_id: int, body: LogRecipe, user_id: int = Depends(auth.current_user_id), conn: Connection = Depends(get_conn)
):
    """Log a saved recipe as a new meal on the given day."""
    recipe = recipes_reply(conn, [get_own_recipe(conn, user_id, recipe_id)])[0]
    items = [
        {"fdc_id": i["fdc_id"], "grams": i["grams"], "state": i["state"], "portion_desc": f"from recipe: {recipe['name']}"}
        for i in recipe["items"]
    ]
    return save_meal(conn, user_id, body.meal_date, body.meal_type, items)
