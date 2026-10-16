"""Who's logged in. Served under /api/meals/auth.

Signing up and logging in happen on the website, through Google (Google Cloud Identity Platform).
Google gives the browser a login token, and the website sends it with every request. So there's
no register or login endpoint here; auth.py just checks the token.
"""
from fastapi import APIRouter, Depends

from app import auth, config

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config")
def login_config():
    """What the website needs to show Google's login: the project and its Web API key.

    The website asks for this when it loads, rather than having it built in, so the same website
    build works on any computer or cluster. The key isn't a secret; Google expects it to be public.
    """
    return {
        "api_key": config.GOOGLE_API_KEY,
        "project_id": config.GOOGLE_PROJECT_ID,
        "auth_domain": f"{config.GOOGLE_PROJECT_ID}.firebaseapp.com",   # Google's login pages for the project
    }


@router.get("/me")
def me(claims: dict = Depends(auth.current_claims)):
    """Who am I logged in as? Handy for checking a login token works."""
    return {"user_id": claims["sub"], "email": claims.get("email"), "role": claims["role"]}
