#!/usr/bin/env bash
# Start the BrainC FastAPI server and open the UI

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

# Ensure Ollama is running
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "[*] Starting Ollama service..."
    ollama serve &>/dev/null &
    sleep 2
fi

# Start FastAPI with uvicorn
echo "[*] Starting BrainC API server on http://localhost:8000 ..."
echo "[*] UI available at http://localhost:8000"
echo "[*] Press Ctrl+C to stop."
echo ""

uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
