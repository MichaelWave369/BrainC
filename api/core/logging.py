"""
BrainC structured logging — v1.0
Uses structlog for JSON-structured logs with daily rotation.
"""
import logging
import logging.handlers
import os
import time
from pathlib import Path
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# ── Configuration ─────────────────────────────────────────────────────────────

LOG_LEVEL_STR: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL: int = getattr(logging, LOG_LEVEL_STR, logging.INFO)
DEV_MODE: bool = os.getenv("ENV", "production").lower() in ("development", "dev", "local")

LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── Standard library logging setup ───────────────────────────────────────────


def _configure_stdlib_logging() -> None:
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)

    fmt = logging.Formatter("%(message)s")

    # Daily rotating file handler — keeps 30 days of logs
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOGS_DIR / "braincbrain.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    if DEV_MODE:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(fmt)
        root.addHandler(console_handler)


_configure_stdlib_logging()

# ── structlog configuration ───────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL),
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger("braincbrain")


# ── Convenience loggers ───────────────────────────────────────────────────────


def log_request(
    method: str,
    path: str,
    user_id: int | None,
    duration_ms: float,
    status_code: int,
) -> None:
    log.info(
        "http_request",
        method=method,
        path=path,
        user_id=user_id,
        duration_ms=round(duration_ms, 2),
        status_code=status_code,
    )


def log_ollama_call(
    model: str,
    prompt_tokens: int | None,
    response_tokens: int | None,
    duration_ms: float,
    success: bool = True,
) -> None:
    log.info(
        "ollama_call",
        model=model,
        prompt_tokens=prompt_tokens,
        response_tokens=response_tokens,
        duration_ms=round(duration_ms, 2),
        success=success,
    )


def log_tool_use(tool_name: str, success: bool, duration_ms: float) -> None:
    log.info(
        "tool_use",
        tool_name=tool_name,
        success=success,
        duration_ms=round(duration_ms, 2),
    )


def log_auth_event(event: str, user_id: int | None = None, ip: str | None = None, detail: str | None = None) -> None:
    log.info(
        "auth_event",
        event=event,
        user_id=user_id,
        ip=ip,
        detail=detail,
    )


def log_rate_limit_hit(path: str, ip: str, user_id: int | None = None) -> None:
    log.warning(
        "rate_limit_hit",
        path=path,
        ip=ip,
        user_id=user_id,
    )


def log_error(error: str, exc_info: bool = False, **kwargs) -> None:
    log.error("error", error=error, exc_info=exc_info, **kwargs)


# ── Request logging middleware ─────────────────────────────────────────────────


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        user_id: int | None = None

        # Try to extract user_id from state (set by auth middleware)
        try:
            user_id = request.state.user_id
        except AttributeError:
            pass

        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        log_request(
            method=request.method,
            path=request.url.path,
            user_id=user_id,
            duration_ms=duration_ms,
            status_code=response.status_code,
        )
        return response


# ── Admin log reader ──────────────────────────────────────────────────────────


def get_recent_log_lines(n: int = 100) -> list[str]:
    """Read the last *n* lines from the current log file."""
    log_file = LOGS_DIR / "braincbrain.log"
    if not log_file.exists():
        return []
    with log_file.open("r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    return [ln.rstrip() for ln in lines[-n:]]
