"""Tests for eval/walk_forward.py — expanding-window walk-forward validation."""
import numpy as np
import pandas as pd
import pytest

from eval.walk_forward import run_walk_forward, _run_single_window, WARMUP_BARS


def _make_ohlcv(n_days: int = 600, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    close = 100 + np.cumsum(rng.normal(0.05, 1.5, n_days))
    close = np.maximum(close, 10)  # Prevent negative prices
    return pd.DataFrame({
        "Open": close * (1 + rng.normal(0, 0.005, n_days)),
        "High": close * (1 + abs(rng.normal(0, 0.01, n_days))),
        "Low": close * (1 - abs(rng.normal(0, 0.01, n_days))),
        "Close": close,
        "Volume": rng.integers(1_000_000, 10_000_000, n_days),
    }, index=dates)


def _dummy_strategy(df, params):
    """Simple MA crossover for testing."""
    ma20 = df["Close"].rolling(20, min_periods=1).mean()
    ma50 = df["Close"].rolling(50, min_periods=1).mean()
    return (ma20 > ma50).astype(int)


class TestRunWalkForward:
    def test_happy_path_produces_windows(self):
        df = _make_ohlcv(600)
        result = run_walk_forward(
            df=df, strategy_fn=_dummy_strategy,
            strategy_name="test_ma", params={},
            initial_train_days=252, test_days=63, min_windows=4,
        )
        assert result.num_windows >= 4
        assert len(result.windows) == result.num_windows
        assert result.strategy_name == "test_ma"

    def test_insufficient_data_returns_empty(self):
        df = _make_ohlcv(100)  # Not enough for 252 + 4*63
        result = run_walk_forward(
            df=df, strategy_fn=_dummy_strategy,
            strategy_name="test_ma", params={},
            initial_train_days=252, test_days=63, min_windows=4,
        )
        assert result.num_windows == 0
        assert result.passed is False

    def test_fewer_windows_than_min_fails(self):
        # 252 + 63 = 315, so 320 bars gives only 1 window (< min 4)
        df = _make_ohlcv(320)
        result = run_walk_forward(
            df=df, strategy_fn=_dummy_strategy,
            strategy_name="test_ma", params={},
            initial_train_days=252, test_days=63, min_windows=4,
        )
        assert result.num_windows < 4
        assert result.passed is False

    def test_pass_fail_gate_based_on_sharpe(self):
        df = _make_ohlcv(800, seed=123)
        result = run_walk_forward(
            df=df, strategy_fn=_dummy_strategy,
            strategy_name="test_ma", params={},
            initial_train_days=252, test_days=63, min_windows=4,
        )
        # Pass if >50% windows have positive Sharpe
        positive = sum(1 for w in result.windows if w.sharpe > 0)
        expected_pass = positive / len(result.windows) > 0.5
        assert result.passed == expected_pass

    def test_window_results_have_all_fields(self):
        df = _make_ohlcv(600)
        result = run_walk_forward(
            df=df, strategy_fn=_dummy_strategy,
            strategy_name="test_ma", params={},
        )
        for w in result.windows:
            assert isinstance(w.sharpe, float)
            assert isinstance(w.total_return, float)
            assert isinstance(w.max_drawdown, float)
            assert isinstance(w.num_trades, int)
            assert w.train_start  # Not empty
            assert w.test_start

    def test_strategy_exception_produces_zero_signal(self):
        def bad_strategy(df, params):
            raise ValueError("intentional failure")

        df = _make_ohlcv(600)
        result = run_walk_forward(
            df=df, strategy_fn=bad_strategy,
            strategy_name="bad", params={},
        )
        # Should complete without raising, all windows have 0 trades
        assert result.num_windows >= 1
        for w in result.windows:
            assert w.num_trades == 0

    def test_information_ratio_computed(self):
        df = _make_ohlcv(600)
        result = run_walk_forward(
            df=df, strategy_fn=_dummy_strategy,
            strategy_name="test_ma", params={},
        )
        # IR should be a finite float for each window
        for w in result.windows:
            assert isinstance(w.information_ratio, float)
            assert np.isfinite(w.information_ratio)
