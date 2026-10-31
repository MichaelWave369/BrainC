# BrainC → PhiServe: local inference adapter

## Purpose

BrainC can now select either its original Ollama backend (default) or the existing PhiServe GGUF daemon (**opt-in**). This does not bundle or train weights. The `model/Modelfile` starts from `qwen2.5:14b`, which is an Ollama recipe, **not** a GGUF or additional checkpoint in this repository.

BrainC keeps its JWT/session authorization, existing user preferences, SQLite conversation ownership, message memory, semantic retrieval, optional tool gating, response UI, summarization, and audited admin model selection. Only inference transport, catalog lookup, and readiness are selected.

## Setup on the same Windows/Linux computer

You need a local licensed GGUF checkpoint registered in PhiServe with an actual alias, a separately installed compatible llama.cpp `llama-server`, and a PhiServe private token.

Run PhiServe locally:

~~~powershell
phiserve models list
phiserve auth create --output "$HOME/.phiserve/bridge-token.txt"
phiserve daemon --llama-server "C:\\path\\to\\llama-server.exe" --browser-origin "http://127.0.0.1:8000" --api-key-file "$HOME/.phiserve/bridge-token.txt"
~~~

PhiServe must be started with `--browser-origin` and `--api-key-file` together for bearer enforcement. BrainC's Python backend is a server-side client and does not send an Origin header; the browser-origin argument is **not** a request for LAN access. To use the PhiServe React console at the same time, select its trusted origin and understand that the allowlist is an exact, single origin. No wildcard CORS.

In BrainC's private root `.env` (never commit this file), set:

~~~ini
BRAINC_INFERENCE_BACKEND=phiserve
PHISERVE_BASE_URL=http://127.0.0.1:11435
PHISERVE_TOKEN_FILE=C:\\Users\\YOUR_USER\\.phiserve\\bridge-token.txt
PHISERVE_MODEL=YOUR_REGISTERED_GGUF_ALIAS
~~~

Do not put the bearer-token **contents** into `.env`, page scripts, URLs or command-line args. The backend reads only the selected private file; on POSIX it rejects group/world-readable token permissions. `PHISERVE_BASE_URL` rejects remote/network hosts, URL credentials, query strings and paths.

Restart BrainC after selecting the backend. Its model catalog, admin switch route, readiness and chat all use this exact selected local provider. There is **no automatic fallback** to Ollama, another GGUF, Kimi or remote API if PhiServe is busy, unavailable, unauthorized, or returns incomplete frames. HTTP 409/503 are surfaced as failure states. Model switching does not grant the application any new tool permissions.

### Keeping BrainC's identity

For Ollama, the canonical `braincbrain` Modelfile already encodes the BrainC SYSTEM persona. **For PhiServe**, BrainC injects the checked-in `model/system_prompt.md` into the request as a system message; it can also include the user's existing `system_prompt_override` without changing it. No application state or user data is stored in PhiServe by this adapter. The GGUF itself does not become a renamed or retrained BrainC checkpoint.

User preferences that still say `braincbrain` are mapped to the selected PhiServe active alias. User-selected **other** aliases must genuinely be registered with PhiServe, or the request fails. Admin `/models/switch` remains authenticated and audited.

### What stays separate

- SQLite history and semantic search remain in BrainC. Embeddings still use BrainC's existing sentence-transformers model and may require separate local assets; PhiServe does not magically supply embeddings.
- Existing BrainC tool selection/execution stays under BrainC's existing `tools_enabled` request logic. Provider responses are text only; no tool execution is added to PhiServe.
- Conversation summarization uses the same selected provider; nonempty complete response required before old messages can be compacted.
- PhiStream experimental safetensors models are **not** valid live PhiServe GGUF aliases.
- This integration does **not** prove GPU acceleration or physically execute model weights in GitHub CI.

## Acceptance

CI runs isolated HTTP-stub contract checks (no checkpoint downloads, no CUDA or calls to the real daemon) on Windows/Ubuntu Python 3.11/3.13.

The remaining operator field test: start PhiServe and BrainC on the same trusted PC, select a real GGUF alias, send a two-turn conversation through authenticated BrainC UI, test summary and /models, then stop PhiServe and verify that the system fails closed. Confirm the correct prompt persona and that generated responses remain BrainC-owned memory.

**Security note:** BrainC's existing tool executor is outside the scope of this PR. Selecting a local model does not by itself make arbitrary code execution safe. Keep the existing user/role/tool boundaries under review.
