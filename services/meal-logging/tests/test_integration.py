"""Tests that go all the way through: the real meal_db (with the USDA foods loaded), Redis and
nutrient-calc. They're skipped unless INTEGRATION=1 is set, and the stack must be running:
    docker compose run --rm -e INTEGRATION=1 meal-logging pytest -v

They log in as a made-up user with a random Google ID (using the fake Google tokens from
conftest.py), log meals on dates in 2001 so they can't clash with real data, and delete everything
again at the end.
"""
import os
import uuid
from datetime import date

import httpx2
import pytest
from fastapi.testclient import TestClient

from app import auth, config, db
from app.main import app
from tests.conftest import FakeGoogleKeys, make_service_token, make_user_token

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION") != "1", reason="set INTEGRATION=1 to run")

SPINACH, BANANA = 168462, 173944   # real USDA foods: "Spinach, raw" and "Bananas, raw"
DAY = date(2001, 1, 10)
OTHER_DAY = date(2001, 1, 11)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:   # using `with` runs the startup code, which connects to the database
        db.pool.wait(timeout=10)
        yield c


def login_headers(uid: str) -> dict:
    return {"Authorization": f"Bearer {make_user_token(uid)}"}


@pytest.fixture(scope="module")
def user(client):
    """A made-up user. Their meals are deleted after all the tests have run."""
    uid = f"it-{uuid.uuid4().hex[:12]}"
    headers = login_headers(uid)
    yield {"id": uid, "headers": headers}

    # Delete the meals through the API, so nutrient-calc removes those days too. This runs after
    # the last test, when the fake Google keys from conftest.py are already switched off, so we
    # switch them on again just for the clean-up.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(auth, "google_keys", FakeGoogleKeys())
        meals = client.get("/api/meals/meals?start=2001-01-01&end=2001-01-31", headers=headers).json()
        for meal in meals:
            client.delete(f"/api/meals/meals/{meal['id']}", headers=headers)
    with db.pool.connection() as conn:
        conn.execute("DELETE FROM saved_recipes WHERE user_id = %s", (uid,))


def nutrient_calc_day(user, day):
    """Ask nutrient-calc directly for this user's totals on one day.

    The real nutrient-calc can't check our fake Google tokens, so we ask as a service instead."""
    reply = httpx2.get(
        f"{config.NUTRIENT_CALC_URL}/api/nutrients/daily/{user['id']}?start={day}&end={day}",
        headers={"Authorization": f"Bearer {make_service_token()}"},
    ).json()
    return reply["days"][0]["nutrients"] if reply["days"] else None


# ---------------------------------------------------------------- foods

def test_search_puts_generic_foods_first_and_is_cached(client):
    first = client.get("/api/meals/foods/search?q=banana raw&limit=5")
    assert first.status_code == 200
    top = first.json()[0]
    assert top["data_type"] in ("foundation_food", "sr_legacy_food")
    assert "banana" in top["name"].lower() and top["confidence"]

    second = client.get("/api/meals/foods/search?q=banana raw&limit=5")
    assert second.headers["X-Cache"] == "HIT"
    assert second.json() == first.json()


def test_search_surfaces_cooked_foods_when_asked(client):
    results = client.get("/api/meals/foods/search?q=chicken breast&state=cooked").json()
    assert results[0]["prep_state"] == "cooked"


def test_barcode_lookup_ignores_leading_zeros(client):
    with db.pool.connection() as conn:
        food = conn.execute(
            "SELECT fdc_id, barcode FROM food_catalogue WHERE barcode LIKE '00%' LIMIT 1"
        ).fetchone()
    reply = client.get(f"/api/meals/foods/barcode/{food['barcode'].lstrip('0')}")
    assert reply.status_code == 200
    assert reply.json()["fdc_id"] == food["fdc_id"]
    assert reply.json()["confidence"] == "label data only"
    assert client.get("/api/meals/foods/barcode/1").status_code == 404


def test_food_detail_lists_portions(client):
    banana = client.get(f"/api/meals/foods/{BANANA}").json()
    medium = [p for p in banana["portions"] if p["description"].startswith("1 medium")]
    assert medium and float(medium[0]["gram_weight"]) == 118


# ---------------------------------------------------------------- meals

def test_log_meal_with_grams_and_a_portion(client, user):
    banana = client.get(f"/api/meals/foods/{BANANA}").json()
    medium = next(p for p in banana["portions"] if p["description"].startswith("1 medium"))

    reply = client.post("/api/meals/meals", headers=user["headers"], json={
        "meal_date": str(DAY), "meal_type": "breakfast",
        "items": [{"fdc_id": SPINACH, "grams": 100}, {"fdc_id": BANANA, "portion_id": medium["id"]}],
    })
    assert reply.status_code == 201
    meal = reply.json()
    assert meal["calc_status"] == "done"
    assert [float(i["grams"]) for i in meal["items"]] == [100, 118]
    assert meal["items"][1]["state"] == "raw"          # taken from the food, since we didn't say

    # nutrient-calc now has the day: 23 kcal (100 g spinach) + 105.02 kcal (118 g banana)
    totals = nutrient_calc_day(user, DAY)
    assert totals["energy"]["amount"] == pytest.approx(128.02)


def test_meal_is_saved_as_pending_when_nutrient_calc_is_down(client, user, monkeypatch):
    # Point meal-logging at a port where nothing is listening, as if nutrient-calc had crashed.
    # The change only lasts until the end of the `with` block, then nutrient-calc is "back".
    with monkeypatch.context() as patch:
        patch.setattr(config, "NUTRIENT_CALC_URL", "http://nutrient-calc:1")
        reply = client.post("/api/meals/meals", headers=user["headers"], json={
            "meal_date": str(OTHER_DAY), "meal_type": "lunch", "items": [{"fdc_id": SPINACH, "grams": 200}],
        })
    assert reply.status_code == 201                    # the meal is still saved
    assert reply.json()["calc_status"] == "pending"

    assert nutrient_calc_day(user, OTHER_DAY) is None  # it never heard about this day
    caught_up = client.post("/api/meals/meals/recalculate-pending", headers=user["headers"]).json()
    assert caught_up == {"sent": 1, "still_pending": 0}
    assert nutrient_calc_day(user, OTHER_DAY)["energy"]["amount"] == pytest.approx(46)

    meals = client.get(f"/api/meals/meals?start={OTHER_DAY}", headers=user["headers"]).json()
    assert meals[0]["calc_status"] == "done"


def test_add_and_delete_items(client, user):
    meal = client.get(f"/api/meals/meals?start={DAY}", headers=user["headers"]).json()[0]
    added = client.post(f"/api/meals/meals/{meal['id']}/items", headers=user["headers"],
                        json={"items": [{"fdc_id": SPINACH, "grams": 50}]}).json()
    assert len(added["items"]) == 3
    assert nutrient_calc_day(user, DAY)["energy"]["amount"] == pytest.approx(139.52)

    new_item = added["items"][-1]["id"]
    after = client.delete(f"/api/meals/meals/{meal['id']}/items/{new_item}", headers=user["headers"]).json()
    assert len(after["items"]) == 2
    assert nutrient_calc_day(user, DAY)["energy"]["amount"] == pytest.approx(128.02)


def test_people_cannot_see_each_others_meals(client, user):
    meal = client.get(f"/api/meals/meals?start={DAY}", headers=user["headers"]).json()[0]
    stranger = login_headers(f"it-{uuid.uuid4().hex[:12]}")
    assert client.get(f"/api/meals/meals/{meal['id']}", headers=stranger).status_code == 404
    assert client.delete(f"/api/meals/meals/{meal['id']}", headers=stranger).status_code == 404


def test_deleting_the_last_meal_clears_the_day_in_nutrient_calc(client, user):
    meal = client.get(f"/api/meals/meals?start={OTHER_DAY}", headers=user["headers"]).json()[0]
    reply = client.delete(f"/api/meals/meals/{meal['id']}", headers=user["headers"]).json()
    assert reply["calc_status"] == "done"
    assert nutrient_calc_day(user, OTHER_DAY) is None


# ---------------------------------------------------------------- saved recipes

def test_save_and_relog_a_recipe(client, user):
    created = client.post("/api/meals/recipes", headers=user["headers"], json={
        "name": "Green smoothie", "items": [{"fdc_id": SPINACH, "grams": 60}, {"fdc_id": BANANA, "grams": 120}],
    })
    assert created.status_code == 201
    recipe = created.json()
    assert [r["name"] for r in client.get("/api/meals/recipes", headers=user["headers"]).json()] == ["Green smoothie"]

    logged = client.post(f"/api/meals/recipes/{recipe['id']}/log", headers=user["headers"],
                         json={"meal_date": str(OTHER_DAY), "meal_type": "snack"})
    assert logged.status_code == 201
    assert len(logged.json()["items"]) == 2 and logged.json()["calc_status"] == "done"

    assert client.delete(f"/api/meals/recipes/{recipe['id']}", headers=user["headers"]).status_code == 200
    assert client.get("/api/meals/recipes", headers=user["headers"]).json() == []
