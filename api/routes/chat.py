import asyncio
import json

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.config import MAX_TURNS_BEFORE_SUMMARY, TOP_K_SEMANTIC
from api.models.schemas import (
    ChatMessage,
    ChatRequest,
    DeleteResponse,
    HistoryResponse,
    SearchResponse,
    SearchResult,
)
from api.routes.embeddings import embed_text
from api.routes.memory import (
    delete_history,
    delete_messages_by_ids,
    ensure_conversation,
    get_history,
    get_non_summary_count,
    get_oldest_non_summary_messages,
    save_message,
    save_summary,
    semantic_search,
)

router = APIRouter()

OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_NAME = "braincbrain"


# ── Internal Ollama call (non-streaming, used for summarization) ────────────


async def _call_ollama(messages: list[dict]) -> str:
    """Call Ollama synchronously and return the full response text."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": MODEL_NAME, "messages": messages, "stream": False},
        )
        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Ollama error during summarization: {response.text}",
            )
        return response.json().get("message", {}).get("content", "")


# ── Context window management ───────────────────────────────────────────────


async def _maybe_summarize(conversation_id: str) -> None:
    """Summarize the oldest 10 turns when a conversation exceeds MAX_TURNS_BEFORE_SUMMARY."""
    count = await get_non_summary_count(conversation_id)
    if count <= MAX_TURNS_BEFORE_SUMMARY:
        return

    oldest = await get_oldest_non_summary_messages(conversation_id, 10)
    if not oldest:
        return

    convo_text = "\n".join(
        f"{m['role'].upper()}: {m['message']}" for m in oldest
    )
    summary_messages = [
        {
            "role": "system",
            "content": (
                "You are a conversation summarizer. Produce a concise, factual summary "
                "of the following exchange, preserving all key context, decisions, and facts."
            ),
        },
        {
            "role": "user",
            "content": f"Summarize this conversation:\n\n{convo_text}",
        },
    ]
    summary_text = await _call_ollama(summary_messages)
    if summary_text:
        await delete_messages_by_ids([m["id"] for m in oldest])
        await save_summary(summary_text, conversation_id)


# ── Routes ──────────────────────────────────────────────────────────────────


@router.post("/chat")
async def chat(request: ChatRequest):
    """Send a message to BrainC and stream the response back.

    On each request:
    1. Auto-creates conversation metadata (title from first 6 words).
    2. Summarizes the oldest 10 turns if the conversation exceeds MAX_TURNS_BEFORE_SUMMARY.
    3. Embeds the user message and injects the top-3 semantically similar past exchanges.
    4. Streams the assistant reply and persists both messages with embeddings.
    """
    conversation_id = request.conversation_id or "default"

    # 1. Ensure conversation metadata exists
    await ensure_conversation(conversation_id, request.message)

    # 2. Summarize if needed
    await _maybe_summarize(conversation_id)

    # 3. Retrieve current history (may now contain a fresh summary)
    history = await get_history(conversation_id)

    # 4. Embed the user message
    query_embedding = await asyncio.to_thread(embed_text, request.message)

    # 5. Find semantically similar exchanges from other conversations
    similar = await semantic_search(
        query_embedding,
        top_k=TOP_K_SEMANTIC,
        exclude_conversation_id=conversation_id,
    )

    # 6. Build the context window
    messages: list[dict] = []

    if similar:
        context_lines = [
            f"[Memory — conversation '{r['conversation_id']}']\n"
            f"{r['role'].upper()}: {r['message']}"
            for r in similar
        ]
        messages.append(
            {
                "role": "system",
                "content": (
                    "Relevant past exchanges retrieved from memory:\n\n"
                    + "\n\n".join(context_lines)
                ),
            }
        )

    for row in history:
        if row["role"] == "summary":
            messages.append(
                {
                    "role": "system",
                    "content": f"[Earlier conversation summary]: {row['message']}",
                }
            )
        else:
            messages.append({"role": row["role"], "content": row["message"]})

    messages.append({"role": "user", "content": request.message})

    # 7. Persist the user message with its embedding
    await save_message("user", request.message, conversation_id, query_embedding)

    # 8. Stream the response; persist the full reply with embedding on completion
    full_response_parts: list[str] = []

    async def collecting_generator():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/chat",
                json={"model": MODEL_NAME, "messages": messages, "stream": True},
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    yield (
                        f"[ERROR] Ollama returned {response.status_code}: "
                        f"{error_body.decode()}"
                    )
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
                            full_response = "".join(full_response_parts)
                            if full_response:
                                assistant_embedding = await asyncio.to_thread(
                                    embed_text, full_response
                                )
                                await save_message(
                                    "assistant",
                                    full_response,
                                    conversation_id,
                                    assistant_embedding,
                                )
                            break
                    except json.JSONDecodeError:
                        continue

    return StreamingResponse(collecting_generator(), media_type="text/plain")


@router.get("/search", response_model=SearchResponse)
async def search_history(q: str = Query(..., description="Natural-language search query")):
    """Return the top semantically similar past messages for a query."""
    query_embedding = await asyncio.to_thread(embed_text, q)
    results = await semantic_search(query_embedding, top_k=TOP_K_SEMANTIC)
    return SearchResponse(
        query=q,
        results=[
            SearchResult(
                id=r["id"],
                role=r["role"],
                message=r["message"],
                conversation_id=r["conversation_id"],
                timestamp=r["timestamp"],
            )
            for r in results
        ],
    )


@router.get("/history", response_model=HistoryResponse)
async def get_conversation_history(
    conversation_id: str = Query(
        default="default", description="Conversation session ID"
    )
):
    """Return the full message history for a conversation."""
    rows = await get_history(conversation_id)
    return HistoryResponse(
        conversation_id=conversation_id,
        messages=[
            ChatMessage(
                id=row["id"],
                role=row["role"],
                message=row["message"],
                conversation_id=row["conversation_id"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ],
    )


@router.delete("/history", response_model=DeleteResponse)
async def clear_history(
    conversation_id: str = Query(
        default=None,
        description="Conversation ID to clear. Omit to clear ALL history.",
    )
):
    """Delete conversation history."""
    await delete_history(conversation_id)
    if conversation_id:
        return DeleteResponse(
            success=True,
            message=f"Conversation '{conversation_id}' cleared.",
            conversation_id=conversation_id,
        )
    return DeleteResponse(success=True, message="All conversation history cleared.")
