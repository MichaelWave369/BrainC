"""
BrainC health & observability — v1.0
GET /health, GET /health/ready, GET /admin/stats
"""
import os
import shutil
import time
from pathlib import Path

import aiosqlite
import httpx
from fastapi import APIRouter, Depends

from api.auth.middleware import require_admin
from api.core.queue import inference_queue
from api.routes.memory import DB_PATH

router = APIRouter(tags=["health"])

_START_TIME = time.monotonic()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MEMORY_DIR = Path(__file__).parent.parent.parent / "memory"
WORKSPACE_DIR = Path(__file__).parent.parent.parent / "workspace"


def _dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 2)


# ── Basic liveness ────────────────────────────────────────────────────────────


@router.get("/health")
async def health_liveness():
    return {"status": "ok", "version": "1.0.0"}


# ── Readiness check ───────────────────────────────────────────────────────────


@router.get("/health/ready")
async def health_ready():
    checks: dict = {}
    overall = "ok"

    # 1. Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                # Accept any model that starts with "braincbrain"
                loaded = any(m.startswith("braincbrain") for m in models)
                checks["ollama"] = {
                    "status": "ok" if loaded else "warning",
                    "models": models,
                    "braincbrain_loaded": loaded,
                }
                if not loaded:
                    overall = "degraded"
            else:
                checks["ollama"] = {"status": "error", "detail": f"HTTP {r.status_code}"}
                overall = "degraded"
    except Exception as exc:
        checks["ollama"] = {"status": "error", "detail": str(exc)}
        overall = "degraded"

    # 2. Database
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM messages") as cur:
                count = (await cur.fetchone())[0]
        checks["database"] = {"status": "ok", "message_count": count}
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}
        overall = "error"

    # 3. Tools availability
    tool_checks = {}
    for tool in ("search", "executor", "file_reader", "notes"):
        try:
            __import__(f"api.tools.{tool}")
            tool_checks[tool] = "ok"
        except ImportError:
            tool_checks[tool] = "missing"
            overall = "degraded"
    checks["tools"] = tool_checks

    # 4. Queue depth
    checks["queue"] = {
        "depth": inference_queue.qsize(),
        "max_size": inference_queue.maxsize,
    }

    return {
        "status": overall,
        "checks": checks,
        "uptime_seconds": round(time.monotonic() - _START_TIME, 1),
    }


# ── Admin stats ───────────────────────────────────────────────────────────────


@router.get("/admin/stats")
async def admin_stats(_admin: dict = Depends(require_admin)):
    from api.core.queue import active_model_name

    stats: dict = {}

    # DB stats
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            stats["total_users"] = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM conversations") as cur:
            stats["total_conversations"] = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM messages") as cur:
            stats["total_messages"] = (await cur.fetchone())[0]

        # Messages per day (last 30 days)
        async with db.execute("""
            SELECT DATE(timestamp) AS day, COUNT(*) AS count
            FROM messages
            WHERE timestamp >= datetime('now', '-30 days')
            GROUP BY DATE(timestamp)
            ORDER BY day ASC
        """) as cur:
            stats["messages_per_day"] = [dict(r) for r in await cur.fetchall()]

        # Active sessions
        async with db.execute(
            "SELECT COUNT(*) FROM sessions WHERE last_active >= datetime('now', '-1 hour')"
        ) as cur:
            stats["active_sessions"] = (await cur.fetchone())[0]

        # Tool usage counts (from audit_log if it exists)
        try:
            async with db.execute("""
                SELECT action, COUNT(*) AS count FROM audit_log
                WHERE action IN ('code_execution', 'file_read')
                GROUP BY action
            """) as cur:
                stats["tool_usage"] = {r["action"]: r["count"] for r in await cur.fetchall()}
        except Exception:
            stats["tool_usage"] = {}

    # Disk usage
    stats["disk_usage_mb"] = {
        "memory": _dir_size_mb(MEMORY_DIR),
        "workspace": _dir_size_mb(WORKSPACE_DIR),
    }

    # Current model
    stats["active_model"] = active_model_name()

    # System info (psutil optional)
    try:
        import psutil
        stats["system"] = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_used_gb": round(psutil.virtual_memory().used / (1024 ** 3), 2),
        }
    except ImportError:
        stats["system"] = {"note": "psutil not installed"}

    # GPU VRAM (nvidia-smi)
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            gpus = []
            for line in lines:
                used, total = line.split(", ")
                gpus.append({"vram_used_mb": int(used), "vram_total_mb": int(total)})
            stats["gpu"] = gpus
    except Exception:
        stats["gpu"] = []

    return stats


# ── Admin log viewer ──────────────────────────────────────────────────────────


@router.get("/admin/logs")
async def admin_logs(_admin: dict = Depends(require_admin)):
    from api.core.logging import get_recent_log_lines
    lines = get_recent_log_lines(100)
    return {"lines": lines, "count": len(lines)}


# ── Admin audit log ───────────────────────────────────────────────────────────


@router.get("/admin/audit")
async def admin_audit(
    page: int = 1,
    page_size: int = 50,
    user_id: int | None = None,
    action: str | None = None,
    _admin: dict = Depends(require_admin),
):
    from api.core.audit import get_audit_log
    return await get_audit_log(page=page, page_size=page_size, user_id=user_id, action=action)
