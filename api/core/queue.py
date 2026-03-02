"""
BrainC Ollama inference queue — v1.0
Serialises Ollama requests to prevent GPU memory conflicts.
"""
import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# ── Configuration ─────────────────────────────────────────────────────────────

MAX_QUEUE_SIZE: int = int(os.getenv("MAX_QUEUE_SIZE", "10"))
QUEUE_TIMEOUT_SECONDS: float = float(os.getenv("QUEUE_TIMEOUT_SECONDS", "120"))

# ── Global queue ──────────────────────────────────────────────────────────────

inference_queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
_queue_lock = asyncio.Lock()

# ── Active model (cached in memory) ──────────────────────────────────────────

_active_model: str = os.getenv("ACTIVE_MODEL", "braincbrain")


def active_model_name() -> str:
    return _active_model


def set_active_model(name: str) -> None:
    global _active_model
    _active_model = name


# ── Queue slot context manager ────────────────────────────────────────────────


@asynccontextmanager
async def queue_slot() -> AsyncGenerator[int, None]:
    """
    Acquire a slot in the inference queue.
    Yields the current queue position (1-based).
    Raises asyncio.QueueFull if the queue is full.
    Raises asyncio.TimeoutError if waiting exceeds QUEUE_TIMEOUT_SECONDS.
    """
    ticket: asyncio.Event = asyncio.Event()

    if inference_queue.full():
        from api.core.errors import QueueFullError
        raise QueueFullError()

    await inference_queue.put(ticket)
    position = inference_queue.qsize()

    try:
        # Wait our turn — the previous request will signal us via the lock
        start = time.monotonic()
        async with asyncio.timeout(QUEUE_TIMEOUT_SECONDS):
            async with _queue_lock:
                elapsed = time.monotonic() - start
                if elapsed > QUEUE_TIMEOUT_SECONDS:
                    raise asyncio.TimeoutError()
                yield position
    finally:
        # Remove our ticket from the queue
        try:
            inference_queue.get_nowait()
            inference_queue.task_done()
        except asyncio.QueueEmpty:
            pass
