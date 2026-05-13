#!/bin/bash
# scripts/news-morning.sh
# ─────────────────────────────────────────────────────────────────────
# launchd-triggered NY 09:00 ET pre-market news scan.
# Fetches RSS → filters to 14-ticker watchlist + sector keywords →
# Claude tags impact → writes to alex-brain/research/markets-news/.
set -u

PY="${PY:-$HOME/.local/bin/python3.11}"
SCRIPT="$HOME/.orallexa/markets/scripts/news_morning.py"
LOG_DIR="$HOME/.orallexa/markets/logs"
mkdir -p "$LOG_DIR"

# Pull ANTHROPIC_API_KEY from ~/.zshrc (launchd context doesn't load zshrc)
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    export ANTHROPIC_API_KEY=$(grep "^export ANTHROPIC_API_KEY" "$HOME/.zshrc" | head -1 | cut -d= -f2)
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "[$(date -u +%FT%TZ)] FATAL: ANTHROPIC_API_KEY not set" >&2
    exit 1
fi

echo "[$(date -u +%FT%TZ)] news-morning.sh starting"
"$PY" "$SCRIPT"
RC=$?
echo "[$(date -u +%FT%TZ)] news-morning.sh exit rc=$RC"
exit $RC
