"""Authentication routes — register, login, refresh, logout, me."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from api.auth.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from api.auth.middleware import (
    check_login_rate_limit,
    clear_login_attempts,
    get_current_user,
    record_failed_login,
    require_admin,
)
from api.config import ALLOW_REGISTRATION, MAX_SESSIONS_PER_USER, REFRESH_TOKEN_EXPIRE_DAYS
from api.routes.memory import (
    count_users,
    create_session,
    create_user,
    delete_all_refresh_tokens_for_user,
    delete_refresh_token,
    delete_user,
    get_refresh_token,
    get_user_by_id,
    get_user_by_username,
    get_user_conversation_count,
    list_sessions_for_user,
    list_users,
    prune_expired_sessions,
    save_refresh_token,
    update_user_last_login,
    update_user_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Pydantic request/response models ─────────────────────────────────────────


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8)
    display_name: str = Field(..., min_length=1, max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8)


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8)
    display_name: str = Field(..., min_length=1, max_length=64)
    role: str = Field(default="user")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _issue_tokens(user_id: int, request: Request) -> dict:
    """Create access + refresh tokens, record session, and return token payload."""
    await prune_expired_sessions()

    # Enforce max sessions per user
    active = await list_sessions_for_user(user_id)
    if len(active) >= MAX_SESSIONS_PER_USER:
        oldest = sorted(active, key=lambda s: s["created_at"])[0]
        from api.routes.memory import delete_session
        await delete_session(oldest["session_id"])

    import secrets as _secrets
    session_id = _secrets.token_urlsafe(24)

    ip = _get_client_ip(request)
    ua = request.headers.get("User-Agent", "")
    await create_session(session_id, user_id, ip, ua)

    access_token = create_access_token({"sub": str(user_id), "sid": session_id})
    refresh_token = create_refresh_token()

    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    await save_refresh_token(refresh_token, user_id, expires_at.isoformat())
    await update_user_last_login(user_id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request):
    """Create a new user account. The first registered user is automatically admin."""
    if not ALLOW_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled",
        )

    existing = await get_user_by_username(body.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    total = await count_users()
    role = "admin" if total == 0 else "user"
    password_hash = hash_password(body.password)
    user_id = await create_user(body.username, password_hash, body.display_name, role)

    tokens = await _issue_tokens(user_id, request)
    return {
        "user": {
            "id": user_id,
            "username": body.username,
            "display_name": body.display_name,
            "role": role,
        },
        **tokens,
    }


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    """Authenticate with username + password, returns access_token + refresh_token."""
    ip = _get_client_ip(request)
    check_login_rate_limit(ip)

    user = await get_user_by_username(body.username)
    if not user or not verify_password(body.password, user["password_hash"]):
        record_failed_login(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    clear_login_attempts(ip)
    tokens = await _issue_tokens(user["id"], request)
    return {
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
        },
        **tokens,
    }


@router.post("/refresh")
async def refresh_token(body: RefreshRequest, request: Request):
    """Exchange a valid refresh token for a new access token."""
    stored = await get_refresh_token(body.refresh_token)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    expires_at = datetime.fromisoformat(stored["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        await delete_refresh_token(body.refresh_token)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )

    await delete_refresh_token(body.refresh_token)
    tokens = await _issue_tokens(stored["user_id"], request)
    return tokens


@router.post("/logout")
async def logout(body: RefreshRequest, user: dict = Depends(get_current_user)):
    """Invalidate the provided refresh token."""
    await delete_refresh_token(body.refresh_token)
    return {"success": True, "message": "Logged out"}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """Return the current user's profile."""
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "created_at": user["created_at"],
        "last_login": user["last_login"],
    }


# ── Admin routes ──────────────────────────────────────────────────────────────


@router.get("/users")
async def list_all_users(_admin: dict = Depends(require_admin)):
    """List all users with metadata (admin only)."""
    users = await list_users()
    result = []
    for u in users:
        conv_count = await get_user_conversation_count(u["id"])
        result.append({
            "id": u["id"],
            "username": u["username"],
            "display_name": u["display_name"],
            "role": u["role"],
            "created_at": u["created_at"],
            "last_login": u["last_login"],
            "conversation_count": conv_count,
        })
    return {"users": result}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def admin_create_user(body: CreateUserRequest, request: Request, _admin: dict = Depends(require_admin)):
    """Create a new user (admin only)."""
    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'user'")
    existing = await get_user_by_username(body.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")
    password_hash = hash_password(body.password)
    user_id = await create_user(body.username, password_hash, body.display_name, body.role)
    return {"id": user_id, "username": body.username, "display_name": body.display_name, "role": body.role}


@router.delete("/users/{user_id}")
async def admin_delete_user(user_id: int, admin: dict = Depends(require_admin)):
    """Delete a user and all their data (admin only)."""
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    target = await get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await delete_user(user_id)
    return {"success": True, "user_id": user_id}


@router.post("/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: int,
    body: ResetPasswordRequest,
    _admin: dict = Depends(require_admin),
):
    """Reset a user's password (admin only)."""
    target = await get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    password_hash = hash_password(body.new_password)
    await update_user_password(user_id, password_hash)
    await delete_all_refresh_tokens_for_user(user_id)
    return {"success": True, "message": "Password reset successfully"}
