"""BrainC v0.4 — Local notes (Markdown) and calendar (JSON) tool.

Notes are stored as Markdown files in ~/BrainC/workspace/notes/.
Calendar events are stored in ~/BrainC/workspace/calendar.json.
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

WORKSPACE = Path.home() / "BrainC" / "workspace"
NOTES_DIR = WORKSPACE / "notes"
CALENDAR_FILE = WORKSPACE / "calendar.json"


def _ensure() -> None:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)


def _safe_slug(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:80] or "untitled"


# ── Notes ────────────────────────────────────────────────────────────────────


def create_note(title: str, content: str) -> dict:
    """Save a new Markdown note and return its metadata."""
    _ensure()
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str}-{_safe_slug(title)}.md"
    path = NOTES_DIR / filename
    path.write_text(f"# {title}\n\n{content}", encoding="utf-8")
    return {"filename": filename, "title": title, "date": date_str, "path": str(path)}


def list_notes() -> list[dict]:
    """Return all notes sorted by date descending."""
    _ensure()
    notes = []
    for f in sorted(NOTES_DIR.glob("*.md"), reverse=True):
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        title = lines[0].lstrip("#").strip() if lines else f.stem
        m = re.match(r"(\d{4}-\d{2}-\d{2})", f.stem)
        notes.append(
            {
                "filename": f.name,
                "title": title,
                "date": m.group(1) if m else "",
                "size": f.stat().st_size,
            }
        )
    return notes


def search_notes(query: str) -> list[dict]:
    """Keyword search across all notes."""
    _ensure()
    ql = query.lower()
    results = []
    for f in NOTES_DIR.glob("*.md"):
        content = f.read_text(encoding="utf-8", errors="replace")
        if ql in content.lower():
            lines = content.splitlines()
            title = lines[0].lstrip("#").strip() if lines else f.stem
            results.append({"filename": f.name, "title": title})
    return results


def read_note(filename: str) -> dict:
    """Read a single note by filename."""
    _ensure()
    safe = Path(filename).name  # strip any directory component
    path = NOTES_DIR / safe
    if not path.exists() or path.suffix != ".md":
        return {"content": None, "filename": safe, "error": f"Note not found: {filename}"}
    content = path.read_text(encoding="utf-8", errors="replace")
    return {"content": content, "filename": safe, "error": None}


def delete_note(filename: str) -> bool:
    """Delete a note. Returns True if deleted, False if not found."""
    _ensure()
    path = NOTES_DIR / Path(filename).name
    if path.exists() and path.suffix == ".md":
        path.unlink()
        return True
    return False


# ── Calendar ─────────────────────────────────────────────────────────────────


def _load() -> list[dict]:
    if CALENDAR_FILE.exists():
        try:
            return json.loads(CALENDAR_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save(events: list[dict]) -> None:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    CALENDAR_FILE.write_text(json.dumps(events, indent=2, ensure_ascii=False))


def add_event(
    title: str, date: str, time: str = "", description: str = ""
) -> dict:
    """Add a calendar event and return it."""
    events = _load()
    event = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "date": date,
        "time": time,
        "description": description,
        "created_at": datetime.now().isoformat(),
    }
    events.append(event)
    _save(events)
    return event


def list_events(from_date: str = "", to_date: str = "") -> list[dict]:
    """List events, optionally filtered by date range."""
    events = _load()
    if from_date:
        events = [e for e in events if e.get("date", "") >= from_date]
    if to_date:
        events = [e for e in events if e.get("date", "") <= to_date]
    return sorted(events, key=lambda e: (e.get("date", ""), e.get("time", "")))


def delete_event(event_id: str) -> bool:
    """Delete an event by id. Returns True if found and deleted."""
    events = _load()
    filtered = [e for e in events if e.get("id") != event_id]
    if len(filtered) == len(events):
        return False
    _save(filtered)
    return True
