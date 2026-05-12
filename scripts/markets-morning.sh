#!/bin/bash
# scripts/markets-morning.sh
# ─────────────────────────────────────────────────────────────
# Called by launchd at 9 am local time. Generates the morning
# queue, then opens ~/.orallexa/markets/queue/pending/ in Finder
# so Alex sees the day's cards the moment he sits down.
#
# Failures here are NOT silent — log to logs/morning.err.log so
# we can debug the next morning if something didn't generate.
set -u  # treat unset vars as errors (NOT -e: we want to keep going after open fails)

REPO_ROOT="${REPO_ROOT:-$HOME/Desktop/orallexa-ai-trading-agent}"
PYTHON_BIN="${PYTHON_BIN:-/Library/Developer/CommandLineTools/usr/bin/python3}"
PLATFORM="${MARKETS_PLATFORM:-polymarket}"
LIMIT="${MARKETS_QUEUE_LIMIT:-5}"
BANKROLL="${MARKETS_BANKROLL:-300}"

cd "$REPO_ROOT" || { echo "[$(date -u +%FT%TZ)] FATAL: cannot cd into $REPO_ROOT" >&2; exit 1; }

echo "[$(date -u +%FT%TZ)] morning queue starting — platform=$PLATFORM limit=$LIMIT bankroll=\$$BANKROLL"
"$PYTHON_BIN" -m markets queue --platform "$PLATFORM" --limit "$LIMIT" --bankroll "$BANKROLL"
RC=$?

if [ $RC -eq 0 ]; then
    echo "[$(date -u +%FT%TZ)] queue ok — opening Finder for HITL review"
    open "$HOME/.orallexa/markets/queue/pending/"
else
    echo "[$(date -u +%FT%TZ)] queue FAILED rc=$RC — Finder not opened"
fi

exit $RC
