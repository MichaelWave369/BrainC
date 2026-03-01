import json
import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.models.schemas import ChatRequest, HistoryResponse, DeleteResponse, ChatMessage
from api.routes.memory import save_message, get_history, delete_history

router = APIRouter()

OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_NAME = "braincbrain"


async def stream_ollama(messages: list[dict]) -> StreamingResponse:
    """Stream a chat completion from the Ollama API."""

    async def generator():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": MODEL_NAME,
                    "messages": messages,
                    "stream": True,
                },
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    raise HTTPException(
                        status_code=502,
                        detail=f"Ollama error: {error_body.decode()}"
                    )
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

    return StreamingResponse(generator(), media_type="text/plain")


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Send a message to BrainC and stream the response back.
    Stores both the user message and assistant reply in SQLite.
    """
    conversation_id = request.conversation_id or "default"

    # Retrieve existing history to build context window
    history = await get_history(conversation_id)
    messages = [
        {"role": row["role"], "content": row["message"]}
        for row in history
    ]
    messages.append({"role": "user", "content": request.message})

    # Persist the user message before streaming
    await save_message("user", request.message, conversation_id)

    # Collect the full assistant response while streaming
    full_response_parts = []

    async def collecting_generator():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": MODEL_NAME,
                    "messages": messages,
                    "stream": True,
                },
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    yield f"[ERROR] Ollama returned {response.status_code}: {error_body.decode()}"
                    return

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            full_response_parts.append(content)
                            yield content
                        if chunk.get("done"):
                            # Persist the complete assistant reply
                            full_response = "".join(full_response_parts)
                            if full_response:
                                await save_message("assistant", full_response, conversation_id)
                            break
                    except json.JSONDecodeError:
                        continue

    return StreamingResponse(collecting_generator(), media_type="text/plain")


@router.get("/history", response_model=HistoryResponse)
async def get_conversation_history(
    conversation_id: str = Query(default="default", description="Conversation session ID")
):
    """Return the full message history for a conversation."""
    rows = await get_history(conversation_id)
    messages = [
        ChatMessage(
            id=row["id"],
            role=row["role"],
            message=row["message"],
            conversation_id=row["conversation_id"],
            timestamp=row["timestamp"],
        )
        for row in rows
    ]
    return HistoryResponse(conversation_id=conversation_id, messages=messages)


@router.delete("/history", response_model=DeleteResponse)
async def clear_history(
    conversation_id: str = Query(
        default=None,
        description="Conversation ID to clear. Omit to clear ALL history."
    )
):
    """
    Delete conversation history.
    Provide conversation_id to clear a specific session, or omit to wipe everything.
    """
    await delete_history(conversation_id)
    if conversation_id:
        return DeleteResponse(
            success=True,
            message=f"Conversation '{conversation_id}' cleared.",
            conversation_id=conversation_id
        )
    return DeleteResponse(success=True, message="All conversation history cleared.")
