"""Conversation metadata routes — GET / PATCH / DELETE /conversations."""

import json

from fastapi import APIRouter, HTTPException

from api.models.schemas import ConversationMeta, ConversationUpdate
from api.routes.memory import list_conversations, update_conversation, delete_conversation

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationMeta])
async def get_conversations():
    """List all conversations with metadata, ordered by most recently updated."""
    rows = await list_conversations()
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
async def patch_conversation(conversation_id: str, body: ConversationUpdate):
    """Update a conversation's title or tags."""
    await update_conversation(conversation_id, title=body.title, tags=body.tags)
    rows = await list_conversations()
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
async def remove_conversation(conversation_id: str):
    """Delete a conversation and all its messages."""
    await delete_conversation(conversation_id)
    return {"success": True, "conversation_id": conversation_id}
