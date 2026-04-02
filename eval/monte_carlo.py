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

    # Monte Carlo simulation
    sim_sharpes = np.zeros(n_iterations)
    sim_returns = np.zeros(n_iterations)
    sim_drawdowns = np.zeros(n_iterations)
    equity_sample = []
    sample_interval = max(1, n_iterations // 20)

    for i in range(n_iterations):
        shuffled = rng.permutation(trade_returns)
        sim_sharpes[i] = _compute_sharpe(shuffled)
        sim_returns[i] = float((1 + shuffled).prod() - 1)

        equity = np.cumprod(1 + shuffled)
        sim_drawdowns[i] = _compute_max_drawdown(equity)

        if i % sample_interval == 0:
            equity_sample.append(equity.tolist())

    # Percentile statistics
    pcts = [5, 25, 50, 75, 95]
    sharpe_pcts = {p: float(np.percentile(sim_sharpes, p)) for p in pcts}
    return_pcts = {p: float(np.percentile(sim_returns, p)) for p in pcts}
    dd_pcts = {p: float(np.percentile(sim_drawdowns, p)) for p in pcts}

    # Where does the original strategy fall?
    sharpe_rank = float(np.mean(sim_sharpes <= original_sharpe) * 100)

    # Probability of ruin (total return < -50%)
    ruin_pct = float(np.mean(sim_returns < -0.5) * 100)

    # Pass/fail: strategy Sharpe exceeds 75th percentile of simulated
    passed = original_sharpe > sharpe_pcts[75]

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
