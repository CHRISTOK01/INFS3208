import os
import time

import jwt

# This has to be set before the app is imported, because config.py reads it straight away.
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-0123456789")


def make_token(sub: str = "1", role: str = "user", expires_in: int = 3600, secret: str | None = None) -> str:
    """Make a login token the same way meal-logging will."""
    claims = {"sub": sub, "role": role, "exp": int(time.time()) + expires_in}
    return jwt.encode(claims, secret or os.environ["JWT_SECRET"], algorithm="HS256")
