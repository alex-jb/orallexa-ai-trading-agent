"""
engine/breaking_signals.py
──────────────────────────────────────────────────────────────────
Breaking Signal detection — Polymarket-inspired probability shift alerts.

Compares current analysis against the last logged signal for the same ticker.
Flags as "breaking" when:
  - Up/down probability shifts by >15 percentage points
  - Confidence changes by >20 percentage points
  - Decision flips (e.g. BUY → SELL)

Usage:
    from engine.breaking_signals import detect_breaking, get_recent_breaking

    alert = detect_breaking(current_decision, ticker)
    if alert:
        print(alert)  # {"type": "probability_shift", "ticker": "NVDA", ...}
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Optional

from models.decision import DecisionOutput

# ── Thresholds ───────────────────────────────────────────────────────────────

PROB_SHIFT_THRESHOLD = 0.15      # 15 percentage points
CONFIDENCE_SHIFT_THRESHOLD = 20  # 20 points (0-100 scale)
BREAKING_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "memory_data", "breaking_signals.json"
)
DECISION_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "memory_data", "decision_log.json"
)


def _load_json(path: str) -> list:
    abs_path = os.path.abspath(path)
    if os.path.exists(abs_path):
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_json(path: str, data: list) -> None:
    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def _get_last_signal(ticker: str) -> Optional[dict]:
    """Find the most recent decision log entry for this ticker."""
    entries = _load_json(DECISION_LOG_PATH)
    for entry in entries:
        if entry.get("ticker", "").upper() == ticker.upper():
            return entry
    return None


def detect_breaking(
    current: DecisionOutput,
    ticker: str,
) -> Optional[dict]:
    """
    Compare current decision against last logged signal for same ticker.
    Returns a breaking signal dict if thresholds exceeded, else None.
    """
    prev = _get_last_signal(ticker)
    if prev is None:
        return None

    alerts = []
    now = datetime.now().isoformat()

    cur_probs = current.probabilities or {}
    prev_probs = prev.get("probabilities", {})

    cur_up = cur_probs.get("up", 0)
    prev_up = prev_probs.get("up", 0)
    cur_down = cur_probs.get("down", 0)
    prev_down = prev_probs.get("down", 0)

    up_shift = cur_up - prev_up
    down_shift = cur_down - prev_down

    # Decision flip (most dramatic)
    prev_decision = prev.get("decision", "WAIT")
    if current.decision != prev_decision and current.decision != "WAIT" and prev_decision != "WAIT":
        alerts.append({
            "type": "decision_flip",
            "severity": "critical",
            "ticker": ticker,
            "timestamp": now,
            "prev_decision": prev_decision,
            "new_decision": current.decision,
            "confidence": round(current.confidence, 1),
            "message": f"{ticker} flipped from {prev_decision} to {current.decision}",
        })

    # Probability shift
    if abs(up_shift) > PROB_SHIFT_THRESHOLD:
        direction = "bullish" if up_shift > 0 else "bearish"
        alerts.append({
            "type": "probability_shift",
            "severity": "high",
            "ticker": ticker,
            "timestamp": now,
            "direction": direction,
            "shift_pct": round(up_shift * 100, 1),
            "prev_up": round(prev_up * 100, 1),
            "new_up": round(cur_up * 100, 1),
            "message": f"{ticker} upside probability shifted {up_shift*100:+.0f}% ({prev_up*100:.0f}% → {cur_up*100:.0f}%)",
        })

    if abs(down_shift) > PROB_SHIFT_THRESHOLD:
        direction = "bearish" if down_shift > 0 else "bullish"
        alerts.append({
            "type": "probability_shift",
            "severity": "high",
            "ticker": ticker,
            "timestamp": now,
            "direction": direction,
            "shift_pct": round(down_shift * 100, 1),
            "prev_down": round(prev_down * 100, 1),
            "new_down": round(cur_down * 100, 1),
            "message": f"{ticker} downside probability shifted {down_shift*100:+.0f}% ({prev_down*100:.0f}% → {cur_down*100:.0f}%)",
        })

    # Confidence shift
    prev_conf = prev.get("confidence", 50)
    conf_shift = current.confidence - prev_conf
    if abs(conf_shift) > CONFIDENCE_SHIFT_THRESHOLD:
        alerts.append({
            "type": "confidence_shift",
            "severity": "medium",
            "ticker": ticker,
            "timestamp": now,
            "shift": round(conf_shift, 1),
            "prev_confidence": round(prev_conf, 1),
            "new_confidence": round(current.confidence, 1),
            "message": f"{ticker} confidence shifted {conf_shift:+.0f}% ({prev_conf:.0f}% → {current.confidence:.0f}%)",
        })

    if not alerts:
        return None

    # Pick the highest severity alert as the primary
    severity_order = {"critical": 0, "high": 1, "medium": 2}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 99))
    primary = dict(alerts[0])  # copy to avoid circular reference
    if len(alerts) > 1:
        primary["additional_alerts"] = [a["type"] for a in alerts[1:]]

    # Save to breaking signals log
    _save_breaking(primary)

    return primary


def _save_breaking(alert: dict) -> None:
    """Append a breaking signal to the log, cap at 100."""
    signals = _load_json(BREAKING_LOG_PATH)
    signals.insert(0, alert)
    signals = signals[:100]
    _save_json(BREAKING_LOG_PATH, signals)


def get_recent_breaking(hours: int = 24, limit: int = 10) -> list[dict]:
    """Return recent breaking signals within the last N hours."""
    signals = _load_json(BREAKING_LOG_PATH)
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

    recent = []
    for s in signals:
        ts = s.get("timestamp", "")
        if ts >= cutoff:
            recent.append(s)
        if len(recent) >= limit:
            break

    return recent
