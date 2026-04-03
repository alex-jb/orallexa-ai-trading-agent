"""Tests for eval/regime.py — Bull/bear regime detection and segmented performance."""
import numpy as np
import pandas as pd
import pytest

from eval.regime import detect_regimes, segment_performance, _empty_metrics


def _make_price_df(n_days: int = 300, trend: str = "up", seed: int = 42) -> pd.DataFrame:
    """Generate synthetic price data with a clear trend."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n_days)
    if trend == "up":
        prices = 100 + np.cumsum(rng.normal(0.3, 1.0, n_days))
    elif trend == "down":
        prices = 200 + np.cumsum(rng.normal(-0.3, 1.0, n_days))
    else:
        prices = 150 + np.cumsum(rng.normal(0.0, 1.0, n_days))
    return pd.DataFrame({"Close": prices}, index=dates)


def _make_backtest_df(n_days: int = 300, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic backtest returns."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n_days)
    returns = rng.normal(0.001, 0.02, n_days)
    return pd.DataFrame({"net_strategy_return": returns}, index=dates)


class TestDetectRegimes:
    def test_returns_series_with_correct_index(self):
        df = _make_price_df(300)
        regimes = detect_regimes(df, lookback=200)
        assert isinstance(regimes, pd.Series)
        assert len(regimes) == len(df)
        assert regimes.index.equals(df.index)

    def test_values_are_valid_labels(self):
        df = _make_price_df(300)
        regimes = detect_regimes(df, lookback=200)
        assert set(regimes.unique()).issubset({"bull", "bear", "neutral"})

    def test_neutral_during_warmup(self):
        df = _make_price_df(300, trend="up")
        regimes = detect_regimes(df, lookback=200)
        # First 199 bars should be neutral (insufficient data for SMA)
        assert (regimes.iloc[:199] == "neutral").all()

    def test_uptrend_mostly_bull(self):
        df = _make_price_df(500, trend="up", seed=10)
        regimes = detect_regimes(df, lookback=200)
        post_warmup = regimes.iloc[200:]
        bull_pct = (post_warmup == "bull").mean()
        assert bull_pct > 0.5, f"Expected mostly bull in uptrend, got {bull_pct:.1%}"

    def test_downtrend_mostly_bear(self):
        df = _make_price_df(500, trend="down", seed=10)
        regimes = detect_regimes(df, lookback=200)
        post_warmup = regimes.iloc[200:]
        bear_pct = (post_warmup == "bear").mean()
        assert bear_pct > 0.5, f"Expected mostly bear in downtrend, got {bear_pct:.1%}"

    def test_lowercase_close_column(self):
        df = _make_price_df(300)
        df.columns = ["close"]
        regimes = detect_regimes(df, lookback=200)
        assert len(regimes) == 300

    def test_custom_lookback(self):
        df = _make_price_df(100)
        regimes = detect_regimes(df, lookback=50)
        # First 49 bars should be neutral
        assert (regimes.iloc[:49] == "neutral").all()
        # After warmup, should have bull or bear
        post = regimes.iloc[50:]
        assert set(post.unique()).issubset({"bull", "bear"})


class TestSegmentPerformance:
    def test_returns_dict_with_bull_and_bear(self):
        bt = _make_backtest_df(300)
        regimes = pd.Series("bull", index=bt.index)
        regimes.iloc[:150] = "bear"
        result = segment_performance(bt, regimes)
        assert "bull" in result
        assert "bear" in result

    def test_metrics_keys(self):
        bt = _make_backtest_df(300)
        regimes = pd.Series("bull", index=bt.index)
        regimes.iloc[:150] = "bear"
        result = segment_performance(bt, regimes)
        expected_keys = {"sharpe", "total_return", "max_drawdown", "win_rate", "n_bars"}
        for regime in ("bull", "bear"):
            assert set(result[regime].keys()) == expected_keys

    def test_n_bars_sum_correct(self):
        bt = _make_backtest_df(300)
        regimes = pd.Series("bull", index=bt.index)
        regimes.iloc[:100] = "bear"
        result = segment_performance(bt, regimes)
        assert result["bear"]["n_bars"] + result["bull"]["n_bars"] == 300

    def test_empty_regime_returns_zeros(self):
        bt = _make_backtest_df(300)
        regimes = pd.Series("bull", index=bt.index)  # All bull, no bear
        result = segment_performance(bt, regimes)
        assert result["bear"] == _empty_metrics()

    def test_few_bars_returns_empty(self):
        bt = _make_backtest_df(300)
        regimes = pd.Series("bull", index=bt.index)
        regimes.iloc[:3] = "bear"  # Only 3 bear bars — below threshold of 5
        result = segment_performance(bt, regimes)
        assert result["bear"] == _empty_metrics()

    def test_sharpe_is_float(self):
        bt = _make_backtest_df(300)
        regimes = pd.Series("bull", index=bt.index)
        regimes.iloc[:150] = "bear"
        result = segment_performance(bt, regimes)
        assert isinstance(result["bull"]["sharpe"], float)
        assert isinstance(result["bear"]["sharpe"], float)

    def test_fallback_to_strategy_return_col(self):
        bt = _make_backtest_df(300)
        bt.rename(columns={"net_strategy_return": "strategy_return"}, inplace=True)
        regimes = pd.Series("bull", index=bt.index)
        regimes.iloc[:150] = "bear"
        result = segment_performance(bt, regimes)
        assert result["bull"]["n_bars"] > 0

    def test_missing_return_col_returns_empty(self):
        bt = pd.DataFrame({"other_col": range(100)})
        regimes = pd.Series("bull", index=bt.index)
        result = segment_performance(bt, regimes)
        assert result["bull"] == _empty_metrics()
        assert result["bear"] == _empty_metrics()


class TestEmptyMetrics:
    def test_all_zeros(self):
        m = _empty_metrics()
        assert m["sharpe"] == 0.0
        assert m["total_return"] == 0.0
        assert m["max_drawdown"] == 0.0
        assert m["win_rate"] == 0.0
        assert m["n_bars"] == 0
