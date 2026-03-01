import json
from pathlib import Path
from typing import Optional

import aiosqlite

DB_PATH = Path(__file__).parent.parent.parent / "memory" / "conversations.db"


async def init_db() -> None:
    """Initialize the SQLite database and create / migrate tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                role            TEXT    NOT NULL,
                message         TEXT    NOT NULL,
                conversation_id TEXT    NOT NULL DEFAULT 'default',
                timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
                embedding       BLOB
            )
        """)
        # Safe migration: add embedding column to existing databases
        try:
            await db.execute("ALTER TABLE messages ADD COLUMN embedding BLOB")
        except Exception:
            pass  # column already exists

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_id
            ON messages(conversation_id)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         TEXT     PRIMARY KEY,
                title      TEXT     NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                tags       TEXT     NOT NULL DEFAULT '[]'
            )
        """)
        await db.commit()


# ── Conversation metadata ───────────────────────────────────────────────────


async def ensure_conversation(conversation_id: str, first_message: str) -> None:
    """Create a conversation record if one does not already exist.

    The title is auto-generated from the first six words of the opening message.
    Subsequent calls for the same id only bump updated_at.
    """
    words = first_message.split()
    title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO conversations (id, title) VALUES (?, ?)",
            (conversation_id, title),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,),
        )
        await db.commit()


async def list_conversations() -> list[dict]:
    """Return all conversations ordered by most recently updated."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    """Update a conversation's title or tags."""
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
    """Delete a conversation and all associated messages."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
        )
        await db.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        await db.commit()


# ── Message persistence ─────────────────────────────────────────────────────


async def save_message(
    role: str,
    message: str,
    conversation_id: str = "default",
    embedding: Optional[bytes] = None,
) -> int:
    """Persist a single message and return its row id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO messages (role, message, conversation_id, embedding) "
            "VALUES (?, ?, ?, ?)",
            (role, message, conversation_id, embedding),
        )
        await db.commit()
        return cursor.lastrowid


async def get_history(conversation_id: str = "default") -> list[dict]:
    """Retrieve all messages for a given conversation, ordered by timestamp."""
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
    """Delete conversation history. Pass None to delete everything."""
    async with aiosqlite.connect(DB_PATH) as db:
        if conversation_id is not None:
            await db.execute(
                "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
            )
        else:
            await db.execute("DELETE FROM messages")
        await db.commit()


# ── Context window management ───────────────────────────────────────────────


async def get_non_summary_count(conversation_id: str) -> int:
    """Count non-summary messages in a conversation."""
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
    """Fetch the oldest non-summary messages for summarization."""
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
    """Delete specific messages by their row IDs."""
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"DELETE FROM messages WHERE id IN ({placeholders})", ids
        )
        await db.commit()


async def save_summary(summary_text: str, conversation_id: str) -> None:
    """Insert a summary message for a conversation."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (role, message, conversation_id) "
            "VALUES ('summary', ?, ?)",
            (summary_text, conversation_id),
        )
        await db.commit()


# ── Semantic search ─────────────────────────────────────────────────────────


async def semantic_search(
    query_embedding: bytes,
    top_k: int = 3,
    exclude_conversation_id: Optional[str] = None,
) -> list[dict]:
    """Return the top-k most semantically similar messages across all conversations.

    Embeddings are compared using cosine similarity (dot product of normalized vectors).
    Importing cosine_similarity here avoids a module-level circular dependency.
    """
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
