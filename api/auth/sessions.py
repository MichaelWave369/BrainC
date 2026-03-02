"""Session tracking routes — list, revoke, and prune active sessions."""

from fastapi import APIRouter, Depends, HTTPException

from api.auth.middleware import get_current_user
from api.routes.memory import (
    delete_all_sessions_for_user,
    delete_session,
    get_session,
    list_sessions_for_user,
)

router = APIRouter(prefix="/auth/sessions", tags=["auth"])


@router.get("")
async def list_sessions(user: dict = Depends(get_current_user)):
    """List all active sessions for the current user."""
    sessions = await list_sessions_for_user(user["id"])
    return {"sessions": sessions}


@router.delete("/{session_id}")
async def revoke_session(session_id: str, user: dict = Depends(get_current_user)):
    """Revoke a specific session by its ID."""
    session = await get_session(session_id)
    if not session or session["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    await delete_session(session_id)
    return {"success": True, "session_id": session_id}


@router.delete("")
async def revoke_all_sessions(user: dict = Depends(get_current_user)):
    """Revoke all sessions for the current user (logout everywhere)."""
    await delete_all_sessions_for_user(user["id"])
    return {"success": True, "message": "All sessions revoked"}
