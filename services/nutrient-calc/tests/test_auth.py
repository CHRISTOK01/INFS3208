"""Tests for checking login tokens. No database or internet needed (see conftest.py)."""
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.auth import check_user_access, decode_token
from tests.conftest import make_service_token, make_user_token


def test_google_token_decodes_as_a_user():
    claims = decode_token(make_user_token("abc123"))
    assert claims["sub"] == "abc123" and claims["role"] == "user"


def test_expired_google_token_is_rejected():
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(make_user_token(expires_in=-10))


def test_google_token_for_another_project_is_rejected():
    with pytest.raises((jwt.InvalidAudienceError, jwt.InvalidIssuerError)):
        decode_token(make_user_token(project="someone-elses-project"))


def test_token_not_signed_by_google_is_rejected():
    impostor_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(make_user_token(key=impostor_key))


def test_service_token_decodes():
    assert decode_token(make_service_token())["role"] == "service"


def test_shared_secret_cannot_be_used_to_pretend_to_be_a_person():
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(make_service_token(sub="abc123", role="user"))


def test_service_token_with_wrong_secret_is_rejected():
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(make_service_token(secret="a-different-secret-that-is-also-32-chars-long"))


def test_user_can_access_own_data():
    check_user_access({"sub": "abc123", "role": "user"}, "abc123")  # should not raise


def test_user_cannot_access_someone_elses_data():
    with pytest.raises(HTTPException) as err:
        check_user_access({"sub": "abc123", "role": "user"}, "someone-else")
    assert err.value.status_code == 403


def test_service_token_can_access_any_user():
    check_user_access({"sub": "meal-logging", "role": "service"}, "abc123")  # should not raise
