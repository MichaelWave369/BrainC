#!/usr/bin/env bash
# BrainC Master Setup Script — PHI369 Labs
# Installs all dependencies, builds the model, and starts the server.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║         BrainC — PHI369 Labs         ║"
echo "  ║       Local AI Ecosystem v0.1.0      ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── Step 1: Install Ollama ─────────────────────────────────

echo "━━━ Step 1/5: Checking Ollama ───────────────────────────"
bash "$REPO_ROOT/scripts/install_ollama.sh"

# ── Step 2: Ensure Ollama service is running ───────────────

echo ""
echo "━━━ Step 2/5: Starting Ollama service ───────────────────"
if curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "[ok] Ollama service already running."
else
    echo "[*] Starting Ollama service..."
    ollama serve &>/dev/null &
    OLLAMA_PID=$!
    echo "[*] Waiting for Ollama to be ready..."
    for i in {1..15}; do
        if curl -s http://localhost:11434/api/tags &>/dev/null; then
            echo "[ok] Ollama is ready."
            break
        fi
        sleep 1
        if [ "$i" -eq 15 ]; then
            echo "[!] Ollama didn't start in time. Try running 'ollama serve' manually."
            exit 1
        fi
    done
fi

# ── Step 3: Pull base model ────────────────────────────────

echo ""
echo "━━━ Step 3/5: Checking qwen2.5:14b base model ───────────"
if ollama list | grep -q "qwen2.5:14b"; then
    echo "[ok] qwen2.5:14b already present."
else
    echo "[*] Pulling qwen2.5:14b (~9GB download — grab a coffee)..."
    ollama pull qwen2.5:14b
    echo "[ok] Base model downloaded."
fi

# ── Step 4: Build BrainC model ────────────────────────────

echo ""
echo "━━━ Step 4/5: Building BrainC model ─────────────────────"
bash "$REPO_ROOT/scripts/build_model.sh"

# ── Step 5: Install Python deps ───────────────────────────

echo ""
echo "━━━ Step 5/5: Installing Python dependencies ────────────"

if ! command -v python3 &>/dev/null; then
    echo "[!] Python 3 not found. Install Python 3.11+ and try again."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$PYTHON_VERSION" -lt 11 ]; then
    echo "[!] Python 3.11+ required (found 3.$PYTHON_VERSION)."
    exit 1
fi

# Create virtual environment if not present
if [ ! -d "$REPO_ROOT/.venv" ]; then
    echo "[*] Creating Python virtual environment..."
    python3 -m venv "$REPO_ROOT/.venv"
fi

echo "[*] Installing packages..."
"$REPO_ROOT/.venv/bin/pip" install --quiet --upgrade pip
"$REPO_ROOT/.venv/bin/pip" install --quiet -r "$REPO_ROOT/api/requirements.txt"
echo "[ok] Python dependencies installed."

# ── Launch ─────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete. Starting BrainC..."
echo "  UI: http://localhost:8000"
echo "  API docs: http://localhost:8000/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Open browser if possible
if command -v open &>/dev/null; then
    sleep 2 && open http://localhost:8000 &
elif command -v xdg-open &>/dev/null; then
    sleep 2 && xdg-open http://localhost:8000 &
fi

cd "$REPO_ROOT"
"$REPO_ROOT/.venv/bin/uvicorn" api.main:app --host 0.0.0.0 --port 8000 --reload
