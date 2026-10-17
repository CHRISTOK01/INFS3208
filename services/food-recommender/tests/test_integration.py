"""Tests that go all the way through: the real recommender_db (with the food data loaded), the real
gap-analysis and the real nutrient-calc. They're skipped unless INTEGRATION=1 is set, and the stack
must be running:
    docker compose run --rm -e INTEGRATION=1 food-recommender pytest -v

They use a made-up user who has eaten nothing but spinach and olive oil for 5 days, which leaves
big gaps (vitamin B12, vitamin D and more). Their food days are removed at the end. Their profile
stays in gap_db, because only gap-analysis can delete it, and the next run just overwrites it.
"""
import os
from datetime import date, timedelta

import httpx2
import pytest
from fastapi.testclient import TestClient

from app import config, db, rules
from app.main import app
from tests.conftest import make_service_token, make_user_token

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION") != "1", reason="set INTEGRATION=1 to run")

NUTRIENT_CALC_URL = os.getenv("NUTRIENT_CALC_URL", "http://nutrient-calc:8002")
USER = "recommender-integration-test-user"
TODAY = date(2001, 3, 15)
LOGGED_DAYS = [TODAY - timedelta(days=n) for n in range(1, 6)]   # the 5 days before "today"
SPINACH = 168462        # USDA "Spinach, raw"
OLIVE_OIL = 171413      # USDA "Oil, olive, salad or cooking"
FULL_DAY = [{"fdc_id": SPINACH, "grams": 100}, {"fdc_id": OLIVE_OIL, "grams": 150}]
PROFILE = {"sex": "female", "date_of_birth": "1976-01-01", "weight_kg": 60, "height_cm": 165,
           "lifestyle": "seated_some_walking", "exercise_sessions_per_week": 0, "goal": "maintain"}
SERVICE = {"Authorization": f"Bearer {make_service_token()}"}
URL = f"/api/recommend/foods/{USER}?date={TODAY}"


def login():
    return {"Authorization": f"Bearer {make_user_token(USER)}"}


def put_day(day, items):
    """Save a day's food straight into nutrient-calc, the way meal-logging would."""
    httpx2.put(f"{NUTRIENT_CALC_URL}/api/nutrients/daily/{USER}/{day}", json={"items": items},
               headers=SERVICE).raise_for_status()


def save_profile(diet):
    httpx2.put(f"{config.GAP_ANALYSIS_URL}/api/gaps/profile/{USER}", json={**PROFILE, "diet": diet},
               headers=SERVICE).raise_for_status()


def adg_codes(ids):
    with db.pool.connection() as conn:
        rows = conn.execute("SELECT fdc_id, adg_code, discretionary FROM foods WHERE fdc_id = ANY(%s)", (ids,)).fetchall()
    return {r["fdc_id"]: r for r in rows}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        db.pool.wait(timeout=10)
        save_profile("omnivore")
        for day in LOGGED_DAYS:
            put_day(day, FULL_DAY)
        yield c
        for day in LOGGED_DAYS:
            put_day(day, [])                      # an empty day removes it from nutrient-calc


def test_suggests_everyday_foods_for_the_gaps(client):
    body = client.get(URL + "&period=week", headers=login()).json()
    assert body["based_on"]["window_days"] == 7 and body["based_on"]["days_logged"] == 5
    gap_keys = {g["nutrient_key"] for g in body["gaps"]}
    assert {"vitamin_b12", "vitamin_d"} <= gap_keys
    suggestions = body["suggestions"]
    assert 1 <= len(suggestions) <= 8
    rows = adg_codes([s["fdc_id"] for s in suggestions])
    for s in suggestions:
        assert rules.food_group(rows[s["fdc_id"]]["adg_code"]) is not None    # one of the five groups
        assert rows[s["fdc_id"]]["discretionary"] is False
        assert s["covers"][0]["nutrient_key"] in gap_keys
        assert s["why"].endswith("kcal.")
    # Best first
    assert [s["score"] for s in suggestions] == sorted((s["score"] for s in suggestions), reverse=True)


def test_vegan_suggestions_have_no_animal_foods(client):
    save_profile("vegan")
    try:
        suggestions = client.get(URL, headers=login()).json()["suggestions"]
    finally:
        save_profile("omnivore")
    assert suggestions
    rows = adg_codes([s["fdc_id"] for s in suggestions])
    assert all(rules.animal_source(rows[s["fdc_id"]]["adg_code"]) is None for s in suggestions)


def test_foods_rich_in_one_nutrient(client):
    body = client.get(URL + "&nutrient=iron", headers=login()).json()
    assert body["suggestions"]
    assert all(s["covers"][0]["nutrient_key"] == "iron" for s in body["suggestions"])


def test_someone_else_cant_ask(client):
    other = {"Authorization": f"Bearer {make_user_token('someone-else')}"}
    assert client.get(URL, headers=other).status_code == 403


def test_says_503_when_gap_analysis_is_down(client, monkeypatch):
    monkeypatch.setattr(config, "GAP_ANALYSIS_URL", "http://gap-analysis:1")   # nothing listens here
    assert client.get(URL, headers=login()).status_code == 503
