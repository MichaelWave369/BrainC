import json
from pathlib import Path
from typing import Optional

import aiosqlite

DB_PATH = Path(__file__).parent.parent.parent / "memory" / "conversations.db"


async def init_db() -> None:
    """Initialize the SQLite database and create / migrate all tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        # ── Users ────────────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER  PRIMARY KEY AUTOINCREMENT,
                username      TEXT     NOT NULL UNIQUE,
                password_hash TEXT     NOT NULL,
                display_name  TEXT     NOT NULL,
                role          TEXT     NOT NULL DEFAULT 'user',
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login    DATETIME
            )
        """)

        # ── Refresh tokens ───────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token      TEXT     PRIMARY KEY,
                user_id    INTEGER  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT     NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Sessions ─────────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT     PRIMARY KEY,
                user_id      INTEGER  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_active  DATETIME DEFAULT CURRENT_TIMESTAMP,
                ip_address   TEXT,
                user_agent   TEXT
            )
        """)

        # ── User preferences ─────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id               INTEGER  PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                theme                 TEXT     NOT NULL DEFAULT 'dark',
                model                 TEXT     NOT NULL DEFAULT 'braincbrain',
                tools_enabled         INTEGER  NOT NULL DEFAULT 1,
                system_prompt_override TEXT,
                context_length        INTEGER  NOT NULL DEFAULT 8192
            )
        """)

        # ── Messages ─────────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                role            TEXT    NOT NULL,
                message         TEXT    NOT NULL,
                conversation_id TEXT    NOT NULL DEFAULT 'default',
                timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
                embedding       BLOB,
                user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        # Safe migrations for existing databases
        for col_sql in [
            "ALTER TABLE messages ADD COLUMN embedding BLOB",
            "ALTER TABLE messages ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
        ]:
            try:
                await db.execute(col_sql)
            except Exception:
                pass

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_id
            ON messages(conversation_id)
        """)

        # ── Conversations ─────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         TEXT     PRIMARY KEY,
                title      TEXT     NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                tags       TEXT     NOT NULL DEFAULT '[]',
                user_id    INTEGER  REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        try:
            await db.execute(
                "ALTER TABLE conversations ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
            )
        except Exception:
            pass

        await db.commit()


# ── User CRUD ────────────────────────────────────────────────────────────────


async def count_users() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def create_user(
    username: str, password_hash: str, display_name: str, role: str = "user"
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
            (username, password_hash, display_name, role),
        )
        await db.commit()
        # Ensure preferences row exists
        await db.execute(
            "INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)",
            (cursor.lastrowid,),
        )
        await db.commit()
        return cursor.lastrowid


async def get_user_by_username(username: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_user_by_id(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def list_users() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, username, display_name, role, created_at, last_login "
            "FROM users ORDER BY created_at ASC"
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def update_user_last_login(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user_id,)
        )
        await db.commit()


async def update_user_password(user_id: int, password_hash: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id)
        )
        await db.commit()


async def delete_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.commit()


async def get_user_conversation_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM conversations WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


# ── Refresh tokens ────────────────────────────────────────────────────────────


async def save_refresh_token(token: str, user_id: int, expires_at: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO refresh_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )
        await db.commit()


async def get_refresh_token(token: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM refresh_tokens WHERE token = ?", (token,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def delete_refresh_token(token: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM refresh_tokens WHERE token = ?", (token,))
        await db.commit()


async def delete_all_refresh_tokens_for_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM refresh_tokens WHERE user_id = ?", (user_id,))
        await db.commit()


# ── Sessions ──────────────────────────────────────────────────────────────────


async def create_session(
    session_id: str, user_id: int, ip_address: str, user_agent: str
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO sessions (session_id, user_id, ip_address, user_agent) "
            "VALUES (?, ?, ?, ?)",
            (session_id, user_id, ip_address, user_agent),
        )
        await db.commit()


async def get_session(session_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def list_sessions_for_user(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY last_active DESC",
            (user_id,),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def update_session_activity(session_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET last_active = CURRENT_TIMESTAMP WHERE session_id = ?",
            (session_id,),
        )
        await db.commit()


async def delete_session(session_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await db.commit()


async def delete_all_sessions_for_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        await db.commit()


async def prune_expired_sessions() -> None:
    """Remove sessions inactive for more than 7 days."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM sessions WHERE last_active < datetime('now', '-7 days')"
        )
        await db.commit()


# ── User preferences ──────────────────────────────────────────────────────────


async def get_preferences(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Ensure row exists
        await db.execute(
            "INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (user_id,)
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {
                    "user_id": user_id,
                    "theme": "dark",
                    "model": "braincbrain",
                    "tools_enabled": True,
                    "system_prompt_override": None,
                    "context_length": 8192,
                }
            d = dict(row)
            d["tools_enabled"] = bool(d["tools_enabled"])
            return d


async def update_preferences(user_id: int, **kwargs) -> None:
    allowed = {"theme", "model", "tools_enabled", "system_prompt_override", "context_length"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return
    # Ensure row exists first
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (user_id,)
        )
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [user_id]
        await db.execute(
            f"UPDATE user_preferences SET {set_clause} WHERE user_id = ?", values
        )
        await db.commit()


# ── Conversation metadata ─────────────────────────────────────────────────────


async def ensure_conversation(
    conversation_id: str, first_message: str, user_id: Optional[int] = None
) -> None:
    """Create a conversation record if one does not already exist."""
    words = first_message.split()
    title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO conversations (id, title, user_id) VALUES (?, ?, ?)",
            (conversation_id, title, user_id),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,),
        )
        await db.commit()


async def list_conversations(user_id: Optional[int] = None) -> list[dict]:
    """Return conversations ordered by most recently updated.

    Pass user_id to scope to a specific user; pass None to return all (admin).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id is not None:
            async with db.execute(
                "SELECT id, title, created_at, updated_at, tags "
                "FROM conversations WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ) as cursor:
                return [dict(r) for r in await cursor.fetchall()]
        else:
            async with db.execute(
                "SELECT id, title, created_at, updated_at, tags "
                "FROM conversations ORDER BY updated_at DESC"
            ) as cursor:
                return [dict(r) for r in await cursor.fetchall()]


async def update_conversation(
    conversation_id: str,
    title: Optional[str] = None,
    tags: Optional[list] = None,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        if title is not None:
            await db.execute(
                "UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (title, conversation_id),
            )
        if tags is not None:
            await db.execute(
                "UPDATE conversations SET tags = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (json.dumps(tags), conversation_id),
            )
        await db.commit()


async def delete_conversation(conversation_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
        )
        await db.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        await db.commit()


async def get_conversation_owner(conversation_id: str) -> Optional[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


# ── Message persistence ───────────────────────────────────────────────────────


async def save_message(
    role: str,
    message: str,
    conversation_id: str = "default",
    embedding: Optional[bytes] = None,
    user_id: Optional[int] = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO messages (role, message, conversation_id, embedding, user_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (role, message, conversation_id, embedding, user_id),
        )
        await db.commit()
        return cursor.lastrowid


async def get_history(conversation_id: str = "default") -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, role, message, conversation_id, timestamp
            FROM   messages
            WHERE  conversation_id = ?
            ORDER  BY timestamp ASC
            """,
            (conversation_id,),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def delete_history(conversation_id: Optional[str] = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        if conversation_id is not None:
            await db.execute(
                "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
            )
        else:
            await db.execute("DELETE FROM messages")
        await db.commit()


# ── Context window management ─────────────────────────────────────────────────


async def get_non_summary_count(conversation_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM messages "
            "WHERE conversation_id = ? AND role != 'summary'",
            (conversation_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_oldest_non_summary_messages(
    conversation_id: str, limit: int
) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, role, message
            FROM   messages
            WHERE  conversation_id = ? AND role != 'summary'
            ORDER  BY timestamp ASC
            LIMIT  ?
            """,
            (conversation_id, limit),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def delete_messages_by_ids(ids: list[int]) -> None:
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"DELETE FROM messages WHERE id IN ({placeholders})", ids
        )
        await db.commit()


async def save_summary(summary_text: str, conversation_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (role, message, conversation_id) "
            "VALUES ('summary', ?, ?)",
            (summary_text, conversation_id),
        )
        await db.commit()


# ── Semantic search ───────────────────────────────────────────────────────────


async def semantic_search(
    query_embedding: bytes,
    top_k: int = 3,
    exclude_conversation_id: Optional[str] = None,
) -> list[dict]:
    """Return the top-k most semantically similar messages across all conversations."""
    from api.routes.embeddings import cosine_similarity

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if exclude_conversation_id:
            async with db.execute(
                """
                SELECT id, role, message, conversation_id, timestamp, embedding
                FROM   messages
                WHERE  embedding IS NOT NULL AND conversation_id != ?
                """,
                (exclude_conversation_id,),
            ) as cursor:
                rows = [dict(r) for r in await cursor.fetchall()]
        else:
            async with db.execute(
                """
                SELECT id, role, message, conversation_id, timestamp, embedding
                FROM   messages
                WHERE  embedding IS NOT NULL
                """
            ) as cursor:
                rows = [dict(r) for r in await cursor.fetchall()]

    if not rows:
        return []

    scored = [
        (cosine_similarity(query_embedding, row["embedding"]), row)
        for row in rows
        if row.get("embedding")
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    results = [row for _, row in scored[:top_k]]
    for r in results:
        r.pop("embedding", None)
    return results


# ── System stats ──────────────────────────────────────────────────────────────


async def get_system_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM conversations") as c:
            total_convs = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM messages") as c:
            total_msgs = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0]
    return {
        "total_conversations": total_convs,
        "total_messages": total_msgs,
        "total_users": total_users,
    }
