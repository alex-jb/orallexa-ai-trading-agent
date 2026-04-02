"""Tests for engine/param_optimizer.py — Optuna hyperparameter optimization."""
import numpy as np
import pandas as pd
import pytest

from engine.param_optimizer import (
    StrategyOptimizer,
    _run_and_score,
    _sample_params,
    SEARCH_SPACES,
    OptimizationResult,
)
from engine.strategies import get_strategy, STRATEGY_DEFAULT_PARAMS


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


class TestSearchSpaces:
    def test_all_strategies_have_spaces(self):
        """Every registered strategy should have a search space."""
        from engine.strategies import STRATEGY_REGISTRY
        for name in STRATEGY_REGISTRY:
            assert name in SEARCH_SPACES, f"Missing search space for {name}"

    def test_spaces_match_default_params(self):
        """Search space keys should be a subset of default params."""
        for name, space in SEARCH_SPACES.items():
            defaults = STRATEGY_DEFAULT_PARAMS.get(name, {})
            for param_name in space:
                assert param_name in defaults, f"{name}.{param_name} not in defaults"


class TestRunAndScore:
    def test_valid_strategy_returns_float(self, ta_df):
        fn = get_strategy("double_ma")
        params = STRATEGY_DEFAULT_PARAMS["double_ma"]
        score = _run_and_score(fn, ta_df, params)
        assert isinstance(score, float)
        assert score != -10.0  # Should not be the penalty value

    def test_zero_trade_penalized(self, ta_df):
        """Strategy producing 0 trades should get penalty score."""
        def zero_fn(df, params):
            return pd.Series(0, index=df.index)
        score = _run_and_score(zero_fn, ta_df, {})
        assert score == -10.0

    def test_failing_strategy_returns_penalty(self, ta_df):
        def bad_fn(df, params):
            raise ValueError("boom")
        score = _run_and_score(bad_fn, ta_df, {})
        assert score == -10.0


class TestOptimizationResult:
    def test_to_dict(self):
        r = OptimizationResult(
            strategy_name="test", default_params={}, best_params={},
            default_sharpe=0.5, optimized_sharpe=0.8, improvement=60.0, n_trials=10,
        )
        d = r.to_dict()
        assert d["strategy_name"] == "test"
        assert d["improvement"] == 60.0


class TestStrategyOptimizer:
    def test_optimize_single_strategy(self, train_test):
        train, test = train_test
        optimizer = StrategyOptimizer(train, test)
        result = optimizer.optimize_strategy("rsi_reversal", n_trials=10)
        assert isinstance(result, OptimizationResult)
        assert result.strategy_name == "rsi_reversal"
        assert result.n_trials == 10
        assert isinstance(result.optimized_sharpe, float)

    def test_optimize_all(self, train_test):
        train, test = train_test
        optimizer = StrategyOptimizer(train, test)
        results = optimizer.optimize_all(n_trials=5)
        assert len(results) > 0
        for name, r in results.items():
            assert r.strategy_name == name

    def test_get_best(self, train_test):
        train, test = train_test
        optimizer = StrategyOptimizer(train, test)
        optimizer.optimize_all(n_trials=5)
        best = optimizer.get_best()
        assert best is not None
        assert isinstance(best.optimized_sharpe, float)

    def test_summary_table(self, train_test):
        train, test = train_test
        optimizer = StrategyOptimizer(train, test)
        optimizer.optimize_all(n_trials=5)
        table = optimizer.summary_table()
        assert isinstance(table, pd.DataFrame)
        assert "strategy" in table.columns
        assert "optimized_sharpe" in table.columns
        assert len(table) > 0
