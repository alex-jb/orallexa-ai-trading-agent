"""
eval/statistical_tests.py
--------------------------------------------------------------------
Statistical significance tests for trading strategy evaluation.

Includes:
  - t-test on strategy returns vs. zero
  - Bootstrap confidence intervals on Sharpe ratio
  - Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014)

Minimum 20 trades required for meaningful statistical tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import stats


MIN_TRADES_FOR_STATS = 20


@dataclass
class StatisticalTestResult:
    strategy_name: str
    ticker: str
    n_observations: int
    sufficient_data: bool

    # t-test: are returns significantly different from zero?
    t_statistic: float = 0.0
    p_value: float = 1.0
    returns_significant: bool = False

    # Bootstrap confidence intervals on Sharpe
    sharpe_ci_lower: float = 0.0
    sharpe_ci_upper: float = 0.0
    sharpe_point: float = 0.0

    # Deflated Sharpe Ratio
    dsr: float = 0.0
    dsr_passed: bool = False
    num_strategies_tested: int = 1


@dataclass
class AggregateStatResult:
    """Aggregate statistical results across all strategies for a ticker."""
    ticker: str
    results: list  # List[StatisticalTestResult]
    num_significant: int = 0
    num_dsr_passed: int = 0


def ttest_returns(returns: np.ndarray) -> tuple[float, float]:
    """
    One-sample t-test: are strategy returns significantly > 0?

    Returns:
        (t_statistic, p_value) — one-sided test.
    """
    if len(returns) < MIN_TRADES_FOR_STATS:
        return 0.0, 1.0

    t_stat, p_two = stats.ttest_1samp(returns, 0.0)
    # One-sided: we care if returns > 0
    p_one = p_two / 2 if t_stat > 0 else 1.0 - p_two / 2
    return float(t_stat), float(p_one)


def bootstrap_sharpe_ci(
    returns: np.ndarray,
    n_bootstrap: int = 5000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float, float]:
    """
    Bootstrap confidence interval for the annualized Sharpe ratio.

    Returns:
        (lower_bound, point_estimate, upper_bound)
    """
    if len(returns) < MIN_TRADES_FOR_STATS:
        return 0.0, 0.0, 0.0

    rng = np.random.default_rng(seed)
    n = len(returns)

    def _sharpe(r: np.ndarray) -> float:
        s = r.std()
        if s == 0 or np.isnan(s):
            return 0.0
        return float((r.mean() / s) * np.sqrt(252))

    point = _sharpe(returns)
    boot_sharpes = np.zeros(n_bootstrap)

    for i in range(n_bootstrap):
        sample = rng.choice(returns, size=n, replace=True)
        boot_sharpes[i] = _sharpe(sample)

    alpha = (1 - confidence) / 2
    lower = float(np.percentile(boot_sharpes, alpha * 100))
    upper = float(np.percentile(boot_sharpes, (1 - alpha) * 100))

    return lower, point, upper


def deflated_sharpe_ratio(
    observed_sharpe: float,
    num_strategies: int,
    n_observations: int,
    sharpe_std: float = 1.0,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """
    Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014).

    Corrects for multiple testing: the more strategies you test,
    the higher the chance of finding a spuriously good Sharpe.

    DSR > 0.5 implies the Sharpe is unlikely to be a false discovery.

    Args:
        observed_sharpe: The annualized Sharpe ratio of the strategy.
        num_strategies: Number of strategies tested (trial count).
        n_observations: Number of return observations.
        sharpe_std: Standard deviation of Sharpe across strategies.
        skewness: Skewness of the return distribution.
        kurtosis: Kurtosis of the return distribution.

    Returns:
        DSR value between 0 and 1.
    """
    if num_strategies < 1 or n_observations < 2:
        return 0.0

    # Expected maximum Sharpe under null (Euler-Mascheroni approximation)
    euler_mascheroni = 0.5772156649
    e_max_sharpe = sharpe_std * (
        (1 - euler_mascheroni) * stats.norm.ppf(1 - 1 / num_strategies)
        + euler_mascheroni * stats.norm.ppf(1 - 1 / (num_strategies * np.e))
    )

    # Sharpe ratio standard error (Lo 2002, adjusted for non-normality)
    se = np.sqrt(
        (1 + 0.5 * observed_sharpe**2 - skewness * observed_sharpe
         + (kurtosis - 3) / 4 * observed_sharpe**2) / n_observations
    )

    if se <= 0:
        return 0.0

    # PSR: probability that the true Sharpe exceeds the benchmark
    z = (observed_sharpe - e_max_sharpe) / se
    dsr = float(stats.norm.cdf(z))

    return max(0.0, min(1.0, dsr))


def run_statistical_tests(
    trade_returns: np.ndarray,
    strategy_name: str,
    ticker: str,
    num_strategies_tested: int = 1,
    seed: int | None = None,
) -> StatisticalTestResult:
    """
    Run all statistical tests on a strategy's trade returns.

    Args:
        trade_returns: Array of non-zero trade returns.
        strategy_name: Name for reporting.
        ticker: Ticker symbol.
        num_strategies_tested: Total number of strategies evaluated
            in this harness run (for DSR correction).
        seed: Random seed for bootstrap reproducibility.

    Returns:
        StatisticalTestResult with all test outcomes.
    """
    n = len(trade_returns)
    sufficient = n >= MIN_TRADES_FOR_STATS

    if not sufficient:
        return StatisticalTestResult(
            strategy_name=strategy_name,
            ticker=ticker,
            n_observations=n,
            sufficient_data=False,
            num_strategies_tested=num_strategies_tested,
        )

    # t-test
    t_stat, p_val = ttest_returns(trade_returns)

    # Bootstrap Sharpe CI
    ci_lower, sharpe_point, ci_upper = bootstrap_sharpe_ci(
        trade_returns, seed=seed,
    )

    # Deflated Sharpe Ratio
    skew = float(stats.skew(trade_returns)) if n > 2 else 0.0
    kurt = float(stats.kurtosis(trade_returns, fisher=False)) if n > 3 else 3.0

    # Estimate sharpe_std from bootstrap
    rng = np.random.default_rng(seed)
    boot_sharpes = []
    for _ in range(1000):
        s = rng.choice(trade_returns, size=n, replace=True)
        std_s = s.std()
        if std_s > 0:
            boot_sharpes.append((s.mean() / std_s) * np.sqrt(252))
    sharpe_std = float(np.std(boot_sharpes)) if boot_sharpes else 1.0

    dsr = deflated_sharpe_ratio(
        observed_sharpe=sharpe_point,
        num_strategies=num_strategies_tested,
        n_observations=n,
        sharpe_std=sharpe_std,
        skewness=skew,
        kurtosis=kurt,
    )

    return StatisticalTestResult(
        strategy_name=strategy_name,
        ticker=ticker,
        n_observations=n,
        sufficient_data=True,
        t_statistic=t_stat,
        p_value=p_val,
        returns_significant=p_val < 0.05,
        sharpe_ci_lower=ci_lower,
        sharpe_ci_upper=ci_upper,
        sharpe_point=sharpe_point,
        dsr=dsr,
        dsr_passed=dsr > 0.5,
        num_strategies_tested=num_strategies_tested,
    )
