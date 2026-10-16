"""Tests that go all the way through: the real gap_db (with the reference intakes loaded) and the
real nutrient-calc. They're skipped unless INTEGRATION=1 is set, and the stack must be running:
    docker compose run --rm -e INTEGRATION=1 gap-analysis pytest -v

They use a made-up user, put a few days of food straight into nutrient-calc (raw spinach plus
enough oil to make it a full day's calories, which leaves magnesium well short), check the report,
and delete everything again at the end.
"""
import os
from datetime import date, timedelta

import httpx2
import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app
from tests.conftest import make_service_token, make_user_token

pytestmark = pytest.mark.skipif(os.getenv("INTEGRATION") != "1", reason="set INTEGRATION=1 to run")

USER = "gap-integration-test-user"
TODAY = date(2001, 3, 15)
LOGGED_DAYS = [TODAY - timedelta(days=n) for n in range(1, 6)]   # the 5 days before "today"
SPINACH = 168462        # "Spinach, raw": 23 kcal and 79 mg magnesium per 100 g
OLIVE_OIL = 171413      # "Oil, olive, salad or cooking": 884 kcal and no magnesium per 100 g
FULL_DAY = [{"fdc_id": SPINACH, "grams": 100}, {"fdc_id": OLIVE_OIL, "grams": 150}]   # about 1350 kcal
# 25 years old on the test's "today" (2001)
PROFILE = {"sex": "female", "date_of_birth": "1976-01-01", "weight_kg": 60, "height_cm": 165,
           "lifestyle": "seated_some_walking", "exercise_sessions_per_week": 0, "goal": "maintain"}


def login():
    return {"Authorization": f"Bearer {make_user_token(USER)}"}


def put_day(day, items):
    """Save a day's food straight into nutrient-calc, the way meal-logging would."""
    response = httpx2.put(
        f"{config.NUTRIENT_CALC_URL}/api/nutrients/daily/{USER}/{day}",
        json={"items": items},
        headers={"Authorization": f"Bearer {make_service_token()}"},
    )
    response.raise_for_status()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        db.pool.wait(timeout=10)
        for day in LOGGED_DAYS:
            put_day(day, FULL_DAY)
        yield c
        for day in LOGGED_DAYS + [TODAY]:
            put_day(day, [])                      # an empty day removes it from nutrient-calc
        with db.pool.connection() as conn:
            conn.execute("DELETE FROM gap_results WHERE user_id = %s", (USER,))
            conn.execute("DELETE FROM user_profiles WHERE user_id = %s", (USER,))


def by_key(rows):
    return {r["nutrient_key"]: r for r in rows}


def test_no_profile_yet_gives_404(client):
    assert client.get(f"/api/gaps/targets/{USER}", headers=login()).status_code == 404


def test_saving_a_profile_works_out_the_targets(client):
    reply = client.put(f"/api/gaps/profile/{USER}", json=PROFILE, headers=login())
    assert reply.status_code == 200
    # The targets for the test's "today", when she was 25
    targets = by_key(client.get(f"/api/gaps/targets/{USER}?date={TODAY}", headers=login()).json()["targets"])
    # BMR 600 + 1031.25 - 125 - 161 = 1345.25, x 1.65 = 2219.7, rounded to 2220 kcal
    assert targets["energy"]["target_amount"] == 2220
    # From the NHMRC table for women aged 19 to 30
    assert targets["magnesium"]["target_amount"] == 310
    assert targets["iodine"]["target_amount"] == 150
    assert "NHMRC" in targets["magnesium"]["source"]
    assert "not yet checked" not in targets["magnesium"]["source"]   # every value has been checked


def test_cannot_see_someone_elses_profile(client):
    other = {"Authorization": f"Bearer {make_user_token('someone-else')}"}
    assert client.get(f"/api/gaps/profile/{USER}", headers=other).status_code == 403


def test_report_finds_the_magnesium_gap(client):
    reply = client.get(f"/api/gaps/report/{USER}?date={TODAY}", headers=login()).json()
    assert reply["stale"] is False
    week, fortnight = reply["windows"]
    assert week["window_days"] == 7 and fortnight["window_days"] == 14
    assert week["days_logged"] == 5
    magnesium = by_key(week["nutrients"])["magnesium"]
    assert magnesium["avg_intake"] == 79 and magnesium["status"] == "gap"
    # Spinach has almost no vitamin B12 or D, so those are the biggest gaps (0% of target)
    assert set(week["top_gaps"][:2]) == {"vitamin_b12", "vitamin_d"}


def test_today_shows_whats_left(client):
    put_day(TODAY, [{"fdc_id": SPINACH, "grams": 200}])     # 46 kcal so far today
    reply = client.get(f"/api/gaps/today/{USER}?date={TODAY}", headers=login()).json()
    assert reply["remaining"]["energy"] == 2220 - 46
    assert by_key(reply["nutrients"])["magnesium"]["amount"] == 158


def test_report_falls_back_to_the_last_one_when_nutrient_calc_is_down(client, monkeypatch):
    monkeypatch.setattr(config, "NUTRIENT_CALC_URL", "http://nutrient-calc:1")   # nothing listens here
    reply = client.get(f"/api/gaps/report/{USER}?date={TODAY}", headers=login())
    assert reply.status_code == 200
    body = reply.json()
    assert body["stale"] is True
    assert by_key(body["windows"][0]["nutrients"])["magnesium"]["status"] == "gap"


def test_today_says_503_when_nutrient_calc_is_down(client, monkeypatch):
    monkeypatch.setattr(config, "NUTRIENT_CALC_URL", "http://nutrient-calc:1")
    assert client.get(f"/api/gaps/today/{USER}?date={TODAY}", headers=login()).status_code == 503
