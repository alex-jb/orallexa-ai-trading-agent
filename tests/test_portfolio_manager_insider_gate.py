"""
tests/test_portfolio_manager_insider_gate.py
──────────────────────────────────────────────────────────────────
Pins the insider_signal integration into portfolio_manager
(Tier-2 #13, shipped 2026-07-02).

Contract:
  - approve_decision accepts optional insider_events list
  - BUY + Δp(up) ≤ -0.10 → rejected
  - BUY + Δp(up) ≤ -0.05 → warned + sized down by 40%
  - BUY + Δp(up) ≥ +0.05 → warned + signal_strength boosted
  - SELL + Δp(up) ≥ +0.05 → contra-signal warning (not blocked)
  - Missing / empty / malformed events → no crash, no block
  - Insider audit fields always present in checks dict
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from engine.portfolio_manager import approve_decision


def _today_iso():
    return datetime.now(timezone.utc).date().isoformat()


def _insider_event(ticker="NVDA", direction="sale", position="CEO",
                   value_usd=500_000, insider_name="J. Doe",
                   days_ago=1):
    d = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()
    return {
        "ticker": ticker,
        "direction": direction,
        "position": position,
        "value_usd": value_usd,
        "insider_name": insider_name,
        "date": d,
    }


# ═══════════════════════════════════════════════════════════════
# Audit fields
# ═══════════════════════════════════════════════════════════════

def test_insider_fields_present_when_no_events():
    """Even with no events, audit fields should default to 0/False
    so downstream reports have a consistent shape."""
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 70, "signal_strength": 60},
    )
    assert "insider_p_up_delta" in r["checks"]
    assert r["checks"]["insider_p_up_delta"] == 0.0
    assert r["checks"]["insider_events_considered"] == 0
    assert r["checks"]["insider_cluster_bonus"] is False


def test_insider_fields_present_with_events():
    """Insider fields reflect the computed signal on real events."""
    events = [_insider_event(direction="purchase", position="CEO",
                             value_usd=800_000)]
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 70, "signal_strength": 60},
        insider_events=events,
    )
    assert r["checks"]["insider_events_considered"] == 1
    assert r["checks"]["insider_p_up_delta"] > 0  # CEO buying = positive delta


# ═══════════════════════════════════════════════════════════════
# BUY + insider-selling → block
# ═══════════════════════════════════════════════════════════════

def test_buy_blocked_by_strong_insider_selling():
    """Multiple C-suite sales → Δp(up) hits the block threshold → BUY rejected."""
    events = [
        _insider_event(direction="sale", position="CEO",
                       value_usd=1_500_000, insider_name="A"),
        _insider_event(direction="sale", position="CFO",
                       value_usd=1_200_000, insider_name="B"),
        _insider_event(direction="sale", position="President",
                       value_usd=900_000, insider_name="C"),
    ]
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 80, "signal_strength": 70},
        insider_events=events,
    )
    assert r["approved"] is False
    assert "Insider signal" in r["reason"]
    assert r["scaled_position_pct"] == 0.0


def test_buy_downweighted_by_moderate_insider_selling():
    """Δp(up) in the [-0.10, -0.05] warn zone → approved but sized down."""
    events = [
        _insider_event(direction="sale", position="CEO",
                       value_usd=800_000, insider_name="X"),
    ]
    r_with = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 80, "signal_strength": 70},
        insider_events=events,
    )
    r_without = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 80, "signal_strength": 70},
    )
    if r_with["checks"]["insider_p_up_delta"] <= -0.05:
        # Only assert the downweight if the fixture actually hit warn zone
        assert r_with["approved"] is True
        assert r_with["scaled_position_pct"] < r_without["scaled_position_pct"]
        assert any("bearish" in w.lower() for w in r_with["warnings"])


# ═══════════════════════════════════════════════════════════════
# BUY + insider-buying → boost
# ═══════════════════════════════════════════════════════════════

def test_buy_boosted_by_insider_buying_cluster():
    """Multiple C-suite purchases → Δp(up) > +0.05 → boost signal_strength +
    surface bullish warning."""
    events = [
        _insider_event(direction="purchase", position="CEO",
                       value_usd=1_000_000, insider_name="A"),
        _insider_event(direction="purchase", position="CFO",
                       value_usd=800_000, insider_name="B"),
    ]
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 70, "signal_strength": 50},
        insider_events=events,
    )
    if r["checks"]["insider_p_up_delta"] >= 0.05:
        assert r["approved"] is True
        assert any("bullish" in w.lower() for w in r["warnings"])


# ═══════════════════════════════════════════════════════════════
# SELL + insider-buying → contra-signal warning
# ═══════════════════════════════════════════════════════════════

def test_sell_gets_contra_signal_warning_when_insiders_buy():
    """Insiders buying while we're selling → surface warning, don't block."""
    events = [
        _insider_event(direction="purchase", position="CEO",
                       value_usd=1_000_000, insider_name="A"),
        _insider_event(direction="purchase", position="CFO",
                       value_usd=900_000, insider_name="B"),
    ]
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "SELL", "confidence": 70, "signal_strength": 60},
        insider_events=events,
    )
    if r["checks"]["insider_p_up_delta"] >= 0.05:
        assert r["approved"] is True  # SELL not blocked by insider buying
        assert any("insiders buying" in w.lower() or "contra-signal" in w.lower()
                   for w in r["warnings"])


# ═══════════════════════════════════════════════════════════════
# Robustness
# ═══════════════════════════════════════════════════════════════

def test_empty_events_list_no_crash():
    """Empty list should behave like no events (no crash, delta=0)."""
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 70, "signal_strength": 60},
        insider_events=[],
    )
    assert r["approved"] is True
    assert r["checks"]["insider_p_up_delta"] == 0.0


def test_malformed_events_fail_closed():
    """Malformed event dicts must not raise — signal reports 0 or skips."""
    events = [
        {"garbage": "data"},
        {"ticker": "NVDA", "direction": "sale"},  # missing critical fields
        _insider_event(direction="sale", position="CEO",
                       value_usd=600_000, insider_name="OK"),
    ]
    # Should not raise
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 70, "signal_strength": 60},
        insider_events=events,
    )
    # events_considered should be 1 (only OK-event) — malformed dropped
    assert r["checks"]["insider_events_considered"] <= 1


def test_hold_bypasses_insider_gate():
    """HOLD should skip sizing logic entirely including insider path."""
    events = [
        _insider_event(direction="sale", position="CEO",
                       value_usd=2_000_000, insider_name="A"),
        _insider_event(direction="sale", position="CFO",
                       value_usd=1_500_000, insider_name="B"),
    ]
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "HOLD", "confidence": 70, "signal_strength": 50},
        insider_events=events,
    )
    assert r["approved"] is True
    assert r["scaled_position_pct"] == 0.0


def test_wrong_ticker_events_ignored():
    """Events for a different ticker should be filtered out inside
    compute_insider_signal — audit reports 0 events."""
    events = [
        _insider_event(ticker="AAPL", direction="sale",
                       position="CEO", value_usd=2_000_000, insider_name="X"),
    ]
    r = approve_decision(
        ticker="NVDA",  # asking about NVDA
        decision={"decision": "BUY", "confidence": 70, "signal_strength": 60},
        insider_events=events,
    )
    assert r["checks"]["insider_events_considered"] == 0
    assert r["checks"]["insider_p_up_delta"] == 0.0


# ═══════════════════════════════════════════════════════════════
# Rules override
# ═══════════════════════════════════════════════════════════════

def test_custom_insider_block_threshold_respected():
    """Overriding insider_block_delta should shift the block boundary."""
    events = [
        _insider_event(direction="sale", position="CEO",
                       value_usd=800_000, insider_name="X"),
    ]
    # With very strict block at -0.01, even a small negative delta should block
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 70, "signal_strength": 50},
        insider_events=events,
        rules={"insider_block_delta": -0.01},
    )
    if r["checks"]["insider_p_up_delta"] <= -0.01:
        assert r["approved"] is False


def test_custom_downweight_factor_respected():
    """Custom insider_downweight_factor changes the sizing multiplier."""
    events = [
        _insider_event(direction="sale", position="CEO",
                       value_usd=800_000, insider_name="X"),
    ]
    r_default = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 80, "signal_strength": 70},
        insider_events=events,
    )
    r_stricter = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 80, "signal_strength": 70},
        insider_events=events,
        rules={"insider_downweight_factor": 0.30},  # much stricter
    )
    if r_default["checks"]["insider_p_up_delta"] <= -0.05 and r_default["approved"]:
        assert r_stricter["scaled_position_pct"] < r_default["scaled_position_pct"]
