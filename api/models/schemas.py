from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's message")
    conversation_id: Optional[str] = Field(
        default="default",
        description="Session identifier for multi-conversation support"
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
