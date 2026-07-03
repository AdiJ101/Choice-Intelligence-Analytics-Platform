#!/usr/bin/env bash
# =============================================================================
# scripts/start.sh — Start all Choice Analytics services in one command.
#
# Usage:  ./scripts/start.sh
# Stop:   Ctrl+C  (gracefully shuts everything down)
# Logs:   ./logs/<service>.log
# =============================================================================

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_DIR="$PROJECT_DIR/logs"

cd "$PROJECT_DIR"

# ── Colours ──────────────────────────────────────────────────────────────────
GRN='\033[0;32m'; YLW='\033[1;33m'; RED='\033[0;31m'
BLU='\033[0;34m'; CYN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${BLU}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()   { echo -e " ${GRN}✓${NC}  $*"; }
warn() { echo -e " ${YLW}⚠${NC}  $*"; }
err()  { echo -e " ${RED}✗${NC}  $*"; }

# ── PID registry ─────────────────────────────────────────────────────────────
declare -a PIDS=()

# ── Cleanup on Ctrl+C or error ───────────────────────────────────────────────
cleanup() {
    echo ""
    log "Shutting down all services…"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null && wait "$pid" 2>/dev/null || true
    done
    # Belt-and-braces: kill anything still on our ports
    for port in 6333 8000 8501; do
        lsof -ti :"$port" 2>/dev/null | xargs kill -9 2>/dev/null || true
    done
    echo ""
    ok "All services stopped. Goodbye."
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── Helpers ──────────────────────────────────────────────────────────────────
wait_for_http() {
    local name="$1" url="$2" tries="${3:-20}"
    for ((i=1; i<=tries; i++)); do
        if curl -sf "$url" &>/dev/null; then
            ok "$name is ready"
            return 0
        fi
        sleep 1
    done
    err "$name did not become healthy after ${tries}s — check logs/$name.log"
    cleanup; exit 1
}

kill_port() {
    local port="$1"
    if lsof -ti :"$port" &>/dev/null; then
        warn "Port $port already in use — releasing it…"
        lsof -ti :"$port" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

# ── Pre-flight checks ────────────────────────────────────────────────────────
echo ""
echo -e "${CYN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYN}║   Choice Analytics — Starting Up  🚀         ║${NC}"
echo -e "${CYN}╚══════════════════════════════════════════════╝${NC}"
echo ""

# .env must exist
if [ ! -f "$PROJECT_DIR/.env" ]; then
    err ".env not found. Copy .env.example → .env and fill in values."
    exit 1
fi

# qdrant binary must exist
if [ ! -x "$PROJECT_DIR/qdrant" ]; then
    err "Qdrant binary not found at $PROJECT_DIR/qdrant"
    exit 1
fi

# Resolve uvicorn — prefer pyenv/system install, fall back to venv python -m
if command -v uvicorn &>/dev/null; then
    UVICORN_CMD="uvicorn"
elif "$VENV_PYTHON" -m uvicorn --version &>/dev/null 2>&1; then
    UVICORN_CMD="$VENV_PYTHON -m uvicorn"
else
    err "uvicorn not found. Run: pip install uvicorn[standard]"; exit 1
fi

# Resolve streamlit — prefer venv module, fall back to system
if "$VENV_PYTHON" -m streamlit --version &>/dev/null 2>&1; then
    STREAMLIT_CMD="$VENV_PYTHON -m streamlit"
elif command -v streamlit &>/dev/null; then
    STREAMLIT_CMD="streamlit"
else
    err "streamlit not found. Run: pip install streamlit"; exit 1
fi

mkdir -p "$LOG_DIR"

# Release stale port holders
kill_port 6333
kill_port 8000
kill_port 8501
kill_port 3000

# ── 1. Qdrant ────────────────────────────────────────────────────────────────
log "Starting Qdrant…"
"$PROJECT_DIR/qdrant" \
    > "$LOG_DIR/qdrant.log" 2>&1 &
PIDS+=($!)
wait_for_http "Qdrant" "http://localhost:6333/" 20

# ── 2. Ollama ────────────────────────────────────────────────────────────────
if curl -sf http://localhost:11434/api/tags &>/dev/null; then
    ok "Ollama already running (port 11434)"
else
    log "Starting Ollama…"
    ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
    PIDS+=($!)
    for ((i=1; i<=15; i++)); do
        if curl -sf http://localhost:11434/api/tags &>/dev/null; then
            ok "Ollama is ready (port 11434)"; break
        fi
        [[ $i -eq 15 ]] && warn "Ollama still warming up — continuing anyway"
        sleep 1
    done
fi

# ── 3. FastAPI backend ───────────────────────────────────────────────────────
log "Starting FastAPI backend…"
$UVICORN_CMD dashboard.backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    > "$LOG_DIR/backend.log" 2>&1 &
PIDS+=($!)
wait_for_http "FastAPI backend" "http://localhost:8000/health" 25

# ── 4. Next.js frontend ──────────────────────────────────────────────────────
if [ -d "$PROJECT_DIR/dashboard/nextjs/node_modules" ]; then
    log "Starting Next.js frontend…"
    cd "$PROJECT_DIR/dashboard/nextjs"
    npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    PIDS+=($!)
    cd "$PROJECT_DIR"
    wait_for_http "Next.js frontend" "http://localhost:3000" 40
else
    warn "Next.js node_modules not found — run: cd dashboard/nextjs && npm install"
    warn "Falling back to Streamlit on port 8501"
    $STREAMLIT_CMD run dashboard/frontend/app.py \
        --server.port 8501 --server.headless true --server.address 0.0.0.0 \
        > "$LOG_DIR/frontend.log" 2>&1 &
    PIDS+=($!)
    wait_for_http "Streamlit dashboard" "http://localhost:8501" 25
fi

# ── 5. Scraper ───────────────────────────────────────────────────────────────
log "Starting scraper…"
SCRAPER_CONFIG_PATH="$PROJECT_DIR/scraper_config.json" \
    "$VENV_PYTHON" -m src.scraper.main \
    > "$LOG_DIR/scraper.log" 2>&1 &
PIDS+=($!)
ok "Scraper started (first run begins immediately, then every 60 min)"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GRN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${GRN}║  ✅  All services running!                         ║${NC}"
echo -e "${GRN}║                                                    ║${NC}"
echo -e "${GRN}║  ✦  New Dashboard  →  http://localhost:3000        ║${NC}"
echo -e "${GRN}║  API               →  http://localhost:8000        ║${NC}"
echo -e "${GRN}║  Qdrant            →  http://localhost:6333        ║${NC}"
echo -e "${GRN}║  Ollama            →  http://localhost:11434       ║${NC}"
echo -e "${GRN}║                                                    ║${NC}"
echo -e "${GRN}║  Logs  →  ./logs/<service>.log                     ║${NC}"
echo -e "${GRN}║  Stop  →  Ctrl+C                                   ║${NC}"
echo -e "${GRN}╚════════════════════════════════════════════════════╝${NC}"
echo ""

# Keep script alive so Ctrl+C fires the trap
wait
