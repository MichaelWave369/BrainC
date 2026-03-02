import asyncio
import json
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.auth.middleware import get_current_user
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
    get_conversation_owner,
    get_history,
    get_non_summary_count,
    get_oldest_non_summary_messages,
    get_preferences,
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


# ── Tool detection ───────────────────────────────────────────────────────────

_SEARCH_PATTERNS = re.compile(
    r"\b(search|look up|find|google|what is|who is|what are|latest|news about|"
    r"tell me about|search for|look for|find out|check|results for)\b",
    re.IGNORECASE,
)

_EXECUTE_PATTERNS = re.compile(
    r"\b(run|execute|eval|compute|calculate|python|script|code)\b.*\b(this|following|code|snippet|function)\b"
    r"|```python|```py\b",
    re.IGNORECASE | re.DOTALL,
)

_FILE_PATTERNS = re.compile(
    r"\b(read|open|show|display|load|cat)\b.*\bfile\b"
    r"|\bfile\b.*\b(read|open|show|display|load)\b",
    re.IGNORECASE,
)

_NOTE_PATTERNS = re.compile(
    r"\b(add|create|save|write|make)\b.*\bnote\b"
    r"|\bmy notes\b|\bshow notes\b|\blist notes\b",
    re.IGNORECASE,
)

_CALENDAR_PATTERNS = re.compile(
    r"\b(add|create|schedule|remind|put)\b.*\b(calendar|event|reminder|appointment)\b"
    r"|\b(calendar|schedule|agenda|events)\b",
    re.IGNORECASE,
)


async def _detect_and_run_tool(message: str) -> tuple[str | None, str | None]:
    """
    Detect which tool (if any) to invoke for this message and run it.

    Returns (tool_name, tool_result_text) or (None, None) if no tool matched.
    """
    from api.tools.search import search
    from api.tools.notes import list_notes, search_notes
    from api.tools.executor import execute_code

    if _SEARCH_PATTERNS.search(message):
        # Extract a concise query (use the full message as the search query)
        query = message.strip()
        results = await search(query)
        if results:
            snippets = "\n".join(
                f"- {r['title']}: {r['snippet']} ({r['url']})" for r in results
            )
            return "search", f"Web search results for '{query}':\n{snippets}"
        return "search", f"No search results found for '{query}'."

    if _NOTE_PATTERNS.search(message):
        notes = await list_notes()
        if notes.get("notes"):
            items = "\n".join(
                f"- {n['title']} ({n['filename']})" for n in notes["notes"]
            )
            return "notes", f"Notes ({notes['count']}):\n{items}"
        return "notes", "No notes saved yet."

    if _CALENDAR_PATTERNS.search(message):
        from api.tools.notes import list_events
        events = await list_events()
        if events.get("events"):
            items = "\n".join(
                f"- {e['date']} {e.get('time','')} — {e['title']}" for e in events["events"]
            )
            return "calendar", f"Calendar events:\n{items}"
        return "calendar", "No calendar events found."

    # Code execution: only trigger if there's an actual code block
    if "```" in message and _EXECUTE_PATTERNS.search(message):
        code_match = re.search(r"```(?:python|py)?\n?([\s\S]*?)```", message)
        if code_match:
            code = code_match.group(1).strip()
            result = await asyncio.to_thread(execute_code, code)
            if result["success"]:
                output = result.get("output", "").strip() or "(no output)"
                return "execute", f"Code executed successfully:\n{output}"
            else:
                err = result.get("error", "unknown error")
                return "execute", f"Code execution failed:\n{err}"

    if _FILE_PATTERNS.search(message):
        # Extract a filename-like token from the message
        file_match = re.search(r'["\']([^"\']+\.[a-z]{1,5})["\']', message)
        if file_match:
            from api.tools.file_reader import read_file
            path = file_match.group(1)
            result = await read_file(path)
            if not result.get("error"):
                content = result.get("content", "")
                preview = content[:500] + ("…" if len(content) > 500 else "")
                return "file", f"File '{path}':\n{preview}"
            return "file", f"Could not read file: {result['error']}"

    return None, None


# ── Routes ──────────────────────────────────────────────────────────────────


@router.post("/chat")
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    """Send a message to BrainC and stream the response back.

    On each request:
    1. Auto-creates conversation metadata (title from first 6 words).
    2. Summarizes the oldest 10 turns if the conversation exceeds MAX_TURNS_BEFORE_SUMMARY.
    3. Embeds the user message and injects the top-3 semantically similar past exchanges.
    4. Optionally runs a local tool (search, execute, notes, calendar) and injects the result.
    5. Streams the assistant reply and persists both messages with embeddings.
    """
    conversation_id = request.conversation_id or "default"
    user_id: int = user["id"]

    # Verify conversation ownership if it already exists
    owner = await get_conversation_owner(conversation_id)
    if owner is not None and owner != user_id:
        raise HTTPException(status_code=403, detail="Access denied to this conversation")

    # Load per-user preferences (model, tools_enabled override, etc.)
    prefs = await get_preferences(user_id)
    model_name = prefs.get("model", MODEL_NAME)

    # 1. Ensure conversation metadata exists
    await ensure_conversation(conversation_id, request.message, user_id)

    # 2. Summarize if needed
    await _maybe_summarize(conversation_id)

    # 3. Retrieve current history
    history = await get_history(conversation_id)

    # 4. Embed the user message
    query_embedding = await asyncio.to_thread(embed_text, request.message)

    # 5. Find semantically similar exchanges from other conversations
    similar = await semantic_search(
        query_embedding,
        top_k=TOP_K_SEMANTIC,
        exclude_conversation_id=conversation_id,
    )

    # 6. Optionally run a tool
    tool_name: str | None = None
    tool_result: str | None = None
    if request.tools_enabled:
        tool_name, tool_result = await _detect_and_run_tool(request.message)

    # 7. Build the context window
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

    # Inject tool result into context before the user message
    if tool_result:
        messages.append(
            {
                "role": "system",
                "content": f"[TOOL RESULT — {tool_name}]\n{tool_result}",
            }
        )

    messages.append({"role": "user", "content": request.message})

    # 8. Persist the user message with its embedding
    await save_message("user", request.message, conversation_id, query_embedding, user_id)

    # 9. Build response headers (expose tool activity to the UI)
    response_headers: dict[str, str] = {}
    if tool_name:
        response_headers["X-Tool-Used"] = tool_name
        # Truncate to keep headers reasonable
        preview = (tool_result or "")[:512]
        response_headers["X-Tool-Result"] = preview

    # 10. Stream the response; persist the full reply with embedding on completion
    full_response_parts: list[str] = []

    async def collecting_generator():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/chat",
                json={"model": model_name, "messages": messages, "stream": True},
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
                                    user_id,
                                )
                            break
                    except json.JSONDecodeError:
                        continue

    return StreamingResponse(
        collecting_generator(),
        media_type="text/plain",
        headers=response_headers,
    )


@router.get("/search", response_model=SearchResponse)
async def search_history(
    q: str = Query(..., description="Natural-language search query"),
    user: dict = Depends(get_current_user),
):
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
    ),
    user: dict = Depends(get_current_user),
):
    """Return the full message history for a conversation."""
    owner = await get_conversation_owner(conversation_id)
    if owner is not None and owner != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied to this conversation")
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
    ),
    user: dict = Depends(get_current_user),
):
    """Delete conversation history."""
    if conversation_id:
        owner = await get_conversation_owner(conversation_id)
        if owner is not None and owner != user["id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Access denied to this conversation")
    await delete_history(conversation_id)
    if conversation_id:
        return DeleteResponse(
            success=True,
            message=f"Conversation '{conversation_id}' cleared.",
            conversation_id=conversation_id,
        )
    return DeleteResponse(success=True, message="All conversation history cleared.")
