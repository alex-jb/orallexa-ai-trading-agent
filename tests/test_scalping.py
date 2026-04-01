"""
Tests for skills/scalping.py — ScalpingSkill.
All tests use synthetic DataFrames. No network calls.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

from skills.scalping import ScalpingSkill
from models.decision import DecisionOutput


# ── Synthetic data helpers ────────────────────────────────────────────────────

def make_ohlcv(
    n: int = 100,
    base_price: float = 150.0,
    trend: float = 0.0,          # price drift per bar
    volume: float = 1_000_000.0,
) -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame with timezone-aware index."""
    np.random.seed(42)
    closes = base_price + trend * np.arange(n) + np.random.randn(n) * 0.5
    closes = np.maximum(closes, 1.0)

    data = {
        "Open":   closes * (1 - np.random.uniform(0, 0.003, n)),
        "High":   closes * (1 + np.random.uniform(0, 0.005, n)),
        "Low":    closes * (1 - np.random.uniform(0, 0.005, n)),
        "Close":  closes,
        "Volume": np.full(n, volume),
    }

    start = datetime(2026, 1, 2, 9, 30, tzinfo=timezone.utc)
    index = [start + timedelta(minutes=5 * i) for i in range(n)]
    return pd.DataFrame(data, index=index)


def make_skill(ticker: str = "TEST") -> ScalpingSkill:
    return ScalpingSkill(ticker)


# ── _add_indicators ───────────────────────────────────────────────────────────

def test_add_indicators_produces_required_columns():
    skill = make_skill()
    df = make_ohlcv(80)
    result = skill._add_indicators(df)

    required = ["EMA9", "EMA21", "RSI7", "Vol_MA20", "Vol_Ratio", "ATR5", "High20", "Low20"]
    for col in required:
        assert col in result.columns, f"Missing column: {col}"


def test_add_indicators_no_nan_after_dropna():
    skill = make_skill()
    df = make_ohlcv(80)
    result = skill._add_indicators(df)
    assert result.isnull().sum().sum() == 0


def test_add_indicators_sufficient_rows():
    """Should return enough rows for evaluation after dropna."""
    skill = make_skill()
    df = make_ohlcv(80)
    result = skill._add_indicators(df)
    assert len(result) >= 20


# ── _evaluate ─────────────────────────────────────────────────────────────────

def test_evaluate_returns_decision_output():
    skill = make_skill()
    df = make_ohlcv(80)
    df = skill._add_indicators(df)
    result = skill._evaluate(df)
    assert isinstance(result, DecisionOutput)


def test_evaluate_decision_is_valid_label():
    skill = make_skill()
    df = make_ohlcv(80)
    df = skill._add_indicators(df)
    result = skill._evaluate(df)
    assert result.decision in ("BUY", "SELL", "WAIT")


def test_evaluate_confidence_in_range():
    skill = make_skill()
    df = make_ohlcv(80)
    df = skill._add_indicators(df)
    result = skill._evaluate(df)
    assert 0.0 <= result.confidence <= 100.0


def test_evaluate_risk_level_valid():
    skill = make_skill()
    df = make_ohlcv(80)
    df = skill._add_indicators(df)
    result = skill._evaluate(df)
    assert result.risk_level in ("LOW", "MEDIUM", "HIGH")


def test_evaluate_source_is_scalping():
    skill = make_skill()
    df = make_ohlcv(80)
    df = skill._add_indicators(df)
    result = skill._evaluate(df)
    assert result.source == "scalping"


def test_evaluate_reasoning_is_nonempty_list():
    skill = make_skill()
    df = make_ohlcv(80)
    df = skill._add_indicators(df)
    result = skill._evaluate(df)
    assert isinstance(result.reasoning, list)
    assert len(result.reasoning) > 0


def test_probabilities_sum_to_one():
    skill = make_skill()
    df = make_ohlcv(80)
    df = skill._add_indicators(df)
    result = skill._evaluate(df)
    total = sum(result.probabilities.values())
    assert abs(total - 1.0) < 0.05  # allow slight float error


def test_probabilities_all_nonnegative():
    skill = make_skill()
    df = make_ohlcv(80)
    df = skill._add_indicators(df)
    result = skill._evaluate(df)
    for k, v in result.probabilities.items():
        assert v >= 0.0, f"Probability {k} is negative: {v}"


# ── Quality filter ─────────────────────────────────────────────────────────────

def test_insufficient_bars_returns_wait():
    """_evaluate with too few rows after dropna should return WAIT."""
    skill = make_skill()
    result = skill._evaluate(pd.DataFrame())
    assert result.decision == "WAIT"


def test_wait_output_on_flat_no_signal():
    """Flat price with no trend should not generate confident BUY."""
    skill = make_skill()
    df = make_ohlcv(80, trend=0.0)  # flat price
    df = skill._add_indicators(df)
    result = skill._evaluate(df)
    # Flat price likely produces WAIT; confidence should not be high
    if result.decision == "BUY":
        assert result.confidence < 90.0  # sanity: not a super-confident BUY on flat data


# ── _wait helper ──────────────────────────────────────────────────────────────

def test_wait_output_structure():
    skill = make_skill()
    result = skill._wait("test reason")
    assert result.decision == "WAIT"
    assert result.confidence == 0.0
    assert result.risk_level == "HIGH"
    assert "test reason" in result.reasoning
    assert result.source == "scalping"
