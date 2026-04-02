"""Tests for eval/statistical_tests.py — t-test, bootstrap CI, DSR."""
import numpy as np
import pytest

from eval.statistical_tests import (
    ttest_returns,
    bootstrap_sharpe_ci,
    deflated_sharpe_ratio,
    run_statistical_tests,
    MIN_TRADES_FOR_STATS,
)


class TestTtestReturns:
    def test_significant_positive_returns(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.005, 0.01, 100)  # Positive mean
        t_stat, p_val = ttest_returns(returns)
        assert t_stat > 0
        assert p_val < 0.05

    def test_zero_mean_not_significant(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0, 0.01, 100)
        _, p_val = ttest_returns(returns)
        # May or may not be significant, but shouldn't be extremely small
        assert p_val > 0.001

    def test_insufficient_data_returns_defaults(self):
        returns = np.array([0.01, 0.02])  # < MIN_TRADES_FOR_STATS
        t_stat, p_val = ttest_returns(returns)
        assert t_stat == 0.0
        assert p_val == 1.0


class TestBootstrapSharpeCI:
    def test_ci_contains_point_estimate(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.003, 0.015, 200)
        lower, point, upper = bootstrap_sharpe_ci(returns, seed=42)
        assert lower <= point <= upper

    def test_deterministic_with_seed(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.003, 0.015, 200)
        r1 = bootstrap_sharpe_ci(returns, seed=42)
        r2 = bootstrap_sharpe_ci(returns, seed=42)
        assert r1 == r2

    def test_insufficient_data(self):
        returns = np.array([0.01] * 5)
        lower, point, upper = bootstrap_sharpe_ci(returns)
        assert lower == 0.0 and point == 0.0 and upper == 0.0


class TestDeflatedSharpeRatio:
    def test_single_strategy_no_penalty(self):
        # With 1 strategy, DSR should be close to the raw p-value
        dsr = deflated_sharpe_ratio(
            observed_sharpe=2.0, num_strategies=1,
            n_observations=252, sharpe_std=1.0,
        )
        assert 0 <= dsr <= 1

    def test_more_strategies_lower_dsr(self):
        # More strategies tested = more multiple-testing correction = lower DSR
        dsr_few = deflated_sharpe_ratio(
            observed_sharpe=1.5, num_strategies=2,
            n_observations=252, sharpe_std=1.0,
        )
        dsr_many = deflated_sharpe_ratio(
            observed_sharpe=1.5, num_strategies=20,
            n_observations=252, sharpe_std=1.0,
        )
        assert dsr_few >= dsr_many

    def test_edge_cases(self):
        assert deflated_sharpe_ratio(1.0, 0, 252) == 0.0  # No strategies
        assert deflated_sharpe_ratio(1.0, 1, 1) == 0.0  # 1 observation

    def test_bounded_zero_to_one(self):
        for sharpe in [-2, 0, 0.5, 1.0, 2.0, 5.0]:
            dsr = deflated_sharpe_ratio(sharpe, 7, 500, 1.0)
            assert 0 <= dsr <= 1


class TestRunStatisticalTests:
    def test_sufficient_data_runs_all_tests(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.003, 0.015, 200)
        result = run_statistical_tests(returns, "test", "NVDA", num_strategies_tested=7, seed=42)
        assert result.sufficient_data is True
        assert result.t_statistic != 0
        assert result.sharpe_ci_lower <= result.sharpe_ci_upper
        assert 0 <= result.dsr <= 1

    def test_insufficient_data_skips_tests(self):
        returns = np.array([0.01] * 10)  # < 20
        result = run_statistical_tests(returns, "test", "NVDA")
        assert result.sufficient_data is False
        assert result.p_value == 1.0
        assert result.dsr == 0.0

    def test_num_strategies_passed_through(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.003, 0.015, 200)
        result = run_statistical_tests(returns, "test", "NVDA", num_strategies_tested=7, seed=42)
        assert result.num_strategies_tested == 7
