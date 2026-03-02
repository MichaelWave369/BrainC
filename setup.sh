#!/usr/bin/env bash
# BrainC Master Setup Script — PHI369 Labs
# Installs all dependencies, builds the model, and starts the server.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║         BrainC — PHI369 Labs         ║"
echo "  ║       Local AI Ecosystem v0.5.0      ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── Step 1: Install Ollama ─────────────────────────────────

echo "━━━ Step 1/7: Checking Ollama ───────────────────────────"
bash "$REPO_ROOT/scripts/install_ollama.sh"

# ── Step 2: Ensure Ollama service is running ───────────────

echo ""
echo "━━━ Step 2/7: Starting Ollama service ───────────────────"
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
echo "━━━ Step 3/7: Checking qwen2.5:14b base model ───────────"
if ollama list | grep -q "qwen2.5:14b"; then
    echo "[ok] qwen2.5:14b already present."
else
    echo "[*] Pulling qwen2.5:14b (~9GB download — grab a coffee)..."
    ollama pull qwen2.5:14b
    echo "[ok] Base model downloaded."
fi

# ── Step 4: Build BrainC model ────────────────────────────

echo ""
echo "━━━ Step 4/7: Building BrainC model ─────────────────────"
bash "$REPO_ROOT/scripts/build_model.sh"

# ── Step 5: Install Python deps ───────────────────────────

echo ""
echo "━━━ Step 5/7: Installing Python dependencies ────────────"

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

# ── Step 6: Auth setup (.env + migration + admin user) ────

echo ""
echo "━━━ Step 6/7: Auth setup ────────────────────────────────"

ENV_FILE="$REPO_ROOT/.env"

# Generate SECRET_KEY if .env doesn't exist or key is missing/placeholder
if [ ! -f "$ENV_FILE" ]; then
    echo "[*] Creating .env from .env.example..."
    cp "$REPO_ROOT/.env.example" "$ENV_FILE"
fi

if ! grep -q "^SECRET_KEY=" "$ENV_FILE" || grep -q "^SECRET_KEY=your-secret-key-here" "$ENV_FILE"; then
    SECRET_KEY=$("$REPO_ROOT/.venv/bin/python3" -c "import secrets; print(secrets.token_hex(32))")
    # Replace or append SECRET_KEY
    if grep -q "^SECRET_KEY=" "$ENV_FILE"; then
        sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" "$ENV_FILE"
    else
        echo "SECRET_KEY=${SECRET_KEY}" >> "$ENV_FILE"
    fi
    echo "[ok] Generated SECRET_KEY and wrote to .env"
else
    echo "[ok] SECRET_KEY already set."
fi

# Run v0.5 migration script
echo "[*] Running v0.5 database migration..."
"$REPO_ROOT/.venv/bin/python3" "$REPO_ROOT/scripts/migrate_v05.py"

# Create default admin user if no users exist
USER_COUNT=$("$REPO_ROOT/.venv/bin/python3" - <<'PYEOF'
import asyncio, sys
sys.path.insert(0, '.')
async def main():
    from api.config import *  # loads .env
    from api.routes.memory import init_db, count_users
    await init_db()
    print(await count_users())
asyncio.run(main())
PYEOF
)

if [ "$USER_COUNT" = "0" ]; then
    echo ""
    echo "━━━ First-run: Create admin account ─────────────────────"
    echo "No users found. Create your admin account now."
    echo ""

    while true; do
        read -p "  Admin username (min 3 chars): " ADMIN_USERNAME
        [ ${#ADMIN_USERNAME} -ge 3 ] && break
        echo "  Username must be at least 3 characters."
    done

    while true; do
        read -s -p "  Admin password (min 8 chars): " ADMIN_PASSWORD
        echo ""
        [ ${#ADMIN_PASSWORD} -ge 8 ] && break
        echo "  Password must be at least 8 characters."
    done

    read -p "  Display name [Admin]: " ADMIN_DISPLAY
    ADMIN_DISPLAY="${ADMIN_DISPLAY:-Admin}"

    "$REPO_ROOT/.venv/bin/python3" - <<PYEOF
import asyncio, sys
sys.path.insert(0, '.')
async def main():
    from api.routes.memory import init_db, create_user, get_user_by_username
    from api.auth.auth import hash_password
    await init_db()
    existing = await get_user_by_username('${ADMIN_USERNAME}')
    if existing:
        from api.routes.memory import update_user_password
        await update_user_password(existing['id'], hash_password('${ADMIN_PASSWORD}'))
        print(f"[ok] Updated password for existing user '${ADMIN_USERNAME}'")
    else:
        uid = await create_user('${ADMIN_USERNAME}', hash_password('${ADMIN_PASSWORD}'), '${ADMIN_DISPLAY}', 'admin')
        print(f"[ok] Created admin user '${ADMIN_USERNAME}' (id={uid})")
asyncio.run(main())
PYEOF

elif [ "$USER_COUNT" = "1" ]; then
    # A placeholder admin was created by migrate_v05.py — update its password
    PLACEHOLDER=$("$REPO_ROOT/.venv/bin/python3" - <<'PYEOF'
import asyncio, sys
sys.path.insert(0, '.')
async def main():
    from api.routes.memory import get_user_by_username
    u = await get_user_by_username('admin')
    print('yes' if u and u.get('password_hash') == '__PLACEHOLDER__' else 'no')
asyncio.run(main())
PYEOF
)
    if [ "$PLACEHOLDER" = "yes" ]; then
        echo ""
        echo "━━━ Set admin password ───────────────────────────────────"
        echo "An admin account was migrated. Set its password now."
        echo ""

        while true; do
            read -s -p "  New password for 'admin' (min 8 chars): " ADMIN_PASSWORD
            echo ""
            [ ${#ADMIN_PASSWORD} -ge 8 ] && break
            echo "  Password must be at least 8 characters."
        done

        "$REPO_ROOT/.venv/bin/python3" - <<PYEOF
import asyncio, sys
sys.path.insert(0, '.')
async def main():
    from api.routes.memory import get_user_by_username, update_user_password
    from api.auth.auth import hash_password
    u = await get_user_by_username('admin')
    if u:
        await update_user_password(u['id'], hash_password('${ADMIN_PASSWORD}'))
        print("[ok] Admin password set.")
asyncio.run(main())
PYEOF
    else
        echo "[ok] Admin user already configured."
    fi
else
    echo "[ok] Users already exist — skipping admin creation."
fi

# ── Launch ─────────────────────────────────────────────────

echo ""
echo "━━━ Step 7/7: Starting BrainC ───────────────────────────"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete. Starting BrainC v0.5.0"
echo "  UI:           http://localhost:8000"
echo "  Admin panel:  http://localhost:8000/admin"
echo "  API docs:     http://localhost:8000/docs"
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
