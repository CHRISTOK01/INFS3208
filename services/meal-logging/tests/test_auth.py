"""Tests for passwords and login tokens. No database needed."""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import auth
from app.main import app
from tests.conftest import make_token

client = TestClient(app)


def test_password_hash_checks_out():
    hashed = auth.hash_password("correct horse battery")
    assert hashed != "correct horse battery"               # we never store the password itself
    assert auth.check_password("correct horse battery", hashed)
    assert not auth.check_password("wrong password", hashed)


def test_same_password_gives_different_hashes():
    assert auth.hash_password("samepassword") != auth.hash_password("samepassword")


def test_token_round_trip():
    claims = auth.decode_token(auth.create_token("42"))
    assert claims["sub"] == "42" and claims["role"] == "user"


def test_service_token_is_not_a_user_login():
    with pytest.raises(HTTPException) as err:
        auth.current_user_id({"sub": "meal-logging", "role": "service"})
    assert err.value.status_code == 403


def test_meals_need_a_login():
    assert client.get("/api/meals/meals?start=2026-01-01").status_code == 401


def test_expired_or_forged_tokens_are_rejected():
    expired = make_token(expires_in=-10)
    forged = make_token(secret="some-other-secret-that-is-long-enough-000")
    for token in (expired, forged):
        response = client.get("/api/meals/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
