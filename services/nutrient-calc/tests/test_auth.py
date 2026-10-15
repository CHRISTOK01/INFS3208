"""Tests for checking login tokens. No database needed."""
import jwt
import pytest
from fastapi import HTTPException

from app.auth import check_user_access, decode_token
from tests.conftest import make_token


def test_valid_token_decodes():
    assert decode_token(make_token(sub="42"))["sub"] == "42"


def test_expired_token_is_rejected():
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(make_token(expires_in=-10))


def test_token_signed_with_wrong_secret_is_rejected():
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(make_token(secret="a-different-secret-that-is-also-32-chars-long"))


def test_user_can_access_own_data():
    check_user_access({"sub": "42", "role": "user"}, 42)  # should not raise


def test_user_cannot_access_someone_elses_data():
    with pytest.raises(HTTPException) as err:
        check_user_access({"sub": "42", "role": "user"}, 7)
    assert err.value.status_code == 403


def test_service_token_can_access_any_user():
    check_user_access({"sub": "meal-logging", "role": "service"}, 7)  # should not raise
