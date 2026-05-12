#!/bin/bash
# scripts/markets-evening.sh
# ─────────────────────────────────────────────────────────────
# Called by launchd at 9 pm local time. Writes today's retro,
# then opens the resulting markdown in the default editor so
# Alex sees today's PnL + Brier delta + open positions in one
# glance.
set -u

REPO_ROOT="${REPO_ROOT:-$HOME/Desktop/orallexa-ai-trading-agent}"
PYTHON_BIN="${PYTHON_BIN:-/Library/Developer/CommandLineTools/usr/bin/python3}"
BANKROLL="${MARKETS_BANKROLL:-300}"

cd "$REPO_ROOT" || { echo "[$(date -u +%FT%TZ)] FATAL: cannot cd into $REPO_ROOT" >&2; exit 1; }

echo "[$(date -u +%FT%TZ)] evening retro starting — bankroll=\$$BANKROLL"
"$PYTHON_BIN" -m markets retro --bankroll "$BANKROLL"
RC=$?

TODAY=$(date -u +%F)
RETRO_FILE="$HOME/.orallexa/markets/retro/$TODAY.md"

if [ $RC -eq 0 ] && [ -f "$RETRO_FILE" ]; then
    echo "[$(date -u +%FT%TZ)] retro ok — opening $RETRO_FILE"
    open "$RETRO_FILE"
else
    echo "[$(date -u +%FT%TZ)] retro FAILED rc=$RC or file missing"
fi

exit $RC
