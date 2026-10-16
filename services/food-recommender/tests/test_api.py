"""Tests that call the API but don't need a database or the other services.

We create the TestClient without `with`, so the startup code (which connects to the database)
never runs.
"""
import httpx2
import pytest
from fastapi.testclient import TestClient

from app import gap_client, repo
from app.db import get_conn
from app.main import app
from tests.conftest import make_service_token, make_user_token

client = TestClient(app)


def test_health_is_ok_and_names_the_pod():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Served-By"]


def test_health_and_version_also_work_under_the_gateway_prefix():
    assert client.get("/api/recommend/health").status_code == 200
    body = client.get("/api/recommend/version").json()
    assert body["service"] == "food-recommender"
    assert "version" in body and "served_by" in body


def test_ready_reports_503_when_database_is_unavailable():
    response = client.get("/ready")
    assert response.status_code == 503


# ---------------------------------------------------------------- /api/recommend/foods, with gap-analysis and the database faked

URL = "/api/recommend/foods/test-user-1?date=2026-10-16"
TODAY = {
    "situation": {"diet": "vegetarian", "life_stage": "none"},
    "remaining": {"energy": 900},
    "nutrients": [
        {"nutrient_key": "iron", "unit": "mg", "amount": 5, "target_amount": 18, "upper_limit": 45},
        {"nutrient_key": "sodium", "unit": "mg", "amount": 800, "target_amount": None, "upper_limit": 2000},
    ],
}
REPORT = {"stale": False, "windows": [{"window_days": 14, "days_logged": 12, "top_gaps": ["iron"], "nutrients": [
    {"nutrient_key": "iron", "unit": "mg", "avg_intake": 10, "target_amount": 18, "status": "gap"}]}]}
FOODS = [
    # A standard serve of lentils is 75 g: 3 mg iron, 90 kcal
    {"fdc_id": 1, "name": "Lentil, brown, boiled", "adg_code": 204, "discretionary": False, "prep_state": "cooked",
     "kcal": 120, "nutrients": {"iron": 4.0}},
    {"fdc_id": 2, "name": "Beef, rump, grilled", "adg_code": 5011, "discretionary": False, "prep_state": "cooked",
     "kcal": 180, "nutrients": {"iron": 3.0}},
]


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(gap_client, "get_today", lambda uid, day: TODAY)
    monkeypatch.setattr(gap_client, "get_report", lambda uid, day: REPORT)
    monkeypatch.setattr(repo, "candidate_foods", lambda conn, keys: FOODS)
    app.dependency_overrides[get_conn] = lambda: None
    yield
    app.dependency_overrides.clear()


def login(uid="test-user-1"):
    return {"Authorization": f"Bearer {make_user_token(uid)}"}


def test_suggestions_need_a_login():
    assert client.get(URL).status_code == 401


def test_people_only_get_their_own_suggestions(fakes):
    assert client.get(URL, headers=login("someone-else")).status_code == 403


def test_suggestions_fill_the_gap_and_respect_the_diet(fakes):
    body = client.get(URL, headers=login()).json()
    assert body["gaps"][0] == {"nutrient_key": "iron", "unit": "mg", "avg_intake": 10, "target_amount": 18, "shortfall": 8}
    assert [s["name"] for s in body["suggestions"]] == ["Lentil, brown, boiled"]     # no beef for a vegetarian
    assert body["suggestions"][0]["why"] == "A standard serve (75 g) gives 3 mg of iron (38% of what you're short each day), for 90 kcal."
    assert any("vegetarian" in note for note in body["notes"])


def test_a_service_can_ask_for_anyone(fakes):
    assert client.get(URL, headers={"Authorization": f"Bearer {make_service_token()}"}).status_code == 200


def test_foods_rich_in_one_nutrient(fakes):
    body = client.get(URL + "&nutrient=iron", headers=login()).json()
    assert body["based_on"] == {"nutrient": "iron"}
    assert body["suggestions"][0]["covers"][0]["pct_of_shortfall"] == 17            # 3 of the 18 mg target
    assert client.get(URL + "&nutrient=sodium", headers=login()).status_code == 400   # a limit, not a target


def test_no_gaps_means_no_suggestions(fakes, monkeypatch):
    monkeypatch.setattr(gap_client, "get_report", lambda uid, day: {"windows": [
        {"window_days": 14, "top_gaps": [], "nutrients": []}]})
    body = client.get(URL, headers=login()).json()
    assert body["suggestions"] == [] and "No gaps" in body["notes"][0]


def test_no_profile_gives_404(fakes, monkeypatch):
    def no_profile(uid, day):
        request = httpx2.Request("GET", "http://gap-analysis")
        raise httpx2.HTTPStatusError("404", request=request, response=httpx2.Response(404, request=request))
    monkeypatch.setattr(gap_client, "get_today", no_profile)
    assert client.get(URL, headers=login()).status_code == 404


def test_gap_analysis_down_gives_503(fakes, monkeypatch):
    def down(uid, day):
        raise httpx2.ConnectError("connection refused")
    monkeypatch.setattr(gap_client, "get_today", down)
    response = client.get(URL, headers=login())
    assert response.status_code == 503 and "gap-analysis" in response.json()["detail"]
