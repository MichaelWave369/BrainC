"""
BrainC rate limiting — v1.0
Uses slowapi (Starlette-compatible) for per-user and per-IP rate limiting.
Admin users are exempt from all limits.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse

from api.core.logging import log_rate_limit_hit


# ── Key function: user_id for authenticated, IP for unauthenticated ───────────


def _rate_limit_key(request: Request) -> str:
    """Use user_id for authenticated requests; fall back to IP address."""
    try:
        user = getattr(request.state, "user", None)
        if user and user.get("role") == "admin":
            # Admins are exempt — use a key that will never be hit
            return "admin-exempt"
        if user:
            return f"user:{user['id']}"
    except AttributeError:
        pass
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key, default_limits=[])


# ── 429 handler ───────────────────────────────────────────────────────────────


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    try:
        user = getattr(request.state, "user", None)
        user_id = user["id"] if user else None
    except Exception:
        user_id = None

    log_rate_limit_hit(
        path=str(request.url.path),
        ip=get_remote_address(request),
        user_id=user_id,
    )

    return JSONResponse(
        status_code=429,
        content={
            "error": "Too many requests — please slow down",
            "detail": str(exc.detail),
        },
        headers={"Retry-After": "60"},
    )
