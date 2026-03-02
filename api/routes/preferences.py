"""Per-user preference routes — GET and PATCH /preferences."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth.middleware import get_current_user
from api.routes.memory import get_preferences, update_preferences

router = APIRouter(prefix="/preferences", tags=["preferences"])


class PreferenceUpdate(BaseModel):
    theme: Optional[str] = None
    model: Optional[str] = None
    tools_enabled: Optional[bool] = None
    system_prompt_override: Optional[str] = None
    context_length: Optional[int] = None


@router.get("")
async def get_user_preferences(user: dict = Depends(get_current_user)):
    """Return the current user's preferences."""
    return await get_preferences(user["id"])


@router.patch("")
async def patch_user_preferences(
    body: PreferenceUpdate, user: dict = Depends(get_current_user)
):
    """Update the current user's preferences. Only provided fields are changed."""
    valid_themes = {"dark", "light", "system"}
    valid_lengths = {4096, 8192, 16384}

    updates = body.model_dump(exclude_none=True)

    if "theme" in updates and updates["theme"] not in valid_themes:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"theme must be one of {valid_themes}")

    if "context_length" in updates and updates["context_length"] not in valid_lengths:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"context_length must be one of {valid_lengths}")

    await update_preferences(user["id"], **updates)
    return await get_preferences(user["id"])
