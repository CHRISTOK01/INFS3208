"""Tests that go all the way through to the real nutrient_db database.

They need the database container running, so they're skipped unless INTEGRATION=1 is set:
    docker compose run --rm -e INTEGRATION=1 nutrient-calc pytest -v

They add two made-up foods (with IDs far higher than any real USDA food) and remove them again
at the end, so it's safe to run them even after the real data has been loaded.
"""
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from tests.conftest import make_service_token, make_user_token

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION") != "1", reason="set INTEGRATION=1 to run")

FOOD_A, FOOD_B = 990000001, 990000002   # made-up test foods
USER_ID = "integration-test-user"        # made-up test user
DAY = date(2026, 1, 15)
ENERGY, IRON, VIT_D = 1, 11, 32           # nutrient IDs from db/init.sql


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:   # using `with` runs the startup code, which connects to the database
        db.pool.wait(timeout=10)
        with db.pool.connection() as conn:
            # Clear out anything left over from a previous run or a manual test first
            conn.execute("DELETE FROM food_nutrient WHERE fdc_id IN (%s, %s)", (FOOD_A, FOOD_B))
            conn.execute(
                "INSERT INTO food_nutrient (fdc_id, nutrient_id, amount_per_100g) VALUES "
                "(%s, %s, 200), (%s, %s, 2.0), (%s, %s, 1.5), (%s, %s, 50), (%s, %s, 1.0)",
                (FOOD_A, ENERGY, FOOD_A, IRON, FOOD_A, VIT_D, FOOD_B, ENERGY, FOOD_B, IRON),
            )
        yield c
        with db.pool.connection() as conn:
            conn.execute("DELETE FROM food_nutrient WHERE fdc_id IN (%s, %s)", (FOOD_A, FOOD_B))
            conn.execute("DELETE FROM daily_totals WHERE user_id = %s", (USER_ID,))


def auth(uid=USER_ID):
    """Log in as a (fake) Google user."""
    return {"Authorization": f"Bearer {make_user_token(uid)}"}


def service_auth():
    return {"Authorization": f"Bearer {make_service_token()}"}


def by_key(nutrients):
    return {n["key"]: n for n in nutrients}


def test_ready_when_database_is_up(client):
    assert client.get("/ready").status_code == 200


def test_lists_tracked_nutrients(client):
    keys = [n["key"] for n in client.get("/api/nutrients/nutrients").json()]
    assert keys[0] == "energy" and "magnesium" in keys and "vitamin_d" in keys


def test_food_profile_shows_unknowns_as_null(client):
    profile = by_key(client.get(f"/api/nutrients/foods/{FOOD_B}").json()["per_100g"])
    assert profile["energy"]["amount"] == 50.0
    assert profile["vitamin_d"]["amount"] is None


def test_calculate(client):
    items = [{"fdc_id": FOOD_A, "grams": 150}, {"fdc_id": FOOD_B, "grams": 200}]
    result = client.post("/api/nutrients/calculate", json={"items": items}, headers=auth()).json()
    totals = by_key(result["nutrients"])
    assert totals["energy"]["amount"] == 400.0 and totals["energy"]["is_complete"]
    assert totals["vitamin_d"]["amount"] == 2.25 and not totals["vitamin_d"]["is_complete"]
    assert totals["vitamin_d"]["coverage_pct"] == 42.9   # known for 150 g of the 350 g
    assert result["unknown_foods"] == []


def test_rejects_non_positive_grams(client):
    response = client.post(
        "/api/nutrients/calculate", json={"items": [{"fdc_id": FOOD_A, "grams": 0}]}, headers=auth()
    )
    assert response.status_code == 422


def test_daily_totals_round_trip(client):
    items = [{"fdc_id": FOOD_A, "grams": 100}]
    put = client.put(f"/api/nutrients/daily/{USER_ID}/{DAY}", json={"items": items}, headers=auth())
    assert put.status_code == 200

    # Sending the same day again, now with more food, replaces the totals rather than adding to them
    items.append({"fdc_id": FOOD_B, "grams": 100})
    client.put(f"/api/nutrients/daily/{USER_ID}/{DAY}", json={"items": items}, headers=auth())

    got = client.get(f"/api/nutrients/daily/{USER_ID}?start={DAY}&end={DAY}", headers=auth()).json()
    assert len(got["days"]) == 1
    assert got["days"][0]["nutrients"]["energy"]["amount"] == 250.0
    assert got["days"][0]["item_count"] == 2
    assert got["days"][0]["nutrients"]["energy"]["coverage_pct"] == 100.0


def test_empty_day_removes_totals(client):
    client.put(f"/api/nutrients/daily/{USER_ID}/{DAY}", json={"items": []}, headers=auth())
    got = client.get(f"/api/nutrients/daily/{USER_ID}?start={DAY}&end={DAY}", headers=auth()).json()
    assert got["days"] == []


def test_cannot_read_another_users_totals(client):
    response = client.get(f"/api/nutrients/daily/{USER_ID}?start={DAY}&end={DAY}", headers=auth("someone-else"))
    assert response.status_code == 403


def test_service_token_can_write_for_any_user(client):
    response = client.put(
        f"/api/nutrients/daily/{USER_ID}/{DAY}",
        json={"items": [{"fdc_id": FOOD_A, "grams": 10}]},
        headers=service_auth(),
    )
    assert response.status_code == 200
