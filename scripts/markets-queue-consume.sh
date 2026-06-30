#!/bin/bash
# Wrapper for queue_consumer.py — flushes pending Polymarket decisions
# into the audit JSONL. Same TCC-sidestep pattern as morning-deep-dive.sh.
set -e
cd "$HOME/Desktop/orallexa-ai-trading-agent"
exec /usr/bin/python3 markets/auto/queue_consumer.py
