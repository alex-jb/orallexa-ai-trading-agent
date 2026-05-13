#!/bin/bash
# scripts/daily-brief.sh
# ─────────────────────────────────────────────────────────────────────
# launchd-triggered NY 12:00 ET daily brief.
# Pulls AI news + SpaceX + 90-day LLM curriculum → Claude Sonnet 4.6
# synthesizes Chinese brief → writes brain + emails via Resend.
set -u

PY="${PY:-$HOME/.local/bin/python3.11}"
SCRIPT="$HOME/.orallexa/daily-brief/scripts/daily_brief.py"
LOG_DIR="$HOME/.orallexa/daily-brief/logs"
mkdir -p "$LOG_DIR"

# Pull ANTHROPIC_API_KEY from ~/.zshrc (launchd context doesn't load zshrc)
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

echo "[$(date -u +%FT%TZ)] daily-brief.sh starting"
"$PY" "$SCRIPT"
RC=$?

# Mirror to public spacex-ipo-tracker repo? No — daily brief is private (contains
# Alex's stack-specific commentary). Only mirror the SpaceX section,
# which spacex-daily.sh already handles.

echo "[$(date -u +%FT%TZ)] daily-brief.sh exit rc=$RC"
exit $RC
