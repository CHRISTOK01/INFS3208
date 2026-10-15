"""Tests that call the API but don't need a database.

We create the TestClient without `with`, so the startup code (which connects to the database)
never runs.
"""
from fastapi.testclient import TestClient

from app.main import app

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
