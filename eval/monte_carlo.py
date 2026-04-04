"""
eval/monte_carlo.py
--------------------------------------------------------------------
Monte Carlo simulation for strategy robustness testing.

Shuffles non-zero trade returns to generate N simulated equity curves.
Produces confidence bands, probability of ruin, and percentile stats.

Default: 1,000 iterations. Configurable via n_iterations parameter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np
import pandas as pd


@dataclass
class MonteCarloResult:
    strategy_name: str
    ticker: str
    n_iterations: int
    n_trade_returns: int
    original_sharpe: float
    original_total_return: float

    # Percentile statistics from simulated runs
    sharpe_percentiles: dict = field(default_factory=dict)  # {5, 25, 50, 75, 95}
    return_percentiles: dict = field(default_factory=dict)
    drawdown_percentiles: dict = field(default_factory=dict)

    # Strategy vs. random
    sharpe_percentile_rank: float = 0.0  # Where original Sharpe falls in simulated distribution
    probability_of_ruin: float = 0.0     # % of simulations with total return < -50%

    # Simulated equity curves for charting (sampled)
    equity_curves_sample: list = field(default_factory=list)  # List of lists, ~20 curves

    passed: bool = False


def _compute_sharpe(returns: np.ndarray) -> float:
    """Annualized Sharpe ratio from daily returns."""
    if len(returns) == 0:
        return 0.0
    std = returns.std()
    if std == 0 or np.isnan(std):
        return 0.0
    return float((returns.mean() / std) * np.sqrt(252))


def _compute_max_drawdown(equity_curve: np.ndarray) -> float:
    """Maximum drawdown from an equity curve array."""
    if len(equity_curve) < 2:
        return 0.0
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - peak) / np.where(peak > 0, peak, 1.0)
    return float(drawdown.min())


def run_monte_carlo(
    backtest_df: pd.DataFrame,
    strategy_name: str,
    ticker: str,
    n_iterations: int = 1000,
    seed: int | None = None,
) -> MonteCarloResult:
    """
    Monte Carlo simulation by shuffling trade returns.

    Extracts only bars where the strategy had a position (non-zero signal),
    shuffles those returns, and reconstructs equity curves. This avoids
    the sparse-return problem where shuffling mostly-zero daily returns
    produces meaningless Sharpe ratios.

    Args:
        backtest_df: Output from simple_backtest() with signal and return columns.
        strategy_name: Name for reporting.
        ticker: Ticker symbol for reporting.
        n_iterations: Number of Monte Carlo iterations.
        seed: Random seed for reproducibility (None = random).

    Returns:
        MonteCarloResult with percentile statistics and pass/fail.
    """
    rng = np.random.default_rng(seed)

    # Extract returns for bars where strategy had a position
    if "signal" in backtest_df.columns:
        signal_col = "signal"
    elif "Signal" in backtest_df.columns:
        signal_col = "Signal"
    else:
        return MonteCarloResult(
            strategy_name=strategy_name, ticker=ticker,
            n_iterations=n_iterations, n_trade_returns=0,
            original_sharpe=0.0, original_total_return=0.0, passed=False,
        )

    if "net_strategy_return" in backtest_df.columns:
        return_col = "net_strategy_return"
    elif "strategy_return" in backtest_df.columns:
        return_col = "strategy_return"
    else:
        return MonteCarloResult(
            strategy_name=strategy_name, ticker=ticker,
            n_iterations=n_iterations, n_trade_returns=0,
            original_sharpe=0.0, original_total_return=0.0, passed=False,
        )

    # Filter to bars with active position (non-zero signal)
    mask = backtest_df[signal_col].shift(1).fillna(0) != 0
    trade_returns = backtest_df.loc[mask, return_col].dropna().values

    if len(trade_returns) < 5:
        return MonteCarloResult(
            strategy_name=strategy_name, ticker=ticker,
            n_iterations=n_iterations, n_trade_returns=len(trade_returns),
            original_sharpe=0.0, original_total_return=0.0, passed=False,
        )

    # Clip extreme returns to prevent overflow
    trade_returns = np.clip(trade_returns, -0.5, 0.5)

    # Original strategy metrics
    original_sharpe = _compute_sharpe(trade_returns)
    original_total_return = float((1 + trade_returns).prod() - 1)

    # Monte Carlo simulation — vectorized batch approach
    n = len(trade_returns)

    # Generate all shuffled permutations at once: (n_iterations, n)
    indices = np.zeros((n_iterations, n), dtype=int)
    for i in range(n_iterations):
        indices[i] = rng.permutation(n)
    shuffled_matrix = trade_returns[indices]  # (n_iterations, n)

    # Vectorized Sharpe
    means = shuffled_matrix.mean(axis=1)
    stds = shuffled_matrix.std(axis=1)
    safe_stds = np.where(stds > 0, stds, 1.0)
    sim_sharpes = (means / safe_stds) * np.sqrt(252)
    sim_sharpes = np.where(stds > 0, sim_sharpes, 0.0)

    # Vectorized total returns
    equity_matrix = np.cumprod(1 + shuffled_matrix, axis=1)  # (n_iterations, n)
    sim_returns = equity_matrix[:, -1] - 1.0

    # Vectorized max drawdown
    peaks = np.maximum.accumulate(equity_matrix, axis=1)
    drawdowns = (equity_matrix - peaks) / np.where(peaks > 0, peaks, 1.0)
    sim_drawdowns = drawdowns.min(axis=1)

    # Sample equity curves for charting
    sample_interval = max(1, n_iterations // 20)
    equity_sample = [equity_matrix[i].tolist() for i in range(0, n_iterations, sample_interval)]

    # Percentile statistics
    pcts = [5, 25, 50, 75, 95]
    sharpe_pcts = {p: float(np.percentile(sim_sharpes, p)) for p in pcts}
    return_pcts = {p: float(np.percentile(sim_returns, p)) for p in pcts}
    dd_pcts = {p: float(np.percentile(sim_drawdowns, p)) for p in pcts}

    # Where does the original strategy fall?
    sharpe_rank = float(np.mean(sim_sharpes <= original_sharpe) * 100)

    # Probability of ruin (total return < -50%)
    ruin_pct = float(np.mean(sim_returns < -0.5) * 100)

    # Pass/fail: strategy Sharpe ranks above 60th percentile of simulated
    # (Using percentile rank instead of absolute comparison, since shuffled
    # returns preserve the mean and can have high Sharpe even randomly)
    passed = sharpe_rank >= 60.0

    return MonteCarloResult(
        strategy_name=strategy_name,
        ticker=ticker,
        n_iterations=n_iterations,
        n_trade_returns=len(trade_returns),
        original_sharpe=original_sharpe,
        original_total_return=original_total_return,
        sharpe_percentiles=sharpe_pcts,
        return_percentiles=return_pcts,
        drawdown_percentiles=dd_pcts,
        sharpe_percentile_rank=sharpe_rank,
        probability_of_ruin=ruin_pct,
        equity_curves_sample=equity_sample,
        passed=passed,
    )
