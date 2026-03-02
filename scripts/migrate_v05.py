#!/usr/bin/env python3
"""
BrainC v0.5 Database Migration
Adds user_id columns to messages and conversations tables,
creates users/sessions/refresh_tokens/user_preferences tables,
and assigns all existing data to a default 'admin' user.

Usage:
    python scripts/migrate_v05.py [--db PATH]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

import aiosqlite


async def migrate(db_path: Path) -> None:
    if not db_path.exists():
        print(f"[skip] Database not found at {db_path} — nothing to migrate.")
        return

    print(f"[*] Migrating {db_path}")

    async with aiosqlite.connect(db_path) as db:
        # ── Create new tables ──────────────────────────────────────────────

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

        await db.execute("""
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token      TEXT     PRIMARY KEY,
                user_id    INTEGER  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT     NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

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

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id                INTEGER  PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                theme                  TEXT     NOT NULL DEFAULT 'dark',
                model                  TEXT     NOT NULL DEFAULT 'braincbrain',
                tools_enabled          INTEGER  NOT NULL DEFAULT 1,
                system_prompt_override TEXT,
                context_length         INTEGER  NOT NULL DEFAULT 8192
            )
        """)

        # ── Add user_id columns to existing tables ─────────────────────────

        for alter_sql in [
            "ALTER TABLE messages ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE conversations ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
        ]:
            try:
                await db.execute(alter_sql)
                print(f"[+] {alter_sql.split('ADD COLUMN')[1].strip()[:40]}")
            except Exception:
                print(f"[=] Column already exists, skipping")

        # ── Ensure a default admin user exists ─────────────────────────────

        async with db.execute("SELECT id FROM users WHERE username = 'admin'") as cursor:
            admin_row = await cursor.fetchone()

        if admin_row:
            admin_id = admin_row[0]
            print(f"[=] Admin user already exists (id={admin_id})")
        else:
            # Create a placeholder admin — setup.sh will set the real password
            cursor = await db.execute(
                "INSERT INTO users (username, password_hash, display_name, role) "
                "VALUES ('admin', '__PLACEHOLDER__', 'Admin', 'admin')"
            )
            admin_id = cursor.lastrowid
            await db.execute(
                "INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (admin_id,)
            )
            print(f"[+] Created placeholder admin user (id={admin_id})")

        # ── Assign existing data to the admin user ─────────────────────────

        await db.execute(
            "UPDATE messages SET user_id = ? WHERE user_id IS NULL", (admin_id,)
        )
        await db.execute(
            "UPDATE conversations SET user_id = ? WHERE user_id IS NULL", (admin_id,)
        )

        async with db.execute("SELECT changes()") as c:
            pass

        await db.commit()

    print("[ok] Migration complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="BrainC v0.5 database migration")
    parser.add_argument(
        "--db",
        default=str(Path(__file__).parent.parent / "memory" / "conversations.db"),
        help="Path to the SQLite database (default: memory/conversations.db)",
    )
    args = parser.parse_args()
    asyncio.run(migrate(Path(args.db)))


if __name__ == "__main__":
    main()
