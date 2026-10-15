"""Logins: password hashing, and creating and checking login tokens (JWTs).

meal-logging is the only service that creates tokens. It signs them with the shared JWT_SECRET,
and the other services use the same secret to check them.

What's inside a token:
  sub   the user's ID, as a string (e.g. "42")
  exp   when the token expires
  role  "user" for a person, or "service" when one of our own services is calling
        (meal-logging uses a service token when it sends a day's food to nutrient-calc)
"""
import time

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config

bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------- passwords

def hash_password(password: str) -> str:
    """Turn a password into a bcrypt hash. We only ever store the hash, never the password.
    bcrypt adds a random "salt", so the same password gives a different hash each time."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# ---------------------------------------------------------------- tokens

def create_token(sub: str, role: str = "user", seconds: int | None = None) -> str:
    """Make a signed login token. By default it lasts TOKEN_HOURS."""
    if seconds is None:
        seconds = config.TOKEN_HOURS * 3600
    claims = {"sub": sub, "role": role, "exp": int(time.time()) + seconds}
    return jwt.encode(claims, config.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"], options={"require": ["sub", "exp"]})


def current_claims(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """Read the token from the request (FastAPI calls this for us).

    Returns what's inside the token, or replies 401 if there's no token or it isn't valid.
    """
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        return decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


def current_user_id(claims: dict = Depends(current_claims)) -> int:
    """The ID of the person who's logged in. Meals and recipes always belong to this user."""
    if claims.get("role", "user") != "user":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This needs a user login")
    return int(claims["sub"])
