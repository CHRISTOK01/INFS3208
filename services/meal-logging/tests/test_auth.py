"""Tests for logins (Google tokens) and service tokens. No database or internet needed (see conftest.py)."""
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import auth
from app.main import app
from tests.conftest import make_service_token, make_user_token

client = TestClient(app)


def test_google_token_decodes_as_a_user():
    claims = auth.decode_token(make_user_token("abc123"))
    assert claims["sub"] == "abc123" and claims["role"] == "user"


def test_tokens_from_another_project_or_not_from_google_are_rejected():
    impostor_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for token in (make_user_token(project="someone-elses-project"), make_user_token(key=impostor_key)):
        with pytest.raises(jwt.PyJWTError):
            auth.decode_token(token)


def test_our_service_tokens_work_but_cannot_pretend_to_be_a_person():
    claims = auth.decode_token(auth.create_service_token())
    assert claims["sub"] == "meal-logging" and claims["role"] == "service"
    with pytest.raises(jwt.InvalidTokenError):
        auth.decode_token(make_service_token(sub="abc123", role="user"))


def test_service_token_cannot_log_meals():
    with pytest.raises(HTTPException) as err:
        auth.current_user_id({"sub": "meal-logging", "role": "service"})
    assert err.value.status_code == 403


def test_me_shows_who_is_logged_in():
    reply = client.get("/api/meals/auth/me", headers={"Authorization": f"Bearer {make_user_token('abc123')}"})
    assert reply.json() == {"user_id": "abc123", "email": "abc123@example.com", "role": "user"}


def test_meals_need_a_login():
    assert client.get("/api/meals/meals?start=2026-01-01").status_code == 401


def test_expired_tokens_are_rejected():
    expired = make_user_token(expires_in=-120)
    response = client.get("/api/meals/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
