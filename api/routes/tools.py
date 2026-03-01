"""Tool routes — web search, code execution, file reading, notes, calendar."""

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.tools.executor import execute_code
from api.tools.file_reader import read_file
from api.tools.notes import (
    add_event,
    create_note,
    delete_event,
    delete_note,
    list_events,
    list_notes,
    read_note,
    search_notes,
)
from api.tools.search import search

router = APIRouter(prefix="/tools", tags=["tools"])


# ── Request models ───────────────────────────────────────────────────────────


class ExecuteRequest(BaseModel):
    code: str


class FileReadRequest(BaseModel):
    path: str


class NoteCreateRequest(BaseModel):
    title: str
    content: str


class CalendarEventRequest(BaseModel):
    title: str
    date: str  # YYYY-MM-DD
    time: str = ""
    description: str = ""


# ── Web search ───────────────────────────────────────────────────────────────


@router.get("/search")
async def tool_search(q: str = Query(..., description="Search query")):
    """Search the web via SearXNG."""
    results = await search(q)
    return {"query": q, "results": results}


# ── Code execution ───────────────────────────────────────────────────────────


@router.post("/execute")
async def tool_execute(req: ExecuteRequest):
    """Execute Python code in a sandboxed subprocess."""
    result = await asyncio.to_thread(execute_code, req.code)
    if not result["success"] and result.get("error"):
        # Still return 200 with error info — the caller decides how to handle
        pass
    return result


# ── File reading ─────────────────────────────────────────────────────────────


@router.post("/read-file")
async def tool_read_file(req: FileReadRequest):
    """Read a file from the BrainC workspace."""
    result = await read_file(req.path)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── Notes ────────────────────────────────────────────────────────────────────


@router.get("/notes")
async def tool_list_notes():
    """List all notes."""
    return await list_notes()


@router.post("/notes", status_code=201)
async def tool_create_note(req: NoteCreateRequest):
    """Create a new markdown note."""
    result = await create_note(req.title, req.content)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/notes/search")
async def tool_search_notes(q: str = Query(..., description="Search query")):
    """Search notes by title and content."""
    return await search_notes(q)


@router.get("/notes/{filename}")
async def tool_read_note(filename: str):
    """Read a specific note by filename."""
    result = await read_note(filename)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/notes/{filename}")
async def tool_delete_note(filename: str):
    """Delete a note."""
    result = await delete_note(filename)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ── Calendar ─────────────────────────────────────────────────────────────────


@router.get("/calendar")
async def tool_list_events(
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
):
    """List calendar events, optionally filtered by date range."""
    return await list_events(from_date, to_date)


@router.post("/calendar", status_code=201)
async def tool_add_event(req: CalendarEventRequest):
    """Add a calendar event."""
    result = await add_event(req.title, req.date, req.time, req.description)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/calendar/{event_id}")
async def tool_delete_event(event_id: str):
    """Delete a calendar event by ID."""
    result = await delete_event(event_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result
