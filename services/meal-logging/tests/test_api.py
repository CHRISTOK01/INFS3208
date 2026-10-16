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
    assert client.get("/api/meals/health").status_code == 200
    body = client.get("/api/meals/version").json()
    assert body["service"] == "meal-logging"
    assert "version" in body and "served_by" in body


def test_ready_reports_503_when_database_is_unavailable():
    response = client.get("/ready")
    assert response.status_code == 503


def test_login_config_is_public_and_names_the_project():
    from app import config
    body = client.get("/api/meals/auth/config").json()      # no login token needed
    assert body["project_id"] == config.GOOGLE_PROJECT_ID
    assert body["auth_domain"] == f"{config.GOOGLE_PROJECT_ID}.firebaseapp.com"
    assert body["api_key"] == config.GOOGLE_API_KEY
