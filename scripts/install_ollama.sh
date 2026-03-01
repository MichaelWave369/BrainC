#!/usr/bin/env bash
# Install Ollama on macOS or Linux

set -euo pipefail

if command -v ollama &>/dev/null; then
    echo "[ok] Ollama already installed: $(ollama --version 2>&1 | head -1)"
    exit 0
fi

echo "[*] Installing Ollama..."

OS="$(uname -s)"

if [ "$OS" = "Darwin" ]; then
    echo "[*] macOS detected."
    if command -v brew &>/dev/null; then
        brew install ollama
    else
        echo "[*] Homebrew not found. Downloading Ollama.app..."
        curl -fsSL https://ollama.com/download/Ollama-darwin.zip -o /tmp/Ollama.zip
        unzip -q /tmp/Ollama.zip -d /tmp/
        mv /tmp/Ollama.app /Applications/Ollama.app
        echo "[ok] Ollama.app installed to /Applications."
        echo "     Open it once to complete setup, then re-run setup.sh."
        exit 1
    fi
elif [ "$OS" = "Linux" ]; then
    echo "[*] Linux detected."
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "[!] Unsupported OS: $OS"
    echo "    Install Ollama manually from https://ollama.com"
    exit 1
fi

echo "[ok] Ollama installed: $(ollama --version 2>&1 | head -1)"
