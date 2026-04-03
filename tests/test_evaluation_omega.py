"""Tests for engine/evaluation.py — omega ratio and extended metrics."""
import numpy as np
import pandas as pd
import pytest

from engine.evaluation import evaluate


def _make_backtest_df(returns: list[float], seed: int = 42) -> pd.DataFrame:
    """Build a minimal backtest DataFrame from a list of returns."""
    dates = pd.bdate_range("2023-01-01", periods=len(returns))
    signal = [1] * len(returns)
    return pd.DataFrame({
        "net_strategy_return": returns,
        "strategy_return": returns,
        "signal": signal,
    }, index=dates)


class TestOmegaRatio:
    def test_omega_present_in_output(self):
        df = _make_backtest_df([0.01, 0.02, -0.01, 0.015, -0.005])
        result = evaluate(df)
        # omega should be in either top-level or nested "net" key
        metrics = result.get("net", result)
        assert "omega" in metrics

    def test_all_positive_returns_infinite(self):
        df = _make_backtest_df([0.01, 0.02, 0.03, 0.01, 0.02])
        result = evaluate(df)
        metrics = result.get("net", result)
        assert metrics["omega"] == float("inf")

    def test_all_negative_returns_zero(self):
        df = _make_backtest_df([-0.01, -0.02, -0.03, -0.01, -0.02])
        result = evaluate(df)
        metrics = result.get("net", result)
        assert metrics["omega"] == 0.0

    def test_mixed_returns_positive(self):
        df = _make_backtest_df([0.03, 0.02, -0.01, 0.015, -0.005])
        result = evaluate(df)
        metrics = result.get("net", result)
        assert metrics["omega"] > 1.0  # More gains than losses

    def test_equal_gains_losses_omega_one(self):
        df = _make_backtest_df([0.01, -0.01, 0.02, -0.02])
        result = evaluate(df)
        metrics = result.get("net", result)
        assert abs(metrics["omega"] - 1.0) < 0.01


class TestSortinoCalmar:
    def test_sortino_present(self):
        df = _make_backtest_df([0.01, 0.02, -0.01, 0.015, -0.005])
        result = evaluate(df)
        metrics = result.get("net", result)
        assert "sortino" in metrics

    def test_calmar_present(self):
        df = _make_backtest_df([0.01, 0.02, -0.01, 0.015, -0.005])
        result = evaluate(df)
        metrics = result.get("net", result)
        assert "calmar" in metrics

    def test_positive_returns_sortino_zero_or_positive(self):
        # All positive returns → no downside deviation → sortino = 0 (by convention)
        df = _make_backtest_df([0.01, 0.02, 0.01, 0.015, 0.01] * 10)
        result = evaluate(df)
        metrics = result.get("net", result)
        assert metrics["sortino"] >= 0

    def test_mixed_returns_positive_sortino(self):
        df = _make_backtest_df([0.03, 0.02, -0.005, 0.015, -0.002] * 10)
        result = evaluate(df)
        metrics = result.get("net", result)
        assert metrics["sortino"] > 0
