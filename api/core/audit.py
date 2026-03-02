"""
BrainC security audit log — v1.0
Append-only audit trail for all sensitive actions, stored in SQLite.
"""
import json
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from api.routes.memory import DB_PATH


# ── Audit log actions ─────────────────────────────────────────────────────────

class AuditAction:
    LOGIN = "login"
    LOGOUT = "logout"
    FAILED_LOGIN = "failed_login"
    PASSWORD_CHANGE = "password_change"
    USER_CREATED = "user_created"
    USER_DELETED = "user_deleted"
    MODEL_SWITCH = "model_switch"
    CODE_EXECUTION = "code_execution"
    FILE_READ = "file_read"
    TOKEN_REFRESH = "token_refresh"


# ── Database init ─────────────────────────────────────────────────────────────


async def ensure_audit_table() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER  PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                action      TEXT     NOT NULL,
                details     TEXT     NOT NULL DEFAULT '{}',
                ip_address  TEXT,
                timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


# ── Write ─────────────────────────────────────────────────────────────────────


async def audit(
    action: str,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    **details: Any,
) -> None:
    """Append an entry to the audit log. Never raises — logs errors internally."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO audit_log (user_id, action, details, ip_address) "
                "VALUES (?, ?, ?, ?)",
                (user_id, action, json.dumps(details), ip_address),
            )
            await db.commit()
    except Exception as exc:
        # Import lazily to avoid circular import
        from api.core.logging import log_error
        log_error(f"Audit log write failed: {exc}")


# ── Read ──────────────────────────────────────────────────────────────────────


async def get_audit_log(
    page: int = 1,
    page_size: int = 50,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
) -> dict:
    conditions = []
    params: list = []

    if user_id is not None:
        conditions.append("user_id = ?")
        params.append(user_id)
    if action:
        conditions.append("action = ?")
        params.append(action)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * page_size

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        count_params = list(params)
        async with db.execute(
            f"SELECT COUNT(*) FROM audit_log {where}", count_params
        ) as cur:
            total = (await cur.fetchone())[0]

        query_params = list(params) + [page_size, offset]
        async with db.execute(
            f"SELECT id, user_id, action, details, ip_address, timestamp "
            f"FROM audit_log {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            query_params,
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    for r in rows:
        try:
            r["details"] = json.loads(r["details"])
        except Exception:
            pass

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "entries": rows,
    }
