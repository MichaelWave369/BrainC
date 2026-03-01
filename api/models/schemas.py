from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's message")
    conversation_id: Optional[str] = Field(
        default="default",
        description="Session identifier for multi-conversation support",
    )
    tools_enabled: bool = Field(
        default=True,
        description="Whether to allow automatic tool invocation for this request",
    )


class ChatMessage(BaseModel):
    id: int
    role: str
    message: str
    conversation_id: str
    timestamp: datetime

    class Config:
        from_attributes = True


class HistoryResponse(BaseModel):
    conversation_id: str
    messages: list[ChatMessage]


class DeleteResponse(BaseModel):
    success: bool
    message: str
    conversation_id: Optional[str] = None


class SearchResult(BaseModel):
    id: int
    role: str
    message: str
    conversation_id: str
    timestamp: datetime


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class ConversationMeta(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    tags: list[str] = []


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    tags: Optional[list[str]] = None
