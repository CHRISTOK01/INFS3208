"""Shared test helpers: fake Google login tokens, and service tokens.

In real life Google signs login tokens with its own private key, and we check them with Google's
public keys. In the tests we make our own key pair instead, sign "Google-style" tokens with it,
and tell auth.py to use our public key. That way the tests don't need the internet or a real
Google account.
"""
import os
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

# These have to be set before the app is imported, because config.py reads them straight away
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-0123456789")
os.environ.setdefault("GOOGLE_PROJECT_ID", "macroscope-test")
PROJECT = os.environ["GOOGLE_PROJECT_ID"]

TEST_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeGoogleKeys:
    """Stands in for Google's public keys, and always hands back our test key."""
    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=TEST_KEY.public_key())


@pytest.fixture(autouse=True)
def fake_google_keys(monkeypatch):
    from app import auth
    monkeypatch.setattr(auth, "google_keys", FakeGoogleKeys())


def make_user_token(uid: str = "test-user-1", expires_in: int = 3600, project: str = PROJECT, key=TEST_KEY) -> str:
    """A token that looks just like one from Google's login."""
    now = int(time.time())
    claims = {
        "sub": uid,
        "email": f"{uid}@example.com",
        "aud": project,
        "iss": f"https://securetoken.google.com/{project}",
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, key, algorithm="RS256")


def make_service_token(sub: str = "meal-logging", role: str = "service", secret: str | None = None) -> str:
    """A token one of our own services would make with the shared secret."""
    claims = {"sub": sub, "role": role, "exp": int(time.time()) + 60}
    return jwt.encode(claims, secret or os.environ["JWT_SECRET"], algorithm="HS256")
