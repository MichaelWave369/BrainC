"""FastAPI dependencies for authentication and rate limiting."""

import time
from collections import defaultdict
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.auth.auth import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

# ── Rate limiting (in-memory, per-IP) ───────────────────────────────────────

_login_attempts: dict[str, dict] = defaultdict(lambda: {"count": 0, "window_start": 0.0})
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_WINDOW = 900  # 15 minutes


def check_login_rate_limit(ip: str) -> None:
    """Raise 429 if the IP has exceeded 5 failed login attempts in 15 minutes."""
    now = time.time()
    record = _login_attempts[ip]
    if now - record["window_start"] > _RATE_LIMIT_WINDOW:
        record["count"] = 0
        record["window_start"] = now
    if record["count"] >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again in 15 minutes.",
        )


def record_failed_login(ip: str) -> None:
    """Increment the failed login counter for an IP."""
    now = time.time()
    record = _login_attempts[ip]
    if now - record["window_start"] > _RATE_LIMIT_WINDOW:
        record["count"] = 0
        record["window_start"] = now
    record["count"] += 1


def clear_login_attempts(ip: str) -> None:
    """Clear the failed login counter on successful authentication."""
    _login_attempts[ip] = {"count": 0, "window_start": 0.0}


# ── Auth dependencies ────────────────────────────────────────────────────────


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """Validate the JWT bearer token and return the current user object.

    Raises 401 if the token is missing, invalid, or expired.
    """
    from api.routes.memory import get_user_by_id

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise credentials_exception
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise credentials_exception
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    user = await get_user_by_id(int(user_id))
    if user is None:
        raise credentials_exception
    return user


async def optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[dict]:
    """Return the current user if a valid token is present, or None otherwise."""
    from api.routes.memory import get_user_by_id

    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None
    user_id = payload.get("sub")
    if user_id is None:
        return None
    return await get_user_by_id(int(user_id))


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that requires the current user to have the 'admin' role."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
