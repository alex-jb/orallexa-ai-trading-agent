"""
tests/test_portfolio_manager_kill_gate.py
──────────────────────────────────────────────────────────────────
Pins the kill_conditions wire-up into portfolio_manager
(Tier-1 #10 wire-up, shipped 2026-07-02).

Contract:
  - approve_decision accepts optional portfolio_state dict
  - kill condition WAIT → decision REJECTED regardless of confidence
  - kill condition GATED → decision REJECTED with GATED reason
  - kill condition OK → falls through to normal approval flow
  - Malformed portfolio_state → fail-open (kill_state="error"),
    trading continues (safety-in-depth, not sole safety mechanism)
  - No portfolio_state → back-compat, no kill fields in checks
"""
from __future__ import annotations

import pytest

from engine.portfolio_manager import approve_decision


# ═══════════════════════════════════════════════════════════════
# Kill state OK → normal approval
# ═══════════════════════════════════════════════════════════════

def test_ok_kill_state_allows_approval():
    """Healthy state → no kill fires → decision approved normally."""
    state = {
        "cumulative_pnl_usd": 200.0,       # positive P&L
        "rolling_14d_sharpe": 0.8,          # positive Sharpe
        "max_drawdown_pct": 3.0,            # small DD
        "rolling_30d_brier": 0.18,          # good calibration
        "paper_trade_days": 45,
        "real_money_mode": False,
    }
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 70, "signal_strength": 60},
        portfolio_state=state,
    )
    assert r["approved"] is True
    assert r["checks"]["kill_state"] == "OK"
    assert r["checks"]["kill_can_trade"] is True


# ═══════════════════════════════════════════════════════════════
# Kill WAIT → decision rejected
# ═══════════════════════════════════════════════════════════════

def test_cumulative_loss_kill_rejects_buy():
    """Cumulative loss exceeds MAX_CUMULATIVE_LOSS_USD ($500) → WAIT.
    Approval must be rejected even for a high-confidence signal."""
    state = {
        "cumulative_pnl_usd": -600.0,       # past the $500 cap
        "rolling_14d_sharpe": 0.5,
        "max_drawdown_pct": 5.0,
        "rolling_30d_brier": 0.15,
        "paper_trade_days": 30,
    }
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 90, "signal_strength": 80},
        portfolio_state=state,
    )
    assert r["approved"] is False
    assert "Kill" in r["reason"] or "WAIT" in r["reason"]
    assert r["scaled_position_pct"] == 0.0


def test_drawdown_kill_rejects_buy():
    """15% drawdown → WAIT even with fine cumulative P&L (day-scale spike)."""
    state = {
        "cumulative_pnl_usd": 100.0,
        "rolling_14d_sharpe": 0.5,
        "max_drawdown_pct": 20.0,          # past the 15% cap
        "rolling_30d_brier": 0.15,
        "paper_trade_days": 30,
    }
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 80, "signal_strength": 70},
        portfolio_state=state,
    )
    assert r["approved"] is False
    assert r["checks"]["kill_state"] == "WAIT"


def test_negative_sharpe_kill_rejects():
    """Rolling 14d Sharpe ≤ 0 → WAIT."""
    state = {
        "cumulative_pnl_usd": 50.0,
        "rolling_14d_sharpe": -0.5,        # negative
        "max_drawdown_pct": 5.0,
        "rolling_30d_brier": 0.18,
        "paper_trade_days": 30,
    }
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 75, "signal_strength": 65},
        portfolio_state=state,
    )
    assert r["approved"] is False
    assert r["checks"]["kill_state"] == "WAIT"


# ═══════════════════════════════════════════════════════════════
# Kill GATED → decision rejected (real-money gate)
# ═══════════════════════════════════════════════════════════════

def test_high_brier_gates_real_money():
    """rolling_30d_brier > 0.20 AND real_money_mode=True → GATED."""
    state = {
        "cumulative_pnl_usd": 500.0,
        "rolling_14d_sharpe": 1.0,
        "max_drawdown_pct": 2.0,
        "rolling_30d_brier": 0.30,          # above threshold
        "paper_trade_days": 45,
        "real_money_mode": True,
    }
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 80, "signal_strength": 70},
        portfolio_state=state,
    )
    assert r["approved"] is False


# ═══════════════════════════════════════════════════════════════
# Back-compat + robustness
# ═══════════════════════════════════════════════════════════════

def test_no_portfolio_state_falls_through():
    """No portfolio_state arg → no kill fields → normal flow works."""
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 70, "signal_strength": 60},
    )
    assert r["approved"] is True
    # kill_state fields should NOT be present when portfolio_state wasn't passed
    assert "kill_state" not in r["checks"]


def test_malformed_portfolio_state_fails_open():
    """Broken portfolio_state should NOT block all trading — kill gate
    is safety-in-depth. checks["kill_state"] logs the error so it
    surfaces in audit, but the decision continues down the normal path."""
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 70, "signal_strength": 60},
        portfolio_state={"cumulative_pnl_usd": "not_a_number"},
    )
    # Should NOT crash, and kill_state should be "error"
    assert r["checks"]["kill_state"] == "error"
    # And trading should have continued — the decision went through
    # normal gates (which pass here).
    assert r["approved"] is True


def test_kill_reason_populated_in_response():
    """When kill fires, the human-readable reason should include the
    trigger + cooldown for the audit report."""
    state = {
        "cumulative_pnl_usd": -700.0,
        "rolling_14d_sharpe": 0.5,
        "max_drawdown_pct": 5.0,
        "rolling_30d_brier": 0.15,
        "paper_trade_days": 30,
    }
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 80, "signal_strength": 70},
        portfolio_state=state,
    )
    assert r["approved"] is False
    assert "Kill" in r["reason"]
    # Cooldown ISO string should be included for WAIT states
    assert "cooldown" in r["reason"].lower()


def test_kill_state_short_circuits_before_insider_gate():
    """When kill fires + insider events also bad → kill reason wins
    (short-circuit ordering matters for the audit)."""
    from tests.test_portfolio_manager_insider_gate import _insider_event
    state = {
        "cumulative_pnl_usd": -700.0,
        "rolling_14d_sharpe": 0.5,
        "max_drawdown_pct": 5.0,
        "rolling_30d_brier": 0.15,
        "paper_trade_days": 30,
    }
    events = [
        _insider_event(direction="sale", position="CEO",
                       value_usd=2_000_000, insider_name="A"),
    ]
    r = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 80, "signal_strength": 70},
        portfolio_state=state,
        insider_events=events,
    )
    assert r["approved"] is False
    assert "Kill" in r["reason"]  # kill reason wins, not insider reason
