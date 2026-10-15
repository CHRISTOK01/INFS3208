"""Checking login tokens (JWTs).

meal-logging creates the tokens and signs them with the shared JWT_SECRET. Here we just check
that a token is genuine and hasn't expired.

What's inside a token that we care about:
  sub   the user's ID, as a string (e.g. "42")
  exp   when the token expires
  role  "user" for a person, or "service" when one of our own services is calling
        (e.g. meal-logging catching up on meals it couldn't calculate earlier)
"""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config

bearer = HTTPBearer(auto_error=False)


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


def check_user_access(claims: dict, user_id: int):
    """People can only see and change their own data. Our own services can act for anyone."""
    if claims.get("role") == "service":
        return
    if claims.get("sub") != str(user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only access your own data")
