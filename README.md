# BrainC

**BrainC is a project by PHI369 Labs, the technology division of Parallax.**

---

## Changelog

### v0.3.0 — Fine-Tuning Pipeline ✅
- **Dataset collection** (`finetune/collect.py`) — exports conversation history to Alpaca and ShareGPT formats with quality filtering (`--min-words` flag).
- **Dataset analyzer** (`finetune/analyze_dataset.py`) — reports length distributions, flags duplicates and short outputs, warns if dataset is under 500 pairs.
- **Unsloth training script** (`finetune/train_unsloth.py`) — LoRA fine-tuning on `Qwen2.5-14B-Instruct` with bf16, gradient checkpointing, and automatic adapter merge.
- **Axolotl config** (`finetune/axolotl_config.yml`) — production-ready YAML for multi-GPU / Axolotl workflows.
- **GGUF export** (`finetune/export_to_ollama.py`) — converts merged model to Q4_K_M GGUF via llama.cpp, generates Modelfile, registers as `braincbrain-ft` in Ollama.
- **A/B testing framework** (`finetune/ab_test.py`) — side-by-side terminal comparison of any two Ollama models with response-length and time-per-word metrics; results saved to JSON.
- **Test prompt set** (`finetune/test_prompts.txt`) — 10 curated prompts covering reasoning, tone, epistemic honesty, pushback resistance, and prose style.

### v0.2.0 — Memory Expansion ✅
- **Semantic search** over conversation history using `all-MiniLM-L6-v2` (local, no API key). Embeddings stored as BLOBs in SQLite. Top-3 relevant past exchanges injected into every prompt.
- New route: `GET /search?q=<query>` — returns semantically similar past messages.
- **Context window management** — conversations exceeding 20 turns trigger automatic summarization of the oldest 10 turns via BrainC itself. Summary stored with `role: "summary"` and injected at the start of the context window.
- **Conversation metadata** — new `conversations` table with `id`, `title`, `created_at`, `updated_at`, `tags`. Titles auto-generated from the first 6 words of the opening message.
- New routes: `GET /conversations`, `PATCH /conversations/{id}`, `DELETE /conversations/{id}`.
- **UI sidebar** — left panel showing conversation list with titles, relative timestamps, and tag badges. "New Chat" button starts a fresh session. Clicking a conversation loads it.

### v0.1.0 — Initial Scaffold
- FastAPI backend with streaming chat and SQLite memory.
- Custom `braincbrain` model via Ollama (qwen2.5:14b base).
- Dark minimal web UI with conversation switching.

BrainC is a production-quality, privacy-first AI assistant that runs entirely on your hardware. No API keys. No cloud dependencies. No data leaving your machine. It pairs a custom-tuned Ollama model (built on `qwen2.5:14b`) with a streaming FastAPI backend and a clean, minimal web interface.

---

## What Is BrainC?

BrainC is a project by PHI369 Labs, the technology division of Parallax — designed to behave like a thoughtful, direct, non-sycophantic assistant rather than a default chatbot. The system prompt is carefully engineered to produce responses that are honest, prose-forward, and useful — with real pushback when needed.

The architecture is intentionally simple: Ollama handles model inference, FastAPI handles the API and streaming, SQLite handles conversation memory, and a single-file web UI handles the interface. No Docker required. No cloud required. Just your GPU and a terminal.

---

## Requirements

- **Ollama** — [ollama.com](https://ollama.com) (auto-installed by `setup.sh`)
- **Python 3.11+**
- **12GB VRAM** recommended (for `qwen2.5:14b`; an 8B variant works on 8GB)
- **~9GB disk space** for the base model download
- macOS or Linux

---

## Quick Start

```bash
git clone <this-repo>
cd BrainC
./setup.sh
```

`setup.sh` handles everything:

1. Installs Ollama if missing
2. Pulls `qwen2.5:14b` from Ollama's registry
3. Builds the `braincbrain` model from the Modelfile
4. Creates a Python virtual environment and installs dependencies
5. Starts the FastAPI server and opens the UI

The UI will be available at **http://localhost:8000**.

---

## Architecture

```
BrainC/
├── model/
│   ├── Modelfile          # Ollama model definition
│   ├── system_prompt.md   # BrainC's personality and behavior rules
│   └── test_prompts.sh    # Personality verification test suite
├── api/
│   ├── main.py            # FastAPI app entry point
│   ├── requirements.txt   # Python dependencies
│   ├── routes/
│   │   ├── chat.py        # POST /chat — streaming inference
│   │   └── memory.py      # SQLite read/write helpers
│   └── models/
│       └── schemas.py     # Pydantic request/response schemas
├── ui/
│   ├── index.html         # Single-page chat interface
│   ├── style.css          # Dark theme, minimal design
│   └── app.js             # Streaming SSE client, history loading
├── memory/
│   └── conversations.db   # Auto-created SQLite database
├── scripts/
│   ├── install_ollama.sh  # Ollama installer (Mac/Linux)
│   ├── build_model.sh     # Rebuild the braincbrain model
│   └── start.sh           # Start API server only
└── setup.sh               # Master setup + launch script
```

**Request flow:**
```
Browser → FastAPI (port 8000) → Ollama API (port 11434) → qwen2.5:14b
                ↕
           SQLite (memory/)
```

Responses are streamed token-by-token from Ollama through the FastAPI `StreamingResponse` to the browser. Conversation history is persisted to SQLite and loaded on page refresh.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat` | Send a message, stream the response |
| `GET` | `/history` | Get conversation history |
| `DELETE` | `/history` | Clear conversation history |
| `GET` | `/search?q=` | Semantic search over all past messages |
| `GET` | `/conversations` | List all conversations with metadata |
| `PATCH` | `/conversations/{id}` | Update title or tags |
| `DELETE` | `/conversations/{id}` | Delete a conversation and its messages |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Interactive API docs (Swagger UI) |

**POST /chat — request body:**
```json
{
  "message": "Explain the CAP theorem.",
  "conversation_id": "default"
}
```

**GET /history — query params:**
```
?conversation_id=default
```

---

## Customizing the System Prompt

Edit `model/system_prompt.md` to change BrainC's personality, then rebuild the model:

```bash
./scripts/build_model.sh
```

The system prompt is embedded directly into the Ollama Modelfile during the build step.

---

## Running Tests

Verify BrainC's personality is dialed in:

```bash
./model/test_prompts.sh
```

This runs 10 curated prompts through the Ollama CLI and prints results for manual review. Tests cover tone, directness, uncertainty handling, sycophancy resistance, step-by-step reasoning, and more.

---

## Fine-Tuning

BrainC v0.3 includes a complete pipeline for fine-tuning the model on your
own conversation history. See **[finetune/README.md](finetune/README.md)** for
the full guide.

**Quick workflow:**

```bash
python finetune/collect.py          # 1. export dataset
python finetune/analyze_dataset.py  # 2. check quality
python finetune/train_unsloth.py    # 3. train LoRA adapter
python finetune/export_to_ollama.py # 4. convert to GGUF + register
python finetune/ab_test.py          # 5. compare base vs fine-tuned
```

---

## Scripts

| Script | Purpose |
|--------|---------|
| `./setup.sh` | Full setup + launch (start here) |
| `./scripts/start.sh` | Start the API server only |
| `./scripts/build_model.sh` | Rebuild the braincbrain model |
| `./scripts/install_ollama.sh` | Install Ollama only |
| `./model/test_prompts.sh` | Run personality test suite |

---

## Roadmap

**v0.2 — Memory Expansion** ✅ _complete_
- Semantic search over conversation history using local embeddings
- Configurable context window management (summarize old turns)
- Per-conversation metadata and tagging

**v0.3 — Fine-Tuning Pipeline** ✅ _complete_
- Dataset collection tooling from conversation history
- LoRA fine-tuning scripts for custom behavior
- A/B testing framework for prompt and model variants

**v0.4 — API Integrations**
- Local tool use: web search (SearXNG), code execution, file reading
- Calendar and notes integration via local APIs
- MCP (Model Context Protocol) server support

**v0.5 — Multi-User / Auth**
- Basic authentication for shared-machine deployments
- Per-user conversation isolation
- Session management

**v1.0 — Production Hardening**
- Proper logging and observability
- Rate limiting and request queuing
- Configurable model switching at runtime

---

## License

© 2026 Parallax — PHI369 Labs Division. All Rights Reserved. Proprietary and confidential.
