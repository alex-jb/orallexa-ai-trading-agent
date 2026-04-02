"""Tests for engine/ensemble.py — strategy ensemble methods."""
import numpy as np
import pandas as pd
import pytest

from engine.ensemble import (
    StrategyEnsemble,
    majority_vote,
    sharpe_weighted,
    rank_weighted,
    _get_strategy_signals,
    _backtest_signal,
    EnsembleResult,
)


def _make_ta_df(n_days: int = 400, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data with indicators."""
    from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    close = 100 + np.cumsum(rng.normal(0.05, 1.5, n_days))
    close = np.maximum(close, 10)
    df = pd.DataFrame({
        "Open": close * (1 + rng.normal(0, 0.005, n_days)),
        "High": close * (1 + abs(rng.normal(0, 0.01, n_days))),
        "Low": close * (1 - abs(rng.normal(0, 0.01, n_days))),
        "Close": close,
        "Volume": rng.integers(1_000_000, 10_000_000, n_days),
    }, index=dates)
    ta = TechnicalAnalysisSkillV2(df)
    ta.add_indicators()
    return ta.copy().dropna()


@pytest.fixture
def ta_df():
    return _make_ta_df(400)


@pytest.fixture
def train_test(ta_df):
    split = int(len(ta_df) * 0.7)
    return ta_df.iloc[:split], ta_df.iloc[split:]


@pytest.fixture
def sample_signals(ta_df):
    """Three simple signals for testing ensemble methods."""
    n = len(ta_df)
    return {
        "s1": pd.Series([1, 0] * (n // 2) + [0] * (n % 2), index=ta_df.index),
        "s2": pd.Series([0, 1] * (n // 2) + [0] * (n % 2), index=ta_df.index),
        "s3": pd.Series([1, 1] * (n // 2) + [1] * (n % 2), index=ta_df.index),
    }


# ═══════════════════════════════════════════════════════════════════════════
# VOTING FUNCTION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestMajorityVote:
    def test_basic_voting(self, sample_signals):
        result = majority_vote(sample_signals)
        assert len(result) == len(list(sample_signals.values())[0])
        assert set(result.unique()).issubset({0, 1})

    def test_unanimous_long(self):
        signals = {
            "a": pd.Series([1, 1, 1]),
            "b": pd.Series([1, 1, 1]),
            "c": pd.Series([1, 1, 1]),
        }
        result = majority_vote(signals)
        assert (result == 1).all()

    def test_unanimous_flat(self):
        signals = {
            "a": pd.Series([0, 0, 0]),
            "b": pd.Series([0, 0, 0]),
        }
        result = majority_vote(signals)
        assert (result == 0).all()

    def test_empty_signals_raises(self):
        with pytest.raises(ValueError):
            majority_vote({})


class TestSharpeWeighted:
    def test_basic_weighting(self, sample_signals):
        sharpes = {"s1": 1.0, "s2": 0.5, "s3": 0.2}
        result = sharpe_weighted(sample_signals, sharpes)
        assert len(result) == len(list(sample_signals.values())[0])

    def test_zero_sharpes_falls_back_to_vote(self, sample_signals):
        sharpes = {"s1": 0.0, "s2": 0.0, "s3": 0.0}
        result = sharpe_weighted(sample_signals, sharpes)
        assert result is not None

    def test_negative_sharpes_zeroed(self, sample_signals):
        sharpes = {"s1": -1.0, "s2": -0.5, "s3": 0.5}
        result = sharpe_weighted(sample_signals, sharpes)
        assert result is not None


class TestRankWeighted:
    def test_basic_ranking(self, sample_signals):
        sharpes = {"s1": 1.0, "s2": 0.5, "s3": 0.2}
        result = rank_weighted(sample_signals, sharpes)
        assert len(result) == len(list(sample_signals.values())[0])

    def test_weights_sum_to_one(self):
        """Rank weights should sum to 1."""
        ranked = [("a", 2.0), ("b", 1.0), ("c", 0.5)]
        n = len(ranked)
        weights = {name: (n - i) / (n * (n + 1) / 2) for i, (name, _) in enumerate(ranked)}
        assert abs(sum(weights.values()) - 1.0) < 1e-6


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestGetStrategySignals:
    def test_returns_signals_for_all_strategies(self, ta_df):
        signals = _get_strategy_signals(ta_df)
        assert len(signals) > 0
        for name, sig in signals.items():
            assert len(sig) == len(ta_df)

    def test_subset_strategies(self, ta_df):
        signals = _get_strategy_signals(ta_df, strategies=["double_ma", "rsi_reversal"])
        assert len(signals) <= 2


class TestBacktestSignal:
    def test_returns_metrics(self, ta_df):
        signal = pd.Series(1, index=ta_df.index)  # Always long
        metrics = _backtest_signal(ta_df, signal)
        assert "sharpe" in metrics
        assert "total_return" in metrics
        assert isinstance(metrics["sharpe"], float)


class TestStrategyEnsemble:
    def test_run_all_ensembles(self, train_test):
        train, test = train_test
        ensemble = StrategyEnsemble(train, test)
        results = ensemble.run_all_ensembles()
        assert "majority_vote" in results
        assert "sharpe_weighted" in results
        assert "rank_weighted" in results

    def test_get_best(self, train_test):
        train, test = train_test
        ensemble = StrategyEnsemble(train, test)
        ensemble.run_all_ensembles()
        best = ensemble.get_best()
        assert best is not None
        assert isinstance(best.sharpe, float)

    def test_comparison_table(self, train_test):
        train, test = train_test
        ensemble = StrategyEnsemble(train, test)
        ensemble.run_all_ensembles()
        table = ensemble.comparison_table()
        assert isinstance(table, pd.DataFrame)
        assert len(table) > 3  # At least 3 ensembles + some individuals

    def test_ensemble_result_to_dict(self):
        r = EnsembleResult(
            method="test", sharpe=1.0, total_return=0.1,
            max_drawdown=-0.05, win_rate=0.6, n_trades=10,
            weights={"a": 0.5, "b": 0.5},
        )
        d = r.to_dict()
        assert d["method"] == "test"
        assert "signal" not in d  # Signal should be excluded
