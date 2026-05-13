#!/bin/bash
# brier-audit.sh — nightly cron, NY 22:00 ET (post-close)
set -u

PY="${PY:-$HOME/.local/bin/python3.11}"
SCRIPT="$HOME/.orallexa/markets/scripts/brier_audit.py"
LOG_DIR="$HOME/.orallexa/markets/logs"
mkdir -p "$LOG_DIR"

echo "[$(date -u +%FT%TZ)] brier-audit.sh starting"
"$PY" "$SCRIPT"
RC=$?
echo "[$(date -u +%FT%TZ)] brier-audit.sh exit rc=$RC"
exit $RC
