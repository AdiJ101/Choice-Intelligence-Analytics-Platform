#!/usr/bin/env bash
# =============================================================================
# scripts/stop.sh — Stop all Choice Analytics services.
#
# Usage: ./scripts/stop.sh
# =============================================================================

GRN='\033[0;32m'; YLW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e " ${GRN}✓${NC}  $*"; }
warn() { echo -e " ${YLW}⚠${NC}  $*"; }

echo ""
echo "Stopping Choice Analytics services…"
echo ""

stopped=0

for port in 6333 8000 8501; do
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        ok "Killed process on port $port"
        stopped=$((stopped + 1))
    fi
done

# Stop scraper (python -m src.scraper.main)
scraper_pids=$(pgrep -f "src.scraper.main" 2>/dev/null || true)
if [ -n "$scraper_pids" ]; then
    echo "$scraper_pids" | xargs kill -9 2>/dev/null || true
    ok "Killed scraper"
    stopped=$((stopped + 1))
fi

if [ $stopped -eq 0 ]; then
    warn "No running services found."
else
    echo ""
    ok "Done — $stopped service(s) stopped."
fi
echo ""
