"""
BrainC database migration system — v1.0
Tracks applied migrations in schema_migrations table and runs new ones on startup.
"""
import asyncio
import re
from pathlib import Path

import aiosqlite

from api.routes.memory import DB_PATH

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "scripts" / "migrations"


async def _ensure_migrations_table(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id          INTEGER  PRIMARY KEY AUTOINCREMENT,
            name        TEXT     NOT NULL UNIQUE,
            applied_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.commit()


async def _applied_migrations(db: aiosqlite.Connection) -> set[str]:
    async with db.execute("SELECT name FROM schema_migrations ORDER BY name") as cur:
        rows = await cur.fetchall()
    return {r[0] for r in rows}


async def run_migrations() -> list[str]:
    """Apply any pending SQL migrations from scripts/migrations/. Returns list of applied names."""
    if not MIGRATIONS_DIR.exists():
        return []

    migration_files = sorted(
        f for f in MIGRATIONS_DIR.glob("*.sql") if re.match(r"^\d{3}_", f.name)
    )

    applied: list[str] = []
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_migrations_table(db)
        done = await _applied_migrations(db)

        for mf in migration_files:
            if mf.name in done:
                continue
            sql = mf.read_text(encoding="utf-8")
            # Execute each statement separately
            statements = [s.strip() for s in sql.split(";") if s.strip()]
            for stmt in statements:
                await db.execute(stmt)
            await db.execute(
                "INSERT INTO schema_migrations (name) VALUES (?)", (mf.name,)
            )
            await db.commit()
            applied.append(mf.name)

    return applied


async def rollback_migration(name: str) -> bool:
    """Remove a migration record from schema_migrations (rollback tracking only)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_migrations_table(db)
        result = await db.execute(
            "DELETE FROM schema_migrations WHERE name = ?", (name,)
        )
        await db.commit()
        return result.rowcount > 0


async def migration_status() -> list[dict]:
    """Return status of all migration files."""
    if not MIGRATIONS_DIR.exists():
        return []
    migration_files = sorted(
        f for f in MIGRATIONS_DIR.glob("*.sql") if re.match(r"^\d{3}_", f.name)
    )
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_migrations_table(db)
        done = await _applied_migrations(db)

    return [
        {"name": mf.name, "applied": mf.name in done}
        for mf in migration_files
    ]


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="BrainC migration runner")
    parser.add_argument("--rollback", metavar="NAME", help="Roll back a named migration")
    parser.add_argument("--status", action="store_true", help="Show migration status")
    args = parser.parse_args()

    if args.rollback:
        ok = asyncio.run(rollback_migration(args.rollback))
        print(f"Rolled back: {args.rollback}" if ok else f"Not found: {args.rollback}")
    elif args.status:
        rows = asyncio.run(migration_status())
        for r in rows:
            status = "✓" if r["applied"] else "✗"
            print(f"  {status} {r['name']}")
    else:
        applied = asyncio.run(run_migrations())
        if applied:
            print(f"Applied {len(applied)} migration(s): {', '.join(applied)}")
        else:
            print("No new migrations.")
