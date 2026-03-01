"""BrainC v0.4 — Safe file reader restricted to ~/BrainC/workspace/.

Supports text, code, JSON, CSV, and Markdown files. Rejects any path
that escapes the allowed workspace via traversal sequences.
"""

import csv
import io
import json
from pathlib import Path
from typing import Optional

WORKSPACE = Path.home() / "BrainC" / "workspace"

ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".json",
    ".csv", ".yaml", ".yml", ".html", ".css",
}


def _resolve(path_str: str) -> Optional[Path]:
    """Resolve path within WORKSPACE; return None if traversal detected."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    candidate = (WORKSPACE / path_str).resolve()
    try:
        candidate.relative_to(WORKSPACE.resolve())
    except ValueError:
        return None
    return candidate


async def read_file(path_str: str) -> dict:
    """Read a file within the workspace. Returns {content, file_type, size, line_count, error}."""
    resolved = _resolve(path_str)
    if resolved is None:
        return _err("Path traversal detected — only files inside workspace/ are allowed.")

    if not resolved.exists():
        return _err(f"File not found: {path_str}")

    suffix = resolved.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return _err(
            f"File type '{suffix}' is not supported. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    size = resolved.stat().st_size

    if suffix == ".csv":
        return _read_csv(resolved, size)
    if suffix == ".json":
        return _read_json(resolved, size)
    return _read_text(resolved, size)


# ── Format-specific readers ──────────────────────────────────────────────────


def _read_text(path: Path, size: int) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    numbered = "\n".join(f"{i + 1:5}  {line}" for i, line in enumerate(lines))
    return {
        "content": numbered,
        "file_type": path.suffix.lstrip("."),
        "size": size,
        "line_count": len(lines),
        "error": None,
    }


def _read_csv(path: Path, size: int) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    columns = list(reader.fieldnames or [])
    summary = {
        "row_count": len(rows),
        "columns": columns,
        "preview": rows[:5],
    }
    return {
        "content": json.dumps(summary, indent=2, ensure_ascii=False),
        "file_type": "csv",
        "size": size,
        "line_count": len(rows),
        "error": None,
    }


def _read_json(path: Path, size: int) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
        content = json.dumps(data, indent=2, ensure_ascii=False)
    except json.JSONDecodeError as exc:
        content = f"[Invalid JSON — {exc}]\n\n{raw}"
    lines = content.splitlines()
    return {
        "content": content,
        "file_type": "json",
        "size": size,
        "line_count": len(lines),
        "error": None,
    }


def _err(msg: str) -> dict:
    return {"content": None, "file_type": None, "size": 0, "line_count": 0, "error": msg}
