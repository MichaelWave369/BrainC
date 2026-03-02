"""Conversation metadata routes — GET / PATCH / DELETE /conversations."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth.middleware import get_current_user
from api.models.schemas import ConversationMeta, ConversationUpdate
from api.routes.memory import (
    delete_conversation,
    get_conversation_owner,
    list_conversations,
    update_conversation,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationMeta])
async def get_conversations(
    all: bool = Query(default=False, description="Admin: return all users' conversations"),
    user: dict = Depends(get_current_user),
):
    """List conversations for the current user.

    Admin users may pass ?all=true to retrieve all conversations.
    """
    if all and user.get("role") == "admin":
        rows = await list_conversations(user_id=None)
    else:
        rows = await list_conversations(user_id=user["id"])

    return [
        ConversationMeta(
            id=r["id"],
            title=r["title"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            tags=json.loads(r["tags"]) if isinstance(r["tags"], str) else r["tags"],
        )
        for r in rows
    ]


@router.patch("/{conversation_id}", response_model=ConversationMeta)
async def patch_conversation(
    conversation_id: str,
    body: ConversationUpdate,
    user: dict = Depends(get_current_user),
):
    """Update a conversation's title or tags."""
    owner = await get_conversation_owner(conversation_id)
    if owner is not None and owner != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied to this conversation")

    await update_conversation(conversation_id, title=body.title, tags=body.tags)
    rows = await list_conversations(user_id=None)
    match = next((r for r in rows if r["id"] == conversation_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationMeta(
        id=match["id"],
        title=match["title"],
        created_at=match["created_at"],
        updated_at=match["updated_at"],
        tags=json.loads(match["tags"]) if isinstance(match["tags"], str) else match["tags"],
    )


@router.delete("/{conversation_id}")
async def remove_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete a conversation and all its messages."""
    owner = await get_conversation_owner(conversation_id)
    if owner is not None and owner != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied to this conversation")
    await delete_conversation(conversation_id)
    return {"success": True, "conversation_id": conversation_id}
