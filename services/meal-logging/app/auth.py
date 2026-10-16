"""Checking login tokens.

People log in through Google (Google Cloud Identity Platform), on the website. Google checks their
email and password (or their Google account) and gives the browser a signed token, which the
website sends with every request. We check that token here, using Google's public keys. We never
see or store anyone's password.

There's a second kind of token, just for our own services talking to each other (for example,
meal-logging sending a day's food to nutrient-calc). No person is involved there, so we sign those
ourselves with the shared JWT_SECRET.

How we tell them apart: Google signs with RS256 (a private key only Google has), and we sign with
HS256 (our shared secret). An HS256 token only counts if it says role "service", so the shared
secret can never be used to pretend to be a person.

What we get out of a token:
  sub    who it is: the user's Google ID (a string like "Xy7kP2..."), or the service's name
  role   "user" for a person, "service" for one of our services
  email  the person's email (Google tokens only)
"""
import time

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config

bearer = HTTPBearer(auto_error=False)

# Google publishes the public keys for its tokens here. PyJWKClient downloads them the first time
# they're needed and keeps them for an hour, so we don't fetch them on every request.
GOOGLE_KEYS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
google_keys = jwt.PyJWKClient(GOOGLE_KEYS_URL, lifespan=3600, timeout=5)


def decode_google_token(token: str) -> dict:
    """Check a token from Google's login. It must be signed by Google and made for OUR project."""
    key = google_keys.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        key.key,
        algorithms=["RS256"],
        audience=config.GOOGLE_PROJECT_ID,
        issuer=f"https://securetoken.google.com/{config.GOOGLE_PROJECT_ID}",
        options={"require": ["sub", "exp", "iat", "aud", "iss"]},
    )
    return {"sub": claims["sub"], "role": "user", "email": claims.get("email")}


def decode_service_token(token: str) -> dict:
    """Check a token one of our own services made with the shared secret."""
    claims = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"], options={"require": ["sub", "exp"]})
    if claims.get("role") != "service":
        raise jwt.InvalidTokenError("tokens signed with the shared secret are only for our own services")
    return claims


def decode_token(token: str) -> dict:
    algorithm = jwt.get_unverified_header(token).get("alg")
    if algorithm == "RS256":
        return decode_google_token(token)
    if algorithm == "HS256":
        return decode_service_token(token)
    raise jwt.InvalidTokenError(f"unexpected token type {algorithm}")


def create_service_token(seconds: int = 60) -> str:
    """A short-lived token that says "this is one of our services", for calling another service."""
    claims = {"sub": config.SERVICE_NAME, "role": "service", "exp": int(time.time()) + seconds}
    return jwt.encode(claims, config.JWT_SECRET, algorithm="HS256")


def current_claims(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """Read the token from the request (FastAPI calls this for us).

    Returns what's inside the token, or replies 401 if there's no token or it isn't valid.
    """
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        return decode_token(creds.credentials)
    except jwt.PyJWKClientConnectionError:
        # We couldn't download Google's keys, so we can't check anyone's login right now
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Can't check logins right now, please retry")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


def current_user_id(claims: dict = Depends(current_claims)) -> str:
    """The Google ID of the person who's logged in. Their meals, totals and profile are stored under it."""
    if claims.get("role") != "user":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This needs a user login")
    return claims["sub"]


def check_user_access(claims: dict, user_id: str):
    """People can only see and change their own data. Our own services can act for anyone."""
    if claims.get("role") == "service":
        return
    if claims.get("sub") != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only access your own data")
