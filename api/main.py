"""
BrainC API — v1.0.0 Production Release
PHI369 Labs — Parallax Division
"""
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limiter
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from api.auth.routes import router as auth_router
from api.auth.sessions import router as sessions_router
from api.config import ENV, OLLAMA_BASE_URL
from api.core.audit import ensure_audit_table
from api.core.backup import router as backups_router, start_backup_scheduler
from api.core.errors import register_error_handlers
from api.core.health import router as health_router
from api.core.logging import RequestLoggingMiddleware, log
from api.core.migrations import run_migrations
from api.core.queue import active_model_name, set_active_model
from api.core.rate_limiter import limiter, rate_limit_exceeded_handler
from api.mcp.server import router as mcp_router
from api.routes.chat import router as chat_router
from api.routes.conversations import router as conversations_router
from api.routes.memory import init_db
from api.routes.models import router as models_router
from api.routes.preferences import router as preferences_router
from api.routes.tools import router as tools_router

_PRODUCTION = ENV.lower() not in ("development", "dev", "local")

# ── Startup / shutdown ────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize DB (legacy inline schema)
    await init_db()

    # 2. Run SQL migrations
    applied = await run_migrations()
    if applied:
        log.info("migrations_applied", count=len(applied), names=applied)
    else:
        log.info("migrations_up_to_date")

    # 3. Ensure audit table
    await ensure_audit_table()

    # 4. Set initial active model from env
    model_from_env = os.getenv("ACTIVE_MODEL", "braincbrain")
    set_active_model(model_from_env)
    log.info("active_model_loaded", model=model_from_env)

    # 5. Pre-warm Ollama with a silent ping
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.get(f"{OLLAMA_BASE_URL}/api/tags")
        log.info("ollama_prewarm_ok", url=OLLAMA_BASE_URL)
    except Exception as exc:
        log.warning("ollama_prewarm_failed", error=str(exc))

    # 6. Start backup scheduler
    backup_task = start_backup_scheduler()
    log.info("backup_scheduler_started")

    log.info("braincbrain_started", version="1.0.0", env=ENV)
    yield

    backup_task.cancel()
    log.info("braincbrain_stopped")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="BrainC API",
    description="Local AI ecosystem — PHI369 Labs / Parallax Division",
    version="1.0.0",
    lifespan=lifespan,
    # Hide docs in production
    docs_url=None if _PRODUCTION else "/docs",
    redoc_url=None if _PRODUCTION else "/redoc",
)

# ── Rate limiter state ────────────────────────────────────────────────────────

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]

# ── Error handlers ────────────────────────────────────────────────────────────

register_error_handlers(app)

# ── Middleware stack (order matters — outermost first) ────────────────────────

# 1. GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 2. Request logging
app.add_middleware(RequestLoggingMiddleware)

# 3. Security headers
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# 4. Input sanitization — strip null bytes and control characters from query strings
class InputSanitizationMiddleware(BaseHTTPMiddleware):
    _CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

    async def dispatch(self, request: Request, call_next):
        # Sanitize query string
        raw_qs = request.url.query
        if raw_qs and self._CTRL.search(raw_qs):
            return JSONResponse(status_code=400, content={"error": "Invalid characters in request"})
        return await call_next(request)

app.add_middleware(InputSanitizationMiddleware)

# 5. CORS — locked to localhost in production
_origins = (
    ["http://localhost", "http://127.0.0.1", "http://localhost:8000", "http://127.0.0.1:8000"]
    if _PRODUCTION
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Tool-Used", "X-Tool-Query", "X-Tool-Result", "X-Queue-Position"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(preferences_router)
app.include_router(models_router)
app.include_router(chat_router, tags=["chat"])
app.include_router(conversations_router)
app.include_router(tools_router)
app.include_router(mcp_router)
app.include_router(backups_router)

# ── Static UI ─────────────────────────────────────────────────────────────────

UI_DIR = Path(__file__).parent.parent / "ui"
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")

    @app.get("/", include_in_schema=False)
    async def serve_ui():
        return FileResponse(str(UI_DIR / "index.html"))

    @app.get("/login", include_in_schema=False)
    async def serve_login():
        return FileResponse(str(UI_DIR / "login.html"))

    @app.get("/admin", include_in_schema=False)
    async def serve_admin():
        return FileResponse(str(UI_DIR / "admin.html"))

# ── Dev-only routes ───────────────────────────────────────────────────────────

if not _PRODUCTION:
    from fastapi import HTTPException
    from api.auth.middleware import require_admin as _require_admin

    @app.post("/admin/test-error", tags=["admin"])
    async def test_error(_admin: dict = _require_admin):
        raise RuntimeError("Test error — error handling is working correctly")
