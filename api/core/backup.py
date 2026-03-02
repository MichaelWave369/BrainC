"""
BrainC automated backup system — v1.0
Daily backups of conversations.db + workspace/notes/ as tar.gz.
Keeps last 30 backups. Runs at 3am via asyncio background task.
"""
import asyncio
import shutil
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth.middleware import require_admin

router = APIRouter(prefix="/admin/backups", tags=["admin"])

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
DB_PATH = REPO_ROOT / "memory" / "conversations.db"
WORKSPACE_DIR = REPO_ROOT / "workspace"
BACKUPS_DIR = REPO_ROOT / "backups"
MAX_BACKUPS = 30


# ── Core backup logic ─────────────────────────────────────────────────────────


def _create_backup() -> Path:
    """Create a tar.gz backup. Returns path to the backup file."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUPS_DIR / f"braincbrain-{ts}.tar.gz"

    with tarfile.open(backup_path, "w:gz") as tar:
        if DB_PATH.exists():
            tar.add(DB_PATH, arcname="conversations.db")
        if WORKSPACE_DIR.exists():
            tar.add(WORKSPACE_DIR, arcname="workspace")

    return backup_path


def _prune_old_backups() -> int:
    """Delete backups beyond MAX_BACKUPS. Returns count deleted."""
    backups = sorted(BACKUPS_DIR.glob("braincbrain-*.tar.gz"), key=lambda p: p.stat().st_mtime)
    to_delete = backups[:-MAX_BACKUPS] if len(backups) > MAX_BACKUPS else []
    for f in to_delete:
        f.unlink()
    return len(to_delete)


async def run_backup() -> dict:
    """Run backup in a thread pool (file I/O). Returns backup info."""
    backup_path = await asyncio.to_thread(_create_backup)
    deleted = await asyncio.to_thread(_prune_old_backups)
    size_mb = round(backup_path.stat().st_size / (1024 * 1024), 2)
    return {
        "backup_file": backup_path.name,
        "size_mb": size_mb,
        "old_backups_deleted": deleted,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Background scheduler ──────────────────────────────────────────────────────


async def _backup_scheduler() -> None:
    """Run a backup at 3am UTC every day."""
    from api.core.logging import log
    while True:
        now = datetime.now(timezone.utc)
        # Seconds until next 3am UTC
        target_hour = 3
        seconds_until = (
            (target_hour - now.hour) % 24 * 3600
            + (60 - now.minute - 1) * 60
            + (60 - now.second)
        )
        if seconds_until == 0:
            seconds_until = 86400  # exactly 3am — wait 24h
        await asyncio.sleep(seconds_until)
        try:
            info = await run_backup()
            log.info("scheduled_backup", **info)
        except Exception as exc:
            log.error("scheduled_backup_failed", error=str(exc))


def start_backup_scheduler() -> asyncio.Task:
    return asyncio.create_task(_backup_scheduler())


# ── Routes ────────────────────────────────────────────────────────────────────


class RestoreRequest(BaseModel):
    filename: str


@router.get("")
async def list_backups(_admin: dict = Depends(require_admin)):
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    backups = sorted(BACKUPS_DIR.glob("braincbrain-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "backups": [
            {
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
            for f in backups
        ]
    }


@router.post("/trigger")
async def trigger_backup(_admin: dict = Depends(require_admin)):
    info = await run_backup()
    return {"success": True, **info}


@router.post("/restore")
async def restore_backup(body: RestoreRequest, _admin: dict = Depends(require_admin)):
    backup_path = BACKUPS_DIR / body.filename
    if not backup_path.exists() or not backup_path.suffix == ".gz":
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Backup file not found")

    # Extract to repo root
    with tarfile.open(backup_path, "r:gz") as tar:
        tar.extractall(path=REPO_ROOT)

    return {"success": True, "restored_from": body.filename}
