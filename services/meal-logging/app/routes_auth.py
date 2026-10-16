"""Who's logged in. Served under /api/meals/auth.

Signing up and logging in happen on the website, through Google (Google Cloud Identity Platform).
Google gives the browser a login token, and the website sends it with every request. So there's
no register or login endpoint here; auth.py just checks the token.
"""
from fastapi import APIRouter, Depends

from app import auth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def me(claims: dict = Depends(auth.current_claims)):
    """Who am I logged in as? Handy for checking a login token works."""
    return {"user_id": claims["sub"], "email": claims.get("email"), "role": claims["role"]}
