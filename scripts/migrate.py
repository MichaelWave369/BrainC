#!/usr/bin/env python3
"""
BrainC standalone migration runner — v1.0
Usage:
    python scripts/migrate.py              # apply pending migrations
    python scripts/migrate.py --status     # show migration status
    python scripts/migrate.py --rollback 006_add_audit_log.sql
"""
import asyncio
import sys
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from api.core.migrations import run_migrations, rollback_migration, migration_status


def main():
    parser = argparse.ArgumentParser(description="BrainC migration runner")
    parser.add_argument("--rollback", metavar="NAME", help="Roll back a named migration")
    parser.add_argument("--status", action="store_true", help="Show migration status")
    args = parser.parse_args()

    if args.rollback:
        ok = asyncio.run(rollback_migration(args.rollback))
        if ok:
            print(f"✓ Rolled back: {args.rollback}")
        else:
            print(f"✗ Not found: {args.rollback}")
            sys.exit(1)
    elif args.status:
        rows = asyncio.run(migration_status())
        if not rows:
            print("No migration files found.")
        for r in rows:
            mark = "✓" if r["applied"] else "✗"
            print(f"  {mark} {r['name']}")
    else:
        applied = asyncio.run(run_migrations())
        if applied:
            print(f"✓ Applied {len(applied)} migration(s):")
            for name in applied:
                print(f"    • {name}")
        else:
            print("✓ No new migrations — database is up to date.")


if __name__ == "__main__":
    main()
