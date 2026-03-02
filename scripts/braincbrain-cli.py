#!/usr/bin/env python3
"""
BrainC management CLI — v1.0
Usage: python scripts/braincbrain-cli.py <command> [args]

Commands:
  users list
  users create <username>
  users delete <username>
  users reset-password <username>
  db stats
  db backup
  db restore <backup-file>
  model list
  model switch <model-name>
  logs tail
"""
import argparse
import asyncio
import getpass
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    RED = Fore.RED
    GREEN = Fore.GREEN
    YELLOW = Fore.YELLOW
    CYAN = Fore.CYAN
    BOLD = Style.BRIGHT
    RESET = Style.RESET_ALL
except ImportError:
    RED = GREEN = YELLOW = CYAN = BOLD = RESET = ""

# ── DB path ───────────────────────────────────────────────────────────────────
DB_PATH = REPO_ROOT / "memory" / "conversations.db"
BACKUPS_DIR = REPO_ROOT / "backups"
LOGS_DIR = REPO_ROOT / "logs"


def ok(msg: str) -> None:
    print(f"{GREEN}✓{RESET} {msg}")


def err(msg: str) -> None:
    print(f"{RED}✗ {msg}{RESET}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"{CYAN}→{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠ {msg}{RESET}")


# ── users ─────────────────────────────────────────────────────────────────────


async def cmd_users_list():
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, username, display_name, role, created_at, last_login FROM users ORDER BY id"
        ) as cur:
            users = [dict(r) for r in await cur.fetchall()]
    if not users:
        warn("No users found.")
        return
    print(f"\n{BOLD}{'ID':<5} {'Username':<20} {'Display Name':<25} {'Role':<10} {'Last Login'}{RESET}")
    print("─" * 80)
    for u in users:
        role_color = RED if u["role"] == "admin" else ""
        print(
            f"{u['id']:<5} {u['username']:<20} {u['display_name']:<25} "
            f"{role_color}{u['role']:<10}{RESET} {u['last_login'] or 'never'}"
        )
    print()


async def cmd_users_create(username: str):
    import aiosqlite
    from api.auth.auth import hash_password

    existing = await _get_user(username)
    if existing:
        err(f"User '{username}' already exists.")
        sys.exit(1)

    display_name = input(f"Display name for {username}: ").strip() or username
    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        err("Password must be at least 8 characters.")
        sys.exit(1)
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        err("Passwords do not match.")
        sys.exit(1)

    role = input("Role [user/admin] (default: user): ").strip() or "user"
    if role not in ("user", "admin"):
        err("Role must be 'user' or 'admin'.")
        sys.exit(1)

    pw_hash = hash_password(password)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO users (username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
            (username, pw_hash, display_name, role),
        )
        user_id = cur.lastrowid
        await db.execute("INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (user_id,))
        await db.commit()
    ok(f"Created user '{username}' (id={user_id}, role={role})")


async def cmd_users_delete(username: str):
    import aiosqlite

    user = await _get_user(username)
    if not user:
        err(f"User '{username}' not found.")
        sys.exit(1)

    confirm = input(f"{RED}Delete user '{username}' and ALL their data? [yes/no]: {RESET}").strip()
    if confirm.lower() != "yes":
        warn("Aborted.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE username = ?", (username,))
        await db.commit()
    ok(f"Deleted user '{username}'")


async def cmd_users_reset_password(username: str):
    import aiosqlite
    from api.auth.auth import hash_password

    user = await _get_user(username)
    if not user:
        err(f"User '{username}' not found.")
        sys.exit(1)

    password = getpass.getpass("New password (min 8 chars): ")
    if len(password) < 8:
        err("Password must be at least 8 characters.")
        sys.exit(1)
    confirm = getpass.getpass("Confirm new password: ")
    if password != confirm:
        err("Passwords do not match.")
        sys.exit(1)

    pw_hash = hash_password(password)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET password_hash = ? WHERE username = ?", (pw_hash, username))
        await db.execute("DELETE FROM refresh_tokens WHERE user_id = ?", (user["id"],))
        await db.commit()
    ok(f"Password reset for '{username}'. All sessions invalidated.")


async def _get_user(username: str):
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE username = ?", (username,)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


# ── db ────────────────────────────────────────────────────────────────────────


async def cmd_db_stats():
    import aiosqlite

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM conversations") as c:
            convs = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM messages") as c:
            msgs = (await c.fetchone())[0]
        try:
            async with db.execute("SELECT COUNT(*) FROM audit_log") as c:
                audit_entries = (await c.fetchone())[0]
        except Exception:
            audit_entries = "n/a"

    db_size_mb = round(DB_PATH.stat().st_size / (1024 * 1024), 2) if DB_PATH.exists() else 0

    print(f"\n{BOLD}BrainC Database Stats{RESET}")
    print("─" * 40)
    print(f"  Users:          {users}")
    print(f"  Conversations:  {convs}")
    print(f"  Messages:       {msgs}")
    print(f"  Audit entries:  {audit_entries}")
    print(f"  DB size:        {db_size_mb} MB")
    print()


def cmd_db_backup():
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUPS_DIR / f"braincbrain-{ts}.tar.gz"

    with tarfile.open(backup_path, "w:gz") as tar:
        if DB_PATH.exists():
            tar.add(DB_PATH, arcname="conversations.db")
        workspace = REPO_ROOT / "workspace"
        if workspace.exists():
            tar.add(workspace, arcname="workspace")

    size_mb = round(backup_path.stat().st_size / (1024 * 1024), 2)
    ok(f"Backup created: {backup_path.name} ({size_mb} MB)")


def cmd_db_restore(backup_file: str):
    path = BACKUPS_DIR / backup_file
    if not path.exists():
        err(f"Backup not found: {backup_file}")
        sys.exit(1)

    confirm = input(f"{RED}Restore from '{backup_file}'? This overwrites the current database. [yes/no]: {RESET}").strip()
    if confirm.lower() != "yes":
        warn("Aborted.")
        return

    with tarfile.open(path, "r:gz") as tar:
        tar.extractall(path=REPO_ROOT)
    ok(f"Restored from {backup_file}")


# ── model ─────────────────────────────────────────────────────────────────────


def cmd_model_list():
    try:
        import httpx
        import json

        ollama_url = "http://localhost:11434/api/tags"
        result = subprocess.run(
            ["curl", "-s", ollama_url],
            capture_output=True, text=True, timeout=5,
        )
        data = json.loads(result.stdout)
        models = [m["name"] for m in data.get("models", [])]
        if not models:
            warn("No models found in Ollama.")
            return
        print(f"\n{BOLD}Available Ollama Models:{RESET}")
        for m in models:
            print(f"  • {m}")
        print()
    except Exception as exc:
        err(f"Could not reach Ollama: {exc}")


def cmd_model_switch(model_name: str):
    import re

    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        if re.search(r"^ACTIVE_MODEL\s*=", content, re.MULTILINE):
            content = re.sub(r"^ACTIVE_MODEL\s*=.*$", f"ACTIVE_MODEL={model_name}", content, flags=re.MULTILINE)
        else:
            content += f"\nACTIVE_MODEL={model_name}\n"
        env_file.write_text(content, encoding="utf-8")
    else:
        env_file.write_text(f"ACTIVE_MODEL={model_name}\n", encoding="utf-8")

    ok(f"Active model set to '{model_name}' in .env (restart the API to apply)")


# ── logs ──────────────────────────────────────────────────────────────────────


def cmd_logs_tail():
    log_file = LOGS_DIR / "braincbrain.log"
    if not log_file.exists():
        warn(f"Log file not found: {log_file}")
        return
    try:
        subprocess.run(["tail", "-f", str(log_file)])
    except KeyboardInterrupt:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description=f"{BOLD}BrainC Management CLI — v1.0{RESET}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/braincbrain-cli.py users list
  python scripts/braincbrain-cli.py users create alice
  python scripts/braincbrain-cli.py db backup
  python scripts/braincbrain-cli.py model switch braincbrain-ft
  python scripts/braincbrain-cli.py logs tail
        """,
    )

    subparsers = parser.add_subparsers(dest="group")
    subparsers.required = True

    # users
    users_p = subparsers.add_parser("users", help="User management")
    users_sub = users_p.add_subparsers(dest="action")
    users_sub.required = True
    users_sub.add_parser("list", help="List all users")
    create_p = users_sub.add_parser("create", help="Create a user")
    create_p.add_argument("username")
    delete_p = users_sub.add_parser("delete", help="Delete a user")
    delete_p.add_argument("username")
    reset_p = users_sub.add_parser("reset-password", help="Reset a user's password")
    reset_p.add_argument("username")

    # db
    db_p = subparsers.add_parser("db", help="Database management")
    db_sub = db_p.add_subparsers(dest="action")
    db_sub.required = True
    db_sub.add_parser("stats", help="Show database stats")
    db_sub.add_parser("backup", help="Create a backup")
    restore_p = db_sub.add_parser("restore", help="Restore from a backup")
    restore_p.add_argument("backup_file")

    # model
    model_p = subparsers.add_parser("model", help="Model management")
    model_sub = model_p.add_subparsers(dest="action")
    model_sub.required = True
    model_sub.add_parser("list", help="List available Ollama models")
    switch_p = model_sub.add_parser("switch", help="Switch active model")
    switch_p.add_argument("model_name")

    # logs
    logs_p = subparsers.add_parser("logs", help="Log management")
    logs_sub = logs_p.add_subparsers(dest="action")
    logs_sub.required = True
    logs_sub.add_parser("tail", help="Tail the current log file")

    args = parser.parse_args()

    if args.group == "users":
        if args.action == "list":
            asyncio.run(cmd_users_list())
        elif args.action == "create":
            asyncio.run(cmd_users_create(args.username))
        elif args.action == "delete":
            asyncio.run(cmd_users_delete(args.username))
        elif args.action == "reset-password":
            asyncio.run(cmd_users_reset_password(args.username))

    elif args.group == "db":
        if args.action == "stats":
            asyncio.run(cmd_db_stats())
        elif args.action == "backup":
            cmd_db_backup()
        elif args.action == "restore":
            cmd_db_restore(args.backup_file)

    elif args.group == "model":
        if args.action == "list":
            cmd_model_list()
        elif args.action == "switch":
            cmd_model_switch(args.model_name)

    elif args.group == "logs":
        if args.action == "tail":
            cmd_logs_tail()


if __name__ == "__main__":
    main()
