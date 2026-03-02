"""
BrainC global error handling — v1.0
Custom exceptions + FastAPI exception handlers.
"""
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.core.logging import log_error

# ── Custom exception classes ──────────────────────────────────────────────────


class BrainCError(Exception):
    """Base BrainC exception."""
    status_code: int = 500
    default_message: str = "An unexpected error occurred"

    def __init__(self, message: str | None = None, detail: str | None = None):
        self.message = message or self.default_message
        self.detail = detail
        super().__init__(self.message)


class OllamaError(BrainCError):
    status_code = 502
    default_message = "BrainC's brain is offline — is Ollama running?"


class ToolError(BrainCError):
    status_code = 500
    default_message = "A tool encountered an error"


class AuthError(BrainCError):
    status_code = 401
    default_message = "Authentication required"


class RateLimitError(BrainCError):
    status_code = 429
    default_message = "Too many requests — please slow down"


class QueueFullError(BrainCError):
    status_code = 503
    default_message = "BrainC is busy, please try again shortly"


class DatabaseError(BrainCError):
    status_code = 500
    default_message = "Database error — please try again"


# ── Production mode flag ──────────────────────────────────────────────────────

_PRODUCTION = os.getenv("ENV", "production").lower() not in ("development", "dev", "local")


# ── Exception handlers ────────────────────────────────────────────────────────


async def _braincerror_handler(request: Request, exc: BrainCError) -> JSONResponse:
    log_error(exc.message, path=str(request.url.path), status_code=exc.status_code)
    body: dict = {"error": exc.message}
    if exc.detail and not _PRODUCTION:
        body["detail"] = exc.detail
    headers = {}
    if exc.status_code == 429:
        headers["Retry-After"] = "60"
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log_error(
        "Unhandled exception",
        exc_info=True,
        path=str(request.url.path),
        exc_type=type(exc).__name__,
    )
    if _PRODUCTION:
        return JSONResponse(
            status_code=500,
            content={"error": "An internal error occurred — please try again"},
        )
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "type": type(exc).__name__},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BrainCError, _braincerror_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_exception_handler)  # type: ignore[arg-type]
