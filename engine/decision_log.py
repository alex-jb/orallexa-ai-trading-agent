"""
engine/decision_log.py
──────────────────────────────────────────────────────────────────────────────
Decision history persistence for future bot arena / evaluation.

All decisions made via run_for_mode() are appended to:
  memory_data/decision_log.json

Each record stores the full DecisionOutput + context metadata.
This file is the foundation for future evaluation, ranking, and arena comparison.
"""

import json
import os
from datetime import datetime

LOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "memory_data", "decision_log.json"
)


def save_decision(
    decision,               # DecisionOutput
    ticker: str,
    mode: str,
    timeframe: str,
    entry_price: float = 0.0,
    notes: str = "",
) -> None:
    """
    Append a decision record to memory_data/decision_log.json.

    Args:
        decision:    DecisionOutput instance
        ticker:      Symbol (e.g. "NVDA")
        mode:        "scalp" | "intraday" | "swing"
        timeframe:   "1m" | "5m" | "15m" | "1h" | "1D"
        entry_price: Live price at decision time (0 if unavailable)
        notes:       Optional user notes
    """
    record = {
        "timestamp":    datetime.now().isoformat(),
        "ticker":       ticker,
        "mode":         mode,
        "timeframe":    timeframe,
        "entry_price":  entry_price,
        "notes":        notes,
        **decision.to_dict(),   # decision, confidence, risk_level, reasoning, probabilities, source
    }

    log_path = os.path.abspath(LOG_PATH)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    entries = _load(log_path)
    entries.insert(0, record)          # newest first
    entries = entries[:500]            # cap at 500 records

    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
    except OSError:
        pass   # non-critical — don't crash the app


def load_decisions(n: int = 50) -> list:
    """
    Load the most recent N decision records.
    Returns empty list if file doesn't exist.
    """
    return _load(os.path.abspath(LOG_PATH))[:n]


def _load(path: str) -> list:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return []
