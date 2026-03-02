```
██████╗ ██████╗  █████╗ ██╗███╗   ██╗ ██████╗
██╔══██╗██╔══██╗██╔══██╗██║████╗  ██║██╔════╝
██████╔╝██████╔╝███████║██║██╔██╗ ██║██║
██╔══██╗██╔══██╗██╔══██║██║██║╚██╗██║██║
██████╔╝██║  ██║██║  ██║██║██║ ╚████║╚██████╗
╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝ ╚═════╝
```

**A production-grade, fully local AI assistant.**
Powered by Ollama · Built by PHI369 Labs · Parallax Division

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![License](https://img.shields.io/badge/license-Proprietary-red)
![Status](https://img.shields.io/badge/status-Production-success)

---

## What is BrainC?

BrainC is a self-hosted, privacy-first AI assistant that runs entirely on your local machine. No cloud. No telemetry. No API keys.

- **Frontend:** Vanilla JS chat UI with real-time streaming
- **Backend:** FastAPI (Python 3.11+)
- **AI Engine:** Ollama (any local model — default: `braincbrain`)
- **Memory:** SQLite with semantic search (sentence-transformers)
- **Tools:** Web search, code execution, file reading, notes, calendar

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         BrainC v1.0.0                           │
│                      PHI369 Labs / Parallax                     │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend                           │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
│  │  Auth    │  │  Chat    │  │  Memory   │  │  Tools       │  │
│  │  JWT     │  │  Stream  │  │  SQLite   │  │  Search      │  │
│  │  Refresh │  │  Queue   │  │  Semantic │  │  Executor    │  │
│  │  RBAC    │  │  Model   │  │  Embeds   │  │  Files/Notes │  │
│  └──────────┘  └──────────┘  └───────────┘  └──────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Core (v1.0)                                             │  │
│  │  logging · health · rate_limiter · queue · errors        │  │
│  │  migrations · audit · backup                             │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
          │                          │
          ▼                          ▼
┌─────────────────┐        ┌──────────────────┐
│  Ollama Engine  │        │  SQLite DB       │
│  braincbrain    │        │  memory/         │
│  (local LLM)   │        │  conversations.db │
└─────────────────┘        └──────────────────┘
          │
          ▼
┌─────────────────┐
│  SearXNG        │
│  (web search)   │
│  localhost:8080 │
└─────────────────┘
```

---

## Changelog

### v1.0.0 — Production Release (2026-03-02)
- Structured JSON logging with structlog + daily rotation (30 days)
- `GET /health`, `GET /health/ready`, `GET /admin/stats` endpoints
- Rate limiting via slowapi: per-user and per-IP limits
- Asyncio inference queue (max 10 concurrent Ollama requests)
- Runtime model switching: `GET/POST /models` — no restart needed
- Global error handling with custom exception classes
- Formal SQL migration system (`scripts/migrations/`)
- Security audit log table + `GET /admin/audit` endpoint
- Automated daily backups (3am UTC) to `backups/`
- Docker multi-stage production build + docker-compose
- CLI management tool (`scripts/braincbrain-cli.py`)
- Security headers middleware (X-Frame-Options, CSP, etc.)
- CORS locked to localhost in production
- Input sanitization middleware
- GZip response compression
- Ollama pre-warm on startup
- Admin panel: Chart.js stats, audit viewer, log viewer, backup manager
- Chat UI: status bar, model switcher dropdown, toast notifications
- Skeleton loaders, keyboard shortcuts (Ctrl+N, Ctrl+K, Esc)

### v0.5.0 — Multi-User & Auth
- JWT auth (access + refresh tokens)
- Per-user conversation isolation
- Session management (max 5 sessions/user)
- Admin panel with user management
- RBAC: admin / user roles

### v0.4.0 — API Integrations
- Web search via SearXNG (self-hosted)
- Code execution sandbox
- File reading tool
- MCP (Model Context Protocol) server & client
- Notes and calendar tools

### v0.3.0 — Fine-Tuning Pipeline
- Dataset collection from conversation history
- LoRA fine-tuning with Axolotl / Unsloth
- GGUF export to Ollama
- A/B testing framework

### v0.2.0 — Memory Expansion
- Semantic search using sentence-transformers
- Conversation summarization (auto at 20+ turns)
- Embedding persistence in SQLite
- Cross-conversation memory retrieval

### v0.1.0 — Foundation
- FastAPI backend with Ollama streaming
- SQLite conversation history
- Basic chat UI
- Ollama model integration

---

## Quick Start

### Bare Metal

```bash
# 1. Clone the repo
git clone https://github.com/MichaelWave369/BrainC.git
cd BrainC

# 2. Install Ollama
bash scripts/install_ollama.sh

# 3. Build the BrainC model
bash scripts/build_model.sh

# 4. Set up Python environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt

# 5. Configure environment
cp .env.example .env
# Edit .env — set SECRET_KEY:
python -c "import secrets; print(secrets.token_hex(32))"

# 6. Run database migrations
python scripts/migrate.py

# 7. Start BrainC
bash scripts/start.sh
# Open http://localhost:8000
```

### Docker

```bash
# Production stack
docker compose -f docker/docker-compose.yml up -d

# Development with hot reload
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up

# View logs
docker compose -f docker/docker-compose.yml logs -f braincbrain-api
```

---

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | — | Liveness check |
| GET | `/health/ready` | — | Readiness + Ollama + DB |
| POST | `/auth/register` | — | Register user |
| POST | `/auth/login` | — | Login (returns tokens) |
| POST | `/auth/refresh` | — | Refresh access token |
| POST | `/auth/logout` | Bearer | Logout |
| GET | `/auth/me` | Bearer | Current user profile |
| GET | `/auth/users` | Admin | List all users |
| POST | `/auth/users` | Admin | Create user |
| DELETE | `/auth/users/{id}` | Admin | Delete user |
| POST | `/auth/users/{id}/reset-password` | Admin | Reset password |
| POST | `/chat` | Bearer | Send message (streaming) |
| GET | `/history` | Bearer | Conversation history |
| DELETE | `/history` | Bearer | Clear conversation |
| GET | `/search` | Bearer | Semantic search |
| GET | `/conversations` | Bearer | List conversations |
| PUT | `/conversations/{id}` | Bearer | Update conversation |
| DELETE | `/conversations/{id}` | Bearer | Delete conversation |
| GET | `/models` | Bearer | List available models |
| GET | `/models/active` | Bearer | Get active model |
| POST | `/models/switch` | Admin | Switch active model |
| GET | `/tools/notes` | Bearer | List notes |
| POST | `/tools/notes` | Bearer | Create note |
| POST | `/tools/search` | Bearer | Web search |
| POST | `/tools/execute` | Bearer | Execute code |
| GET | `/preferences` | Bearer | Get user preferences |
| PUT | `/preferences` | Bearer | Update preferences |
| GET | `/sessions` | Bearer | List sessions |
| DELETE | `/sessions/{id}` | Bearer | Revoke session |
| GET | `/admin/stats` | Admin | System statistics |
| GET | `/admin/logs` | Admin | Last 100 log lines |
| GET | `/admin/audit` | Admin | Security audit log |
| GET | `/admin/backups` | Admin | List backups |
| POST | `/admin/backups/trigger` | Admin | Create backup |
| POST | `/admin/backups/restore` | Admin | Restore backup |

---

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| POST /chat | 60 req/min per user |
| POST /tools/execute | 10 req/min per user |
| GET /tools/search | 30 req/min per user |
| POST /auth/login | 5 req/15min per IP |
| POST /auth/register | 3 req/hour per IP |

Admin users are exempt from all rate limits.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *required* | JWT signing secret |
| `ENV` | `production` | `production` or `development` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API URL |
| `ACTIVE_MODEL` | `braincbrain` | Default inference model |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING / ERROR |
| `MAX_QUEUE_SIZE` | `10` | Max queued Ollama requests |
| `QUEUE_TIMEOUT_SECONDS` | `120` | Queue request timeout (s) |
| `ALLOW_REGISTRATION` | `true` | Enable public registration |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Access token TTL (24h) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `MAX_SESSIONS_PER_USER` | `5` | Max concurrent sessions |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Allowed hosts (production) |

---

## CLI Management

```bash
# Users
python scripts/braincbrain-cli.py users list
python scripts/braincbrain-cli.py users create alice
python scripts/braincbrain-cli.py users delete alice
python scripts/braincbrain-cli.py users reset-password alice

# Database
python scripts/braincbrain-cli.py db stats
python scripts/braincbrain-cli.py db backup
python scripts/braincbrain-cli.py db restore braincbrain-20260302_030000.tar.gz

# Models
python scripts/braincbrain-cli.py model list
python scripts/braincbrain-cli.py model switch braincbrain-ft

# Logs
python scripts/braincbrain-cli.py logs tail
```

---

## Project Structure

```
BrainC/
├── api/
│   ├── core/               # v1.0 production modules
│   │   ├── logging.py      # structlog + daily rotation
│   │   ├── health.py       # health & observability
│   │   ├── rate_limiter.py # slowapi rate limiting
│   │   ├── queue.py        # asyncio inference queue
│   │   ├── errors.py       # global error handling
│   │   ├── migrations.py   # SQL migration system
│   │   ├── audit.py        # security audit log
│   │   └── backup.py       # automated backups
│   ├── auth/               # JWT auth, middleware, sessions
│   ├── routes/             # chat, conversations, models, etc.
│   ├── mcp/                # Model Context Protocol
│   ├── tools/              # search, executor, file_reader, notes
│   ├── models/             # Pydantic schemas
│   ├── config.py           # centralized configuration
│   ├── main.py             # FastAPI app + middleware stack
│   └── requirements.txt
├── docker/
│   ├── Dockerfile           # multi-stage build
│   ├── docker-compose.yml   # production stack
│   └── docker-compose.dev.yml
├── finetune/               # LoRA training pipeline
├── logs/                   # rotating log files (gitignored)
├── backups/                # database backups (gitignored)
├── memory/                 # conversations.db (gitignored)
├── model/                  # Ollama Modelfile + system prompt
├── scripts/
│   ├── migrations/         # SQL migration files (001-007)
│   ├── braincbrain-cli.py  # management CLI
│   ├── migrate.py          # standalone migration runner
│   ├── start.sh
│   └── build_model.sh
├── tools/
│   └── searxng/            # self-hosted web search
├── ui/                     # vanilla JS chat interface
│   ├── index.html          # main chat UI
│   ├── admin.html          # admin panel
│   ├── login.html          # login page
│   ├── app.js              # chat logic
│   └── style.css           # design system
└── workspace/
    └── notes/              # user notes
```

---

## Security

- **Auth:** JWT with short-lived access tokens + long-lived refresh tokens
- **Passwords:** bcrypt hashing
- **Rate limiting:** Per-user (authenticated) and per-IP (anonymous)
- **Headers:** X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy
- **CORS:** Locked to localhost in production
- **Input:** Null bytes and control characters stripped
- **Audit log:** Append-only; no delete endpoint
- **Stack traces:** Never exposed to clients in production

---

## Performance Tuning

- **Queue:** `MAX_QUEUE_SIZE=10` serializes GPU requests. Increase if you have VRAM headroom.
- **Summarization:** Auto-triggers at `MAX_TURNS_BEFORE_SUMMARY=20`. Reduce for smaller context.
- **Semantic retrieval:** `TOP_K_SEMANTIC=3`. Lower = faster, less context.
- **Indexes:** Migration `005` adds indexes on hot columns.
- **GZip:** All responses ≥1KB compressed automatically.
- **Pre-warm:** Model loaded in memory before first request.

---

## Roadmap (Post v1.0)

- **v1.1** — Voice: Whisper STT + local TTS
- **v1.2** — Plugin system: hot-loadable tools
- **v1.3** — Multi-modal: image input (LLaVA / Qwen-VL)
- **v1.4** — Collaboration: shared workspaces
- **v1.5** — Mobile: React Native app
- **v2.0** — Distributed: multi-node cluster

---

## Contributing

Internal PHI369 Labs project. External contributions not accepted.

---

## License

Proprietary — © 2026 Parallax — PHI369 Labs Division

All rights reserved. Unauthorized use, reproduction, or distribution is strictly prohibited.

---

*Built with obsession. Everything runs local.*

**© 2026 Parallax — PHI369 Labs Division**
