#!/usr/bin/env bash
# Build or rebuild the BrainC model from the Modelfile

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
MODELFILE="$REPO_ROOT/model/Modelfile"

echo "[*] Building BrainC model..."

if [ ! -f "$MODELFILE" ]; then
    echo "[!] Modelfile not found at $MODELFILE"
    exit 1
fi

if ! command -v ollama &>/dev/null; then
    echo "[!] Ollama is not installed. Run scripts/install_ollama.sh first."
    exit 1
fi

# Ensure the base model is available
echo "[*] Checking for qwen2.5:14b base model..."
if ! ollama list | grep -q "qwen2.5:14b"; then
    echo "[*] Pulling qwen2.5:14b (this may take a while on first run)..."
    ollama pull qwen2.5:14b
fi

# Remove existing model if present (clean rebuild)
if ollama list | grep -q "braincbrain"; then
    echo "[*] Removing existing braincbrain model for clean rebuild..."
    ollama rm braincbrain || true
fi

echo "[*] Creating braincbrain from Modelfile..."
ollama create braincbrain -f "$MODELFILE"

echo ""
echo "[ok] BrainC model built successfully."
echo "     Test with: ollama run braincbrain \"Who are you?\""
