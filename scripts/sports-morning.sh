#!/bin/bash
# Wrapper for sports_morning.py — invokes the .venv_sports Python so
# the cron uses penaltyblog / soccerdata isolated from the main env's
# pandas 2.x. Same TCC-sidestep pattern as morning-deep-dive.sh.
set -e
REPO_DIR="$HOME/Desktop/orallexa-ai-trading-agent"
cd "$REPO_DIR"
exec .venv_sports/bin/python markets/auto/sports_morning.py
