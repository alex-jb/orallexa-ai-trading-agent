"""Tests for the dual_thrust strategy in engine/strategies.py."""
import numpy as np
import pandas as pd
import pytest

from engine.strategies import dual_thrust, STRATEGY_REGISTRY, STRATEGY_DEFAULT_PARAMS


def _make_ohlcv(n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0.1, 1.0, n))
    return pd.DataFrame({
        "Open": close * (1 + rng.normal(0, 0.003, n)),
        "High": close * (1 + abs(rng.normal(0, 0.01, n))),
        "Low": close * (1 - abs(rng.normal(0, 0.01, n))),
        "Close": close,
        "Volume": rng.integers(1_000_000, 5_000_000, n),
    }, index=pd.bdate_range("2024-01-01", periods=n))


class TestDualThrust:
    def test_registered_in_registry(self):
        assert "dual_thrust" in STRATEGY_REGISTRY
        assert "dual_thrust" in STRATEGY_DEFAULT_PARAMS

    def test_returns_series_of_correct_length(self):
        df = _make_ohlcv()
        params = STRATEGY_DEFAULT_PARAMS["dual_thrust"]
        result = dual_thrust(df, params)
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)

    def test_signals_are_binary(self):
        df = _make_ohlcv()
        params = STRATEGY_DEFAULT_PARAMS["dual_thrust"]
        result = dual_thrust(df, params)
        unique = set(result.unique())
        assert unique.issubset({0, 1})

    def test_generates_some_trades(self):
        df = _make_ohlcv(200, seed=99)
        params = {"lookback": 4, "k_up": 0.3, "k_down": 0.3}  # Tighter triggers
        result = dual_thrust(df, params)
        assert result.sum() > 0  # At least some long signals

    def test_handles_nan_triggers_gracefully(self):
        df = _make_ohlcv(10)  # Very short, will have NaN in rolling
        params = STRATEGY_DEFAULT_PARAMS["dual_thrust"]
        result = dual_thrust(df, params)
        # Should not raise, signals should be 0 or 1
        assert len(result) == 10
        assert all(s in (0, 1) for s in result)

    def test_registry_has_seven_strategies(self):
        assert len(STRATEGY_REGISTRY) == 7
