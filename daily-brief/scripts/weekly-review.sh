#!/bin/bash
# scripts/weekly-review.sh
# ─────────────────────────────────────────────────────────────────────
# launchd-triggered NY 12:00 ET Sunday weekly review.
# Reads last 7 daily briefs → Claude Sonnet 4.6 → outputs:
#   - HITL JSON queue ~/.solo-founder-os/weekly-review/{week}.json
#   - HTML book-quality digest
#   - Resend email to xji1@mail.yu.edu
set -u

PY="${PY:-$HOME/.local/bin/python3.11}"
SCRIPT="$HOME/.orallexa/daily-brief/scripts/weekly_review.py"
LOG_DIR="$HOME/.orallexa/daily-brief/logs"
mkdir -p "$LOG_DIR"

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    export ANTHROPIC_API_KEY=$(grep "^export ANTHROPIC_API_KEY" "$HOME/.zshrc" | head -1 | cut -d= -f2)
fi
if [ -z "${RESEND_API_KEY:-}" ]; then
    export RESEND_API_KEY=$(grep "^export RESEND_API_KEY" "$HOME/.zshrc" 2>/dev/null | head -1 | cut -d= -f2)
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "[$(date -u +%FT%TZ)] FATAL: ANTHROPIC_API_KEY not set" >&2
    exit 1
fi

echo "[$(date -u +%FT%TZ)] weekly-review.sh starting"
"$PY" "$SCRIPT"
RC=$?
echo "[$(date -u +%FT%TZ)] weekly-review.sh exit rc=$RC"
exit $RC
