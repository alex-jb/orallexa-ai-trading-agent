"""Tests for bot/behavior.py — BehaviorMemory & TradeRecord."""

import json
import os
import tempfile
import pytest
from datetime import datetime

from bot.behavior import BehaviorMemory, TradeRecord


# ── Fixture: isolated temp memory file ───────────────────────────────────────

@pytest.fixture
def mem(tmp_path):
    memory_file = str(tmp_path / "test_memory.json")
    return BehaviorMemory(memory_path=memory_file)


def make_record(ticker="AAPL", decision="BUY", outcome="pending", pnl=0.0):
    return TradeRecord(
        timestamp=datetime.now().isoformat(),
        ticker=ticker,
        decision=decision,
        confidence=70.0,
        risk_level="MEDIUM",
        source="test",
        entry_price=150.0,
        outcome=outcome,
        pnl_pct=pnl,
    )


# ── Initial state ─────────────────────────────────────────────────────────────

def test_initial_aggressiveness(mem):
    assert mem.get_aggressiveness() == 0.5


def test_initial_summary(mem):
    summary = mem.get_summary()
    assert summary["total_trades"] == 0
    assert summary["win_rate_pct"] == 0.0
    assert summary["win_streak"] == 0
    assert summary["loss_streak"] == 0


# ── Trade recording ───────────────────────────────────────────────────────────

def test_record_trade_increments_total(mem):
    mem.record_trade(make_record())
    assert mem.get_summary()["total_trades"] == 1


def test_record_two_trades(mem):
    mem.record_trade(make_record())
    mem.record_trade(make_record(ticker="NVDA"))
    assert mem.get_summary()["total_trades"] == 2


def test_trades_today_increments(mem):
    mem.record_trade(make_record())
    assert mem.get_trades_today() == 1


def test_get_recent_trades(mem):
    for _ in range(5):
        mem.record_trade(make_record())
    recent = mem.get_recent_trades(3)
    assert len(recent) == 3


# ── Outcome updates ───────────────────────────────────────────────────────────

def test_update_outcome_win(mem):
    r = make_record(outcome="pending")
    mem.record_trade(r)
    mem.update_outcome(r.timestamp, "win", 0.025)
    summary = mem.get_summary()
    assert summary["wins"] == 1
    assert summary["win_streak"] == 1
    assert summary["loss_streak"] == 0


def test_update_outcome_loss(mem):
    r = make_record(outcome="pending")
    mem.record_trade(r)
    mem.update_outcome(r.timestamp, "loss", -0.015)
    summary = mem.get_summary()
    assert summary["losses"] == 1
    assert summary["loss_streak"] == 1
    assert summary["win_streak"] == 0


# ── Aggressiveness adaptation ─────────────────────────────────────────────────

def test_three_wins_raise_aggressiveness(mem):
    initial = mem.get_aggressiveness()
    for _ in range(3):
        r = make_record(outcome="pending")
        mem.record_trade(r)
        mem.update_outcome(r.timestamp, "win", 0.02)
    assert mem.get_aggressiveness() > initial


def test_two_losses_lower_aggressiveness(mem):
    initial = mem.get_aggressiveness()
    for _ in range(2):
        r = make_record(outcome="pending")
        mem.record_trade(r)
        mem.update_outcome(r.timestamp, "loss", -0.02)
    assert mem.get_aggressiveness() < initial


def test_aggressiveness_min_cap(mem):
    """Aggressiveness should never go below 0.20."""
    for _ in range(20):
        r = make_record(outcome="pending")
        mem.record_trade(r)
        mem.update_outcome(r.timestamp, "loss", -0.05)
    assert mem.get_aggressiveness() >= 0.20


def test_aggressiveness_max_cap(mem):
    """Aggressiveness should never exceed 0.90."""
    for _ in range(20):
        r = make_record(outcome="pending")
        mem.record_trade(r)
        mem.update_outcome(r.timestamp, "win", 0.05)
    assert mem.get_aggressiveness() <= 0.90


# ── Persistence ───────────────────────────────────────────────────────────────

def test_persistence(tmp_path):
    path = str(tmp_path / "persist_test.json")
    m1 = BehaviorMemory(memory_path=path)
    m1.record_trade(make_record())

    # Load fresh instance from same file
    m2 = BehaviorMemory(memory_path=path)
    assert m2.get_summary()["total_trades"] == 1


def test_corrupted_file_falls_back_to_defaults(tmp_path):
    path = str(tmp_path / "corrupt.json")
    with open(path, "w") as f:
        f.write("NOT VALID JSON {{{{")
    m = BehaviorMemory(memory_path=path)
    assert m.get_aggressiveness() == 0.5
