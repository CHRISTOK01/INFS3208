"""Finding foods: search, barcode lookup, and a food's portions. Served under /api/meals/foods.

No login is needed here, because the food list is public data (FSANZ and USDA).
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg import Connection

from app import cache, config, foods, repo
from app.db import get_conn

router = APIRouter(prefix="/foods", tags=["foods"])


def food_reply(food: dict) -> dict:
    """A food as we send it back, with its data-confidence label added."""
    return {**food, "confidence": foods.confidence_label(food["data_type"], food["has_full_micros"])}


@router.get("/search")
def search(
    response: Response,
    q: str = Query(min_length=2, max_length=100),
    state: Literal["raw", "cooked"] | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    conn: Connection = Depends(get_conn),
):
    """Search foods by name. If you say raw or cooked (as `state`, or in the search, like "rice
    boiled"), foods that match come first.

    Results are cached in Redis. The X-Cache header says whether this answer came from the
    cache (HIT) or the database (MISS).
    """
    wanted = foods.understand_search(q, state)
    if not wanted.words:
        raise HTTPException(422, "Search for at least one word of 2 or more letters")

    key = f"search:{' '.join(q.lower().split())}:{wanted.state}:{limit}"
    results = cache.get_json(key)
    if results is not None:
        response.headers["X-Cache"] = "HIT"
        return results

    results = [food_reply(f) for f in repo.search_foods(conn, wanted, limit, q.lower())]
    cache.set_json(key, results, config.SEARCH_CACHE_SECONDS)
    response.headers["X-Cache"] = "MISS"
    return results


@router.get("/barcode/{code}")
def by_barcode(code: str, conn: Connection = Depends(get_conn)):
    """Look up a packaged food by its barcode, with or without leading zeros."""
    normalised = foods.normalise_barcode(code)
    if not normalised.isdigit():
        raise HTTPException(422, "A barcode should only contain digits")
    food = repo.get_food_by_barcode(conn, normalised)
    if food is None:
        raise HTTPException(404, f"No food found with barcode {code}")
    return food_reply(food)


@router.get("/{fdc_id}")
def food_detail(fdc_id: int, conn: Connection = Depends(get_conn)):
    """One food, with its household portions (like "1 cup = 30 g") for turning into grams."""
    food = repo.get_food(conn, fdc_id)
    if food is None:
        raise HTTPException(404, f"No food with id {fdc_id}")
    return {**food_reply(food), "portions": repo.get_portions(conn, fdc_id)}
