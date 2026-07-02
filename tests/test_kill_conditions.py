"""
tests/test_kill_conditions.py
──────────────────────────────────────────────────────────────────
Pins the kill-conditions contract shipped 2026-07-02 (Tier-1 #10).

These tests exist because the 2026-06-30 audit called the ABSENCE of
kill conditions "the single most dangerous architecture pattern on the
whole stack." If any of the four gates weakens without a re-audit,
these tests are supposed to bite.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.kill_conditions import (
    MAX_CUMULATIVE_LOSS_USD,
    MAX_DRAWDOWN_PCT,
    MIN_BRIER_ROLLING_30D_FOR_REAL_MONEY,
    MIN_PAPER_DAYS_FOR_REAL_MONEY,
    MIN_SHARPE_ROLLING_14D,
    KillDecision,
    PortfolioState,
    check_kill_conditions,
    cooldown_still_active,
    is_ready_for_real_money,
    persist_kill_state,
    read_persisted_kill_state,
)


# ═══════════════════════════════════════════════════════════════
# Gate 1: cumulative loss cap
# ═══════════════════════════════════════════════════════════════

def test_cumulative_loss_below_threshold_ok():
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=-100.0, rolling_14d_sharpe=1.0,
        max_drawdown_pct=3.0, rolling_30d_brier=0.18,
        paper_trade_days=45,
    ))
    assert d.can_trade is True
    assert d.state == "OK"


def test_cumulative_loss_exactly_at_threshold_trips():
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=-MAX_CUMULATIVE_LOSS_USD,
        rolling_14d_sharpe=1.0, max_drawdown_pct=3.0,
        rolling_30d_brier=0.18, paper_trade_days=45,
    ))
    assert d.can_trade is False
    assert d.state == "WAIT"
    assert "cumulative_loss" in d.trigger_reason
    assert "max_cumulative_loss" in d.triggered_gates


def test_cumulative_loss_beyond_threshold_trips():
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=-1_000.0,
        rolling_14d_sharpe=1.0, max_drawdown_pct=3.0,
        rolling_30d_brier=0.18, paper_trade_days=45,
    ))
    assert d.can_trade is False
    assert d.state == "WAIT"


def test_cooldown_iso_string_present_when_wait():
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=-600.0,
        rolling_14d_sharpe=1.0, max_drawdown_pct=3.0,
        rolling_30d_brier=0.18, paper_trade_days=45,
    ))
    assert d.cooldown_until_utc is not None
    # ISO 8601 with Z or +00:00 suffix
    parsed = datetime.fromisoformat(d.cooldown_until_utc.replace("Z", "+00:00"))
    assert parsed > datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════
# Gate 2: rolling 14d Sharpe
# ═══════════════════════════════════════════════════════════════

def test_sharpe_positive_ok():
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=200.0, rolling_14d_sharpe=1.2,
        max_drawdown_pct=3.0, rolling_30d_brier=0.18,
        paper_trade_days=45,
    ))
    assert d.can_trade is True


def test_sharpe_negative_trips():
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=-100.0, rolling_14d_sharpe=-0.3,
        max_drawdown_pct=3.0, rolling_30d_brier=0.18,
        paper_trade_days=45,
    ))
    assert d.can_trade is False
    assert d.state == "WAIT"
    assert "sharpe" in d.trigger_reason.lower()
    assert "min_sharpe_14d" in d.triggered_gates


def test_sharpe_at_zero_trips():
    """Zero is the threshold — we want strictly positive rolling Sharpe."""
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=0.0, rolling_14d_sharpe=0.0,
        max_drawdown_pct=3.0, rolling_30d_brier=0.18,
        paper_trade_days=45,
    ))
    assert d.can_trade is False


def test_sharpe_nan_fails_closed():
    """NaN Sharpe (from math errors upstream) treated as failure."""
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=0.0, rolling_14d_sharpe=float("nan"),
        max_drawdown_pct=3.0, rolling_30d_brier=0.18,
        paper_trade_days=45,
    ))
    assert d.can_trade is False


def test_sharpe_none_treated_as_insufficient_history_not_failure():
    """Insufficient history is not a kill — kill conditions bite once
    you have data, not before."""
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=-10.0, rolling_14d_sharpe=None,
        max_drawdown_pct=3.0, rolling_30d_brier=0.18,
        paper_trade_days=5,
    ))
    assert d.can_trade is True


# ═══════════════════════════════════════════════════════════════
# Gate 3: max drawdown %
# ═══════════════════════════════════════════════════════════════

def test_drawdown_below_threshold_ok():
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=100.0, rolling_14d_sharpe=1.0,
        max_drawdown_pct=10.0, rolling_30d_brier=0.18,
        paper_trade_days=45,
    ))
    assert d.can_trade is True


def test_drawdown_at_threshold_trips():
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=-100.0, rolling_14d_sharpe=1.0,
        max_drawdown_pct=MAX_DRAWDOWN_PCT,
        rolling_30d_brier=0.18, paper_trade_days=45,
    ))
    assert d.can_trade is False
    assert "drawdown" in d.trigger_reason.lower()


# ═══════════════════════════════════════════════════════════════
# Gate 4: Brier gate for real money mode
# ═══════════════════════════════════════════════════════════════

def test_brier_gate_only_applies_in_real_money_mode():
    """A bad Brier in PAPER mode is NOT a kill — it's the data
    Alex is producing to figure out whether he's ready."""
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=100.0, rolling_14d_sharpe=1.0,
        max_drawdown_pct=3.0, rolling_30d_brier=0.35,  # bad Brier
        paper_trade_days=45, real_money_mode=False,
    ))
    assert d.can_trade is True


def test_brier_gate_trips_in_real_money_mode_when_over_threshold():
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=100.0, rolling_14d_sharpe=1.0,
        max_drawdown_pct=3.0, rolling_30d_brier=0.30,
        paper_trade_days=45, real_money_mode=True,
    ))
    assert d.can_trade is False
    assert d.state == "GATED"
    # GATED is not auto-recoverable — no cooldown expiry
    assert d.cooldown_until_utc is None
    assert "brier" in d.trigger_reason.lower()


def test_brier_gate_ok_in_real_money_mode_when_under_threshold():
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=100.0, rolling_14d_sharpe=1.0,
        max_drawdown_pct=3.0,
        rolling_30d_brier=MIN_BRIER_ROLLING_30D_FOR_REAL_MONEY - 0.01,
        paper_trade_days=45, real_money_mode=True,
    ))
    assert d.can_trade is True


# ═══════════════════════════════════════════════════════════════
# Gate ordering — first WAIT short-circuits
# ═══════════════════════════════════════════════════════════════

def test_gate_1_short_circuits_before_gate_2():
    """When multiple gates would trip, only the first is reported —
    Alex should be able to fix one thing and re-check, not chase five."""
    d = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=-2_000.0,  # trips Gate 1
        rolling_14d_sharpe=-1.0,       # would trip Gate 2
        max_drawdown_pct=30.0,          # would trip Gate 3
        rolling_30d_brier=0.4,          # would trip Gate 4 in real money
        paper_trade_days=45,
    ))
    assert "cumulative_loss" in d.trigger_reason
    assert d.triggered_gates == ["max_cumulative_loss"]


# ═══════════════════════════════════════════════════════════════
# is_ready_for_real_money — the paper → real transition
# ═══════════════════════════════════════════════════════════════

def test_real_money_ready_all_gates_clear():
    ready, reason = is_ready_for_real_money(PortfolioState(
        cumulative_pnl_usd=200.0, rolling_14d_sharpe=0.8,
        max_drawdown_pct=5.0, rolling_30d_brier=0.15,
        paper_trade_days=45,
    ))
    assert ready is True, reason


def test_real_money_rejected_when_paper_history_short():
    ready, reason = is_ready_for_real_money(PortfolioState(
        cumulative_pnl_usd=200.0, rolling_14d_sharpe=0.8,
        max_drawdown_pct=5.0, rolling_30d_brier=0.15,
        paper_trade_days=10,
    ))
    assert ready is False
    assert "paper_trade_days" in reason


def test_real_money_rejected_when_brier_bad():
    ready, reason = is_ready_for_real_money(PortfolioState(
        cumulative_pnl_usd=200.0, rolling_14d_sharpe=0.8,
        max_drawdown_pct=5.0, rolling_30d_brier=0.30,
        paper_trade_days=45,
    ))
    assert ready is False
    assert "brier" in reason.lower()


def test_real_money_rejected_when_currently_losing():
    ready, reason = is_ready_for_real_money(PortfolioState(
        cumulative_pnl_usd=-100.0, rolling_14d_sharpe=0.8,
        max_drawdown_pct=5.0, rolling_30d_brier=0.15,
        paper_trade_days=45,
    ))
    assert ready is False


def test_real_money_rejected_when_sharpe_zero():
    ready, reason = is_ready_for_real_money(PortfolioState(
        cumulative_pnl_usd=200.0, rolling_14d_sharpe=0.0,
        max_drawdown_pct=5.0, rolling_30d_brier=0.15,
        paper_trade_days=45,
    ))
    assert ready is False


def test_real_money_rejected_when_already_in_real_money():
    """The check is for the TRANSITION. If we're already there, this
    function returns False + a diagnostic message."""
    ready, reason = is_ready_for_real_money(PortfolioState(
        cumulative_pnl_usd=200.0, rolling_14d_sharpe=0.8,
        max_drawdown_pct=5.0, rolling_30d_brier=0.15,
        paper_trade_days=45, real_money_mode=True,
    ))
    assert ready is False
    assert "already" in reason.lower()


# ═══════════════════════════════════════════════════════════════
# On-disk persistence + cooldown tracking
# ═══════════════════════════════════════════════════════════════

def test_persist_and_read_kill_state(tmp_path: Path):
    p = tmp_path / "kill_state.json"
    dec = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=-700.0, rolling_14d_sharpe=1.0,
        max_drawdown_pct=3.0, rolling_30d_brier=0.18,
        paper_trade_days=45,
    ))
    persist_kill_state(dec, path=p)
    loaded = read_persisted_kill_state(p)
    assert loaded is not None
    assert loaded["state"] == "WAIT"
    assert "cumulative_loss" in loaded["trigger_reason"]
    assert "persisted_at_utc" in loaded


def test_cooldown_still_active_true_when_future_expiry(tmp_path: Path):
    p = tmp_path / "kill_state.json"
    dec = check_kill_conditions(PortfolioState(
        cumulative_pnl_usd=-700.0, rolling_14d_sharpe=1.0,
        max_drawdown_pct=3.0, rolling_30d_brier=0.18,
        paper_trade_days=45,
    ))
    persist_kill_state(dec, path=p)
    assert cooldown_still_active(p) is True


def test_cooldown_still_active_false_when_past_expiry(tmp_path: Path):
    p = tmp_path / "kill_state.json"
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    p.write_text('{"cooldown_until_utc": "' + past + '"}')
    assert cooldown_still_active(p) is False


def test_cooldown_still_active_false_when_no_file(tmp_path: Path):
    assert cooldown_still_active(tmp_path / "nope.json") is False
