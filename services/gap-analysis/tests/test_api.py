"""Tests that call the API but don't need a database.

We create the TestClient without `with`, so the startup code (which connects to the database)
never runs.
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.routes import Profile

client = TestClient(app)


def test_health_is_ok_and_names_the_pod():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Served-By"]


def test_health_and_version_also_work_under_the_gateway_prefix():
    assert client.get("/api/gaps/health").status_code == 200
    body = client.get("/api/gaps/version").json()
    assert body["service"] == "gap-analysis"
    assert "version" in body and "served_by" in body


def test_ready_reports_503_when_database_is_unavailable():
    response = client.get("/ready")
    assert response.status_code == 503


def test_profile_needs_a_login():
    response = client.get("/api/gaps/profile/someone")
    assert response.status_code == 401


GOOD = {"sex": "female", "date_of_birth": "1996-05-20", "height_cm": 165, "weight_kg": 60,
        "lifestyle": "seated_some_walking", "exercise_sessions_per_week": 2, "goal": "maintain"}


def test_a_normal_profile_is_accepted():
    profile = Profile(**GOOD)
    assert profile.diet == "omnivore" and profile.breastfeeding is False


def test_a_pregnant_profile_is_accepted():
    due = (date.today() + timedelta(weeks=20)).isoformat()
    assert Profile(**{**GOOD, "due_date": due, "pre_pregnancy_weight_kg": 58}).due_date


@pytest.mark.parametrize("bad", [
    {"date_of_birth": (date.today() - timedelta(days=365 * 10)).isoformat()},   # too young
    {"weight_kg": 0},
    {"sex": "unknown"},
    {"goal": "shred"},
    {"lifestyle": "couch"},
    {"exercise_sessions_per_week": 30},
    {"sex": "male", "breastfeeding": True},
    {"due_date": (date.today() - timedelta(days=1)).isoformat()},                 # already passed
    {"due_date": (date.today() + timedelta(weeks=20)).isoformat(), "goal": "lose"},
    {"pre_pregnancy_weight_kg": 58},                                              # no due date
])
def test_profile_rejects_things_that_dont_make_sense(bad):
    with pytest.raises(ValidationError):
        Profile(**{**GOOD, **bad})


def test_profile_options_lists_the_lifestyles():
    body = client.get("/api/gaps/profile-options").json()
    assert [o["value"] for o in body["lifestyle"]][0] == "mostly_seated"
