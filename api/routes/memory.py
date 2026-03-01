import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "memory" / "conversations.db"


async def init_db():
    """Initialize the SQLite database and create tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                conversation_id TEXT NOT NULL DEFAULT 'default',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_id
            ON messages(conversation_id)
        """)
        await db.commit()


async def save_message(role: str, message: str, conversation_id: str = "default"):
    """Persist a single message to the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (role, message, conversation_id) VALUES (?, ?, ?)",
            (role, message, conversation_id)
        )
        await db.commit()


async def get_history(conversation_id: str = "default") -> list[dict]:
    """Retrieve all messages for a given conversation, ordered by timestamp."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id, role, message, conversation_id, timestamp
            FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
            """,
            (conversation_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def delete_history(conversation_id: str | None = None):
    """
    Delete conversation history.
    If conversation_id is provided, only that conversation is cleared.
    If None, all history is deleted.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        if conversation_id is not None:
            await db.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,)
            )
        else:
            await db.execute("DELETE FROM messages")
        await db.commit()
