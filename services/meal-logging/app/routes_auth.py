"""Registering and logging in. Served under /api/meals/auth."""
from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection, errors
from pydantic import BaseModel, Field

from app import auth, repo
from app.db import get_conn

router = APIRouter(prefix="/auth", tags=["auth"])

# A simple "something@something.something" check. Good enough to catch typos.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class Register(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    password: str = Field(min_length=8, max_length=72)  # bcrypt only looks at the first 72 bytes
    display_name: str | None = Field(default=None, max_length=100)


class Login(BaseModel):
    email: str
    password: str


def token_reply(user: dict) -> dict:
    return {
        "token": auth.create_token(str(user["id"])),
        "user": {"id": user["id"], "email": user["email"], "display_name": user["display_name"]},
    }


@router.post("/register", status_code=201)
def register(body: Register, conn: Connection = Depends(get_conn)):
    """Create an account and log straight in. Replies with a login token."""
    if len(body.password.encode()) > 72:
        raise HTTPException(422, "Password is too long")
    try:
        user = repo.create_user(conn, body.email.lower(), auth.hash_password(body.password), body.display_name)
    except errors.UniqueViolation:
        raise HTTPException(409, "That email is already registered")
    return token_reply(user)


@router.post("/login")
def login(body: Login, conn: Connection = Depends(get_conn)):
    """Log in with email and password. Replies with a login token."""
    user = repo.get_user_by_email(conn, body.email.lower())
    # Same message whether the email or the password is wrong, so nobody can use this
    # to find out which emails have accounts
    if user is None or not auth.check_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Wrong email or password")
    return token_reply(user)


@router.get("/me")
def me(user_id: int = Depends(auth.current_user_id), conn: Connection = Depends(get_conn)):
    """Who am I logged in as?"""
    user = repo.get_user(conn, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return user
