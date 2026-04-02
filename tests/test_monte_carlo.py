"""Tests for eval/monte_carlo.py — Monte Carlo simulation."""
import numpy as np
import pandas as pd
import pytest

from eval.monte_carlo import run_monte_carlo, _compute_sharpe, _compute_max_drawdown


def _make_backtest_df(n_days: int = 500, trade_fraction: float = 0.6, seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic backtest DataFrame with signal and returns."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    returns = rng.normal(0.001, 0.02, n_days)
    signal = (rng.random(n_days) < trade_fraction).astype(int)
    strategy_return = signal * returns  # Only earn returns when in position
    return pd.DataFrame({
        "signal": signal,
        "net_strategy_return": strategy_return,
        "return": returns,
    }, index=dates)


class TestComputeSharpe:
    def test_positive_returns(self):
        returns = np.array([0.01, 0.02, 0.01, 0.005, 0.015])
        sharpe = _compute_sharpe(returns)
        assert sharpe > 0

    def test_zero_std_returns_zero(self):
        returns = np.array([0.01, 0.01, 0.01])
        assert _compute_sharpe(returns) == 0.0

    def test_empty_returns_zero(self):
        assert _compute_sharpe(np.array([])) == 0.0


class TestComputeMaxDrawdown:
    def test_no_drawdown(self):
        equity = np.array([1.0, 1.1, 1.2, 1.3])
        assert _compute_max_drawdown(equity) == 0.0

    def test_known_drawdown(self):
        equity = np.array([1.0, 1.2, 0.9, 1.1])  # 25% drawdown from 1.2 to 0.9
        dd = _compute_max_drawdown(equity)
        assert dd == pytest.approx(-0.25, abs=0.01)


class TestRunMonteCarlo:
    def test_deterministic_with_seed(self):
        df = _make_backtest_df()
        r1 = run_monte_carlo(df, "test", "NVDA", n_iterations=100, seed=42)
        r2 = run_monte_carlo(df, "test", "NVDA", n_iterations=100, seed=42)
        assert r1.sharpe_percentile_rank == r2.sharpe_percentile_rank
        assert r1.original_sharpe == r2.original_sharpe

    def test_filters_non_zero_trade_returns(self):
        # Create sparse signal (mostly zeros)
        df = _make_backtest_df(trade_fraction=0.1)
        result = run_monte_carlo(df, "sparse", "NVDA", n_iterations=100, seed=42)
        # n_trade_returns should be much less than total bars
        assert result.n_trade_returns < len(df) * 0.3
        assert result.n_trade_returns > 0

    def test_too_few_trade_returns(self):
        df = pd.DataFrame({
            "signal": [1, 0, 0, 0, 0],
            "net_strategy_return": [0.01, 0, 0, 0, 0],
        })
        result = run_monte_carlo(df, "tiny", "NVDA", n_iterations=100, seed=42)
        assert result.passed is False
        assert result.n_trade_returns < 5

    def test_missing_columns_returns_empty(self):
        df = pd.DataFrame({"foo": [1, 2, 3]})
        result = run_monte_carlo(df, "bad", "NVDA")
        assert result.passed is False
        assert result.n_trade_returns == 0

    def test_percentile_statistics_present(self):
        df = _make_backtest_df()
        result = run_monte_carlo(df, "test", "NVDA", n_iterations=500, seed=42)
        for pct in [5, 25, 50, 75, 95]:
            assert pct in result.sharpe_percentiles
            assert pct in result.return_percentiles
            assert pct in result.drawdown_percentiles

    def test_pass_fail_gate(self):
        df = _make_backtest_df()
        result = run_monte_carlo(df, "test", "NVDA", n_iterations=500, seed=42)
        # Pass if original Sharpe > 75th percentile of simulated
        expected_pass = result.original_sharpe > result.sharpe_percentiles[75]
        assert result.passed == expected_pass

    def test_equity_curves_sample_populated(self):
        df = _make_backtest_df()
        result = run_monte_carlo(df, "test", "NVDA", n_iterations=100, seed=42)
        assert len(result.equity_curves_sample) > 0
        for curve in result.equity_curves_sample:
            assert len(curve) > 0

    def test_clips_extreme_returns(self):
        # Returns with extreme outliers
        df = pd.DataFrame({
            "signal": [1] * 100,
            "net_strategy_return": [5.0] * 50 + [-3.0] * 50,  # Extreme values
        })
        result = run_monte_carlo(df, "extreme", "NVDA", n_iterations=50, seed=42)
        # Should complete without overflow
        assert np.isfinite(result.original_sharpe)
