from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes.chat import router as chat_router
from api.routes.conversations import router as conversations_router
from api.routes.memory import init_db
from api.routes.tools import router as tools_router
from api.mcp.server import router as mcp_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="BrainC API",
    description="Local AI ecosystem by PHI369 Labs — powered by Ollama + qwen2.5:14b",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Tool-Used", "X-Tool-Query", "X-Tool-Result"],
)

app.include_router(chat_router, tags=["chat"])
app.include_router(conversations_router)
app.include_router(tools_router)
app.include_router(mcp_router)

# Serve the UI as static files
UI_DIR = Path(__file__).parent.parent / "ui"
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")

    @app.get("/", include_in_schema=False)
    async def serve_ui():
        return FileResponse(str(UI_DIR / "index.html"))


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "model": "braincbrain", "version": "0.4.0"}
