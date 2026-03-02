# BrainC configuration — PHI369 Labs — v1.0
import os
from pathlib import Path

# Load .env from repo root if present
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        pass

# ── Chat / memory settings ────────────────────────────────────────────────────

MAX_TURNS_BEFORE_SUMMARY: int = 20
EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
TOP_K_SEMANTIC: int = 3

# ── Auth settings ─────────────────────────────────────────────────────────────

SECRET_KEY: str = os.getenv("SECRET_KEY", "")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
MAX_SESSIONS_PER_USER: int = int(os.getenv("MAX_SESSIONS_PER_USER", "5"))
ALLOW_REGISTRATION: bool = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"

# ── Ollama ────────────────────────────────────────────────────────────────────

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ── Inference queue ───────────────────────────────────────────────────────────

MAX_QUEUE_SIZE: int = int(os.getenv("MAX_QUEUE_SIZE", "10"))
QUEUE_TIMEOUT_SECONDS: float = float(os.getenv("QUEUE_TIMEOUT_SECONDS", "120"))

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
ENV: str = os.getenv("ENV", "production")

# ── Security ──────────────────────────────────────────────────────────────────

# Comma-separated list of allowed hostnames (production)
ALLOWED_HOSTS: list[str] = [
    h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]

# Maximum request body sizes (bytes)
MAX_CHAT_BODY_SIZE: int = int(os.getenv("MAX_CHAT_BODY_SIZE", str(1 * 1024 * 1024)))    # 1 MB
MAX_UPLOAD_BODY_SIZE: int = int(os.getenv("MAX_UPLOAD_BODY_SIZE", str(10 * 1024 * 1024)))  # 10 MB
