"""
BrainC runtime model switching — v1.0
GET /models, POST /models/switch, GET /models/active
"""
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth.middleware import require_admin
from api.core.audit import AuditAction, audit
from api.core.logging import log
from api.core.queue import active_model_name, set_active_model

router = APIRouter(prefix="/models", tags=["models"])

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
ENV_FILE = Path(__file__).parent.parent.parent / ".env"


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _list_ollama_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
    except Exception as exc:
        from api.core.errors import OllamaError
        raise OllamaError(detail=str(exc))


def _persist_model_to_env(model: str) -> None:
    """Write ACTIVE_MODEL to .env, creating the file if needed."""
    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
        if re.search(r"^ACTIVE_MODEL\s*=", content, re.MULTILINE):
            content = re.sub(
                r"^ACTIVE_MODEL\s*=.*$",
                f"ACTIVE_MODEL={model}",
                content,
                flags=re.MULTILINE,
            )
        else:
            content += f"\nACTIVE_MODEL={model}\n"
        ENV_FILE.write_text(content, encoding="utf-8")
    else:
        ENV_FILE.write_text(f"ACTIVE_MODEL={model}\n", encoding="utf-8")


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("")
async def list_models():
    """List all available Ollama models."""
    models = await _list_ollama_models()
    return {"models": models, "active": active_model_name()}


@router.get("/active")
async def get_active_model():
    """Return the currently active model."""
    return {"model": active_model_name()}


class SwitchModelRequest(BaseModel):
    model: str


@router.post("/switch")
async def switch_model(body: SwitchModelRequest, admin: dict = Depends(require_admin)):
    """Switch the active inference model (admin only)."""
    available = await _list_ollama_models()
    if body.model not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{body.model}' not found in Ollama. Available: {available}",
        )

    previous = active_model_name()
    set_active_model(body.model)

    # Persist to .env
    try:
        await __import__("asyncio").to_thread(_persist_model_to_env, body.model)
    except Exception as exc:
        log.warning("model_env_persist_failed", error=str(exc))

    await audit(
        AuditAction.MODEL_SWITCH,
        user_id=admin["id"],
        previous_model=previous,
        new_model=body.model,
    )

    log.info("model_switched", previous=previous, new=body.model, admin_id=admin["id"])

    return {
        "previous_model": previous,
        "new_model": body.model,
        "switched_at": datetime.now(timezone.utc).isoformat(),
    }
