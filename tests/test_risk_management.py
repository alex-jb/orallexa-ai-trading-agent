"""Tests for skills/risk_management.py — RiskManagementSkill."""

import pytest
from models.decision import DecisionOutput
from skills.risk_management import RiskManagementSkill, RiskParams, RiskOutput


# ── Helpers ─────────────────────────────────────────────────────────────────

def make_decision(decision="BUY", confidence=70.0, risk_level="MEDIUM"):
    return DecisionOutput(
        decision=decision,
        confidence=confidence,
        risk_level=risk_level,
        reasoning=[],
        probabilities={"up": 0.6, "neutral": 0.2, "down": 0.2},
        source="test",
    )


def default_params(entry=150.0, atr=None, max_trades=5):
    return RiskParams(
        account_size=10_000,
        risk_pct=0.01,         # 1% = $100 risk
        entry_price=entry,
        atr=atr,
        max_trades_per_day=max_trades,
    )


rm = RiskManagementSkill()


# ── Approval tests ───────────────────────────────────────────────────────────

def test_buy_approved():
    out = rm.compute(make_decision("BUY"), default_params(), trades_today=0)
    assert out.approved
    assert out.position_size > 0
    assert out.risk_reward_ratio >= 1.5


def test_sell_approved():
    out = rm.compute(make_decision("SELL"), default_params(), trades_today=0)
    assert out.approved
    assert out.stop_loss_price > default_params().entry_price  # stop is above entry for short


def test_wait_rejected():
    out = rm.compute(make_decision("WAIT"), default_params(), trades_today=0)
    assert not out.approved
    assert "WAIT" in out.rejection_reason


# ── Overtrading guard ─────────────────────────────────────────────────────────

def test_overtrading_rejected_at_limit():
    params = default_params(max_trades=3)
    out = rm.compute(make_decision("BUY"), params, trades_today=3)
    assert not out.approved
    assert "Max trades" in out.rejection_reason


def test_just_under_limit_approved():
    params = default_params(max_trades=5)
    out = rm.compute(make_decision("BUY"), params, trades_today=4)
    assert out.approved


# ── Position sizing ───────────────────────────────────────────────────────────

def test_position_value_within_20pct_cap():
    """Position should never exceed 20% of account."""
    params = RiskParams(account_size=10_000, risk_pct=0.10, entry_price=1.0)  # extreme risk_pct
    out = rm.compute(make_decision("BUY", risk_level="LOW"), params, trades_today=0)
    if out.approved:
        assert out.position_value <= 10_000 * 0.20 + 0.01  # allow floating point tolerance


def test_risk_amount_matches_pct():
    params = RiskParams(account_size=10_000, risk_pct=0.01, entry_price=100.0)
    out = rm.compute(make_decision("BUY", risk_level="LOW"), params, trades_today=0)
    if out.approved:
        assert abs(out.risk_amount - 100.0) < 1.0  # ~$100


# ── ATR-based stop vs percentage stop ─────────────────────────────────────────

def test_atr_stop_used_when_provided():
    entry = 100.0
    atr   = 2.0   # stop = entry - 1.5 * atr = 97.0
    params = RiskParams(account_size=10_000, risk_pct=0.01, entry_price=entry, atr=atr)
    out = rm.compute(make_decision("BUY", risk_level="LOW"), params, trades_today=0)
    if out.approved:
        expected_stop = entry - 1.5 * atr
        assert abs(out.stop_loss_price - expected_stop) < 0.01


def test_pct_stop_used_when_no_atr():
    entry = 100.0
    params = RiskParams(account_size=10_000, risk_pct=0.01, entry_price=entry, atr=None)
    out = rm.compute(make_decision("BUY", risk_level="MEDIUM"), params, trades_today=0)
    if out.approved:
        # MEDIUM stop pct = 2.5%, stop = 97.5
        expected_stop = entry * (1 - 0.025)
        assert abs(out.stop_loss_price - expected_stop) < 0.01


# ── Risk/reward ───────────────────────────────────────────────────────────────

def test_rr_at_least_1_5():
    out = rm.compute(make_decision("BUY"), default_params(), trades_today=0)
    if out.approved:
        assert out.risk_reward_ratio >= 1.5


def test_to_dict_structure():
    out = rm.compute(make_decision("BUY"), default_params(), trades_today=0)
    d = out.to_dict()
    assert "position_size" in d
    assert "stop_loss_price" in d
    assert "take_profit_price" in d
    assert "approved" in d
    assert isinstance(d["approved"], bool)
