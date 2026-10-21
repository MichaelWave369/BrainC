```
██████╗ ██████╗  █████╗ ██╗███╗   ██╗ ██████╗
██╔══██╗██╔══██╗██╔══██╗██║████╗  ██║██╔════╝
██████╔╝██████╔╝███████║██║██╔██╗ ██║██║
██╔══██╗██╔══██╗██╔══██║██║██║╚██╗██║██║
██████╔╝██║  ██║██║  ██║██║██║ ╚████║╚██████╗
╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝ ╚═════╝
```

**A fully local AI assistant from the BrainC lineage, now part of the Phi Commons.**
Powered by Ollama · Built by PHI369 Labs · Parallax Division

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![License](https://img.shields.io/badge/license-MIT-blue)
![Status](https://img.shields.io/badge/status-Phi%20Commons-success)

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

## Phi Commons status

BrainC is preserved as an open local-AI runtime and architectural ancestor of the modern PhiOS / PhiVessel stack.

The historical v1.0 README described BrainC as production-grade. Public release does not imply that every dependency, deployment path, or security assumption has been freshly revalidated in 2026. Treat it as runnable software that should be reviewed for the environment in which it is deployed.

The codebase remains valuable as a donor system for local inference, memory, tools, FastAPI/Ollama integration, and local-first interaction patterns.

---

## Contributing

External contributions are welcome under the terms in `CONTRIBUTING.md`.

---

## License

Project-owned BrainC code and documentation are released under the **MIT License** unless otherwise noted.

Third-party dependencies, model weights, and external services retain their upstream licenses. See `THIRD_PARTY_NOTICES.md` and `MODEL_LICENSES.md`.

The pre-Commons proprietary state is preserved in Git history and documented in `LICENSE_HISTORY.md`.

---

*Built with obsession. Everything runs local.*

**© 2026 Parallax — PHI369 Labs Division**


## R9: Offline Skill Passport compatibility (passive)

BrainC can **inspect**, but never automatically trust, PhiLearn Skill Passport v1 files using Python 3.11+ standard library:

    python3 scripts/skill_passport_verify.py path/to/skill-passport.json

This tool validates the 256 KB JSON envelope, locked no-authority policy, six frozen simulated R6 tool-action traces, and R7/R8 SHA-256 consistency checks. It returns REPLAY_PASS_UNTRUSTED or REPLAY_FAIL_UNTRUSTED, and a JSON report with authority NONE and permissions []. Exit 0 means replay consistency only, not an authenticated issuer or a safe agent.

The checker is completely offline, outside FastAPI. It does **not** access or modify BrainC accounts, memory, model routing, tools, code execution, SQLite or Ollama; it adds no API endpoint. Run isolated tests with:

    python3 -m unittest discover -s tests -p 'test_skill_passport_verify.py' -v

An internally consistent transcript can still be fabricated and rehashed. This is not a signature, production competency certificate, tool authorization or internal model training. See PhiLearn interop/README.md for the frozen protocol.


## R10: Optional Ed25519 signed Skill Passport provenance

R10 adds a **read-only offline signature-verification layer** to the existing R8/R9 portable Skill Passport. The outer format is philearn.signed-skill-passport.v1, enclosing an unchanged R8 philearn.skill-passport.v1 record. Signature checking is optional and requires an independently operator-pinned public key; **receiving a public key from the sender is not sufficient authentication**.

### Operator workflow (Node.js 20+)

Run on a trusted operator-owned machine:

    node interop/r10-cli.mjs keygen /secure/operator-dir field-lab
    node interop/r10-cli.mjs sign passport.json /secure/operator-dir/issuer.private.pem field-lab signed.json

Keygen creates a private Ed25519 PEM and a candidate public trust file. The **unencrypted private key** is saved with permission mode 0600, but must be protected using local access controls, excluded from Git, and kept out of shared or cloud-synced directories. For higher-risk signing prefer hardware-backed key protection. The recipient separately authenticates the issuer identity and public key fingerprint through an out-of-band channel, then pins that key in their own local trust-store copy. A key delivered along with an untrusted passport must not be automatically accepted.

Verify using an already authenticated receiver-controlled local trust store:

    node interop/r10-cli.mjs verify signed.json /local/operator-pinned-trust.json

Optional --review is an *explicit inspection acknowledgment*, not a permission change. Unknown keys, revoked/inactive keys, wrong scope, modified payloads, forged signatures or missing evidence fail closed. Without a trust store the signature remains UNPINNED_SIGNATURE. Key revocation is manual at the receiver and never auto-synchronized.

The Ed25519 signature covers a versioned domain separator, issuer ID, SHA-256 DER-SPKI public key fingerprint, claimed signing time and validated R8 passport payload digest. The verifier always validates the six frozen synthetic R6 tool traces and the R7/R8 hashes *before* accepting provenance.

### Consumers and boundaries

- PhiLearn: offline Node 20+ signer/verifier and conformance checks.
- BrainC: offline Python 3.11+ verifier using cryptography; no FastAPI integration.
- SuperPhiVessel: offline Node 20+ verifier; no routing or local-console integration.

In all outcomes, even after a valid pinned-key signature and manual inspection: authority NONE, permissions [], and actionAllowed false. A valid signature confirms use of the matching operator-pinned private key, **not** the historic truth of an editable synthetic benchmark, real-world model ability, changes to weights, an externally attested clock, or permission to execute actions. No signing keys are committed to the repository.

### BrainC invocation

    python3 scripts/r10_verify_signed.py signed.json operator-pinned-trust.json

Install the Python cryptography library before using the standalone verifier. It is also a dependency of BrainC via python-jose[cryptography].


## R11: Governed agent evidence enrollment (inspection-only)

R11 keeps **signing-key identity, demonstrated synthetic benchmark evidence, and operational permissions** as three different concepts. The last remains **completely outside this module**. The receiver cannot enroll anything for action execution, even when every test succeeds.

A standalone receiver-controlled **inspection enrollment registry** records the operator's explicit approval to inspect one exact R10 Ed25519 signed R8 Skill Passport. The review entry is bound to the entire signed envelope's SHA-256, issuer ID, signing key fingerprint, model label, the exact R6 synthetic-only scope, the reviewing operator, and a short lease (1–168 hours). The system replays the six synthetic R6 traces and validates R10's operator-pinned public key every time. The receiving machine's local registry is not a cryptographic credential. Keep it outside shared/untrusted locations.

### Offline operator workflow

Node.js 20+ (PhiLearn or SuperPhiVessel):

    node interop/r11-cli.mjs init local-registry.json
    node interop/r11-cli.mjs check signed.json /local/pinned-keys.json local-registry.json
    node interop/r11-cli.mjs approve signed.json /local/pinned-keys.json local-registry.json operator-id 24 reviewed-registry.json
    node interop/r11-cli.mjs check signed.json /local/pinned-keys.json reviewed-registry.json

To revoke, copy the enrollmentId from your locally approved registry and run:

    node interop/r11-cli.mjs revoke reviewed-registry.json <enrollment-sha256> operator-id revoked-registry.json

BrainC Python 3.11+ with cryptography installed:

    python3 scripts/r11_enrollment.py init local-registry.json
    python3 scripts/r11_enrollment.py approve signed.json /local/pinned-keys.json local-registry.json operator-id 24 reviewed-registry.json
    python3 scripts/r11_enrollment.py check signed.json /local/pinned-keys.json reviewed-registry.json
    python3 scripts/r11_enrollment.py revoke reviewed-registry.json <enrollment-sha256> operator-id revoked-registry.json

All *approve* and *revoke* operations require explicit CLI invocation. Updates are written to new files rather than silently overwriting existing registries; operators decide whether and when to replace the active receiver-controlled file.

### Fail-closed decision states

- SIGNATURE_REJECTED: R10 signer pin or R8/R9 source replay failed.
- REGISTRY_REJECTED / NOT_ENROLLED: absent, malformed, mismatched, or unapproved receiver-local registry.
- NOT_YET_VALID / EXPIRED: local enrollment clock outside the bounded lease.
- REVOKED: operator revoked this exact envelope; same envelope cannot be silently renewed.
- APPROVED_FOR_INSPECTION_ONLY: exact payload, pinned key, valid evidence replay, and receiver's manually approved unexpired inspection lease.

**Invariant:** Every result carries authority NONE, permissions [], actionAllowed false. Even approval authorizes only *local passive evidence inspection*. This is not executable agent enrollment, an access token, deployment approval, a persisted learned skill, or a privilege escalation. No API endpoints, tool bridges, model calls, agent-memory writes, shell execution from evidence, key generation, network exchange, or runtime permission modifications were added by R11. No signing key is checked in.

The registry can be edited by whoever controls the host, and local timestamps depend on that machine's clock. It therefore does not establish an independently verified human approver or trusted time. A more advanced release would require authenticated operator decisions, tamper-evident log storage, key lifecycle operations and a separate real-world action policy gate before permitting any tool execution.


## R12: Tamper-evident, operator-signed governance event ledger

R12 adds a **separate, offline operator event history** on top of R10 pinned-key provenance and R11 inspection-only enrollment. It is intentionally **not** wired into live BrainC or Vessie APIs, agents, model routing, memory, authorization or tooling.

The event log's scope is limited to **inspection of evidence**. It records an operator-signed event for APPROVE_INSPECTION, REVOKE_INSPECTION, or EXPIRE_INSPECTION, with an incrementing sequence number, SHA-256 of the prior signed event, exact signed passport envelope hash, pinned issuer key fingerprint, model label, claim scope, reviewing operator's pinned Ed25519 key fingerprint, timestamp, and bounded expiry (at most seven days).

A receiver independently validates every Ed25519 event signature using a **separate, operator-controlled R12 public-key trust store**, reconstructs the hash-linked chain, validates state transitions, compares the entire event chain with an **independently preserved checkpoint** (event count + head SHA-256), and then rechecks the underlying R10 signed passport and R6 synthetic replay. A changed, reordered, forged, truncated or stale log is rejected when the receiver has the authentic latest checkpoint. A signed revocation or explicit expiry is terminal for that exact enrollment.

**Critical limitations:** The chain alone does not prevent deletion or rewriting. If an attacker can also replace the receiver's checkpoint or pinned keys, a local verification cannot detect all tampering. Keep the latest known head independently from the writable ledger, ideally replicated to independent protected storage. Ed25519 authenticates possession of a pinned operator signing key, not an independently verified human identity or honest historical action. Local timestamps are untrusted. All CLI operations create new files, not silent in-place overwrites. Private operator keys must be generated and stored outside Git or synced folders.

**Invariant:** Even a valid checkpointed and operator-approved report returns authority NONE, permissions [], actionAllowed false. It authorizes *passive evidence inspection only*. No runtime permissions, agent tool grants, live deployment approval, memory-writing, or model execution exist in R12.

### Operator commands

The full offline signing and event-authoring CLI is included with PhiLearn:

    node interop/r12-cli.mjs operator-keygen /secure/outside-repo/dir operator.alpha
    node interop/r12-cli.mjs init new-ledger.json new-checkpoint.json
    node interop/r12-cli.mjs approve signed.json R10-pinned-keys.json R12-operator-keys.json ledger.json operator-private.pem operator.alpha 24 prior-checkpoint.json next-ledger.json next-checkpoint.json --confirm
    node interop/r12-cli.mjs revoke enrollment-sha256 R12-operator-keys.json ledger.json operator-private.pem operator.alpha prior-checkpoint.json next-ledger.json next-checkpoint.json --confirm
    node interop/r12-cli.mjs expire enrollment-sha256 R12-operator-keys.json ledger.json operator-private.pem operator.alpha prior-checkpoint.json next-ledger.json next-checkpoint.json --confirm
    node interop/r12-cli.mjs check signed.json R10-pinned-keys.json R12-operator-keys.json ledger.json independent-checkpoint.json

The operator-keygen command creates an **unencrypted** mode-0600 private key PEM and a candidate public trust-store JSON. Recipients must verify and pin the public key through a separate authenticated process before accepting it. Do not commit either real private keys or approvals as authorization credentials. Explicit event expiry is optional because elapsed lease expiry is enforced during verification even without a new event.

BrainC has its own Python 3.11+ standard-library/cryptography implementation in scripts/r12_governance.py. SuperPhiVessel includes a passive read-only Node verifier in interop/r12-check.mjs, with the matching shared Node event-chain implementation. These implementations deliberately **do not connect** the ledger to real privileges.

Only signature-chain consistency, separately known head continuity, and synthetic-evidence replay are established. This remains a research governance audit, not a trustworthy external authorization system.


### BrainC Python CLI

    python3 scripts/r12_governance.py init ledger.json head.json
    python3 scripts/r12_governance.py approve signed.json R10-trust.json R12-operator-trust.json ledger.json private-key.pem operator.alpha 24 head.json new-ledger.json new-head.json --confirm
    python3 scripts/r12_governance.py revoke enrollment-id R12-operator-trust.json ledger.json private-key.pem operator.alpha head.json new-ledger.json new-head.json --confirm
    python3 scripts/r12_governance.py check signed.json R10-trust.json R12-operator-trust.json ledger.json independently-saved-head.json

This CLI requires the already-used Python cryptography dependency. Signing keys are operator-provided local files and never loaded into BrainC's FastAPI, SQLite or agent tools.
