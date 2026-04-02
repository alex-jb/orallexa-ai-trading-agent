"""
engine/ensemble.py
────────────────────────────────────────────────────────────────────────────
Strategy ensemble methods — combine multiple strategies via voting or
weighted stacking.

Three ensemble modes:
  1. Majority voting: long if >50% of strategies say long
  2. Sharpe-weighted: weight each strategy's signal by its walk-forward Sharpe
  3. Rank-weighted: weight by inverse rank (best strategy gets highest weight)

Usage:
    from engine.ensemble import StrategyEnsemble
    ensemble = StrategyEnsemble(train_df, test_df)
    results = ensemble.run_all_ensembles()
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np
import pandas as pd

from core.logger import get_logger
from engine.strategies import STRATEGY_REGISTRY, STRATEGY_DEFAULT_PARAMS, get_strategy
from engine.backtest import simple_backtest

logger = get_logger("ensemble")


@dataclass
class EnsembleResult:
    """Result of a single ensemble method."""
    method: str
    sharpe: float
    total_return: float
    max_drawdown: float
    win_rate: float
    n_trades: int
    weights: dict  # strategy_name -> weight
    signal: Optional[pd.Series] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("signal", None)
        return d


def _get_strategy_signals(
    df: pd.DataFrame,
    strategies: list[str] | None = None,
    custom_params: dict | None = None,
) -> dict[str, pd.Series]:
    """Run all strategies and collect their signals."""
    targets = strategies or list(STRATEGY_REGISTRY.keys())
    custom_params = custom_params or {}
    signals = {}

    for name in targets:
        fn = get_strategy(name)
        if fn is None:
            continue
        params = {**STRATEGY_DEFAULT_PARAMS.get(name, {}), **custom_params.get(name, {})}
        try:
            sig = fn(df, params)
            if sig is not None and len(sig) == len(df):
                signals[name] = sig.fillna(0).astype(int)
        except Exception as e:
            logger.warning("Strategy %s failed: %s", name, e)

    return signals


def _backtest_signal(df: pd.DataFrame, signal: pd.Series) -> dict:
    """Backtest a signal and return metrics."""
    bt_df = df.copy()
    bt_df["signal"] = signal
    result = simple_backtest(bt_df, signal_col="signal")

    net = result["net_strategy_return"]
    cum = result["CumulativeNetStrategyReturn"]

    sharpe = float(net.mean() / net.std() * np.sqrt(252)) if net.std() > 1e-9 else 0.0
    total = float(cum.iloc[-1] - 1) if len(cum) > 0 else 0.0
    maxdd = float(((cum - cum.cummax()) / cum.cummax().clip(lower=1e-9)).min()) if len(cum) > 0 else 0.0

    shifted = signal.shift(1).fillna(0)
    in_pos = shifted != 0
    winrate = float((net[in_pos] > 0).mean()) if in_pos.any() else 0.0
    n_trades = int(signal.diff().abs().fillna(0).sum())

    return {
        "sharpe": round(sharpe, 4),
        "total_return": round(total, 4),
        "max_drawdown": round(maxdd, 4),
        "win_rate": round(winrate, 4),
        "n_trades": n_trades,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ENSEMBLE METHODS
# ═══════════════════════════════════════════════════════════════════════════

def majority_vote(signals: dict[str, pd.Series]) -> pd.Series:
    """Long if majority of strategies are long. Flat otherwise."""
    if not signals:
        raise ValueError("No signals provided")
    matrix = pd.DataFrame(signals)
    # Count how many strategies are long (signal > 0)
    long_count = (matrix > 0).sum(axis=1)
    threshold = len(signals) / 2.0
    return (long_count > threshold).astype(int)


def sharpe_weighted(
    signals: dict[str, pd.Series],
    sharpes: dict[str, float],
) -> pd.Series:
    """Weight signals by each strategy's Sharpe ratio. Long if weighted sum > 0.5."""
    if not signals:
        raise ValueError("No signals provided")

    # Only use strategies with positive Sharpe
    positive = {k: max(v, 0) for k, v in sharpes.items() if k in signals}
    total_w = sum(positive.values())
    if total_w < 1e-9:
        return majority_vote(signals)

    weights = {k: v / total_w for k, v in positive.items()}

    matrix = pd.DataFrame(signals)
    weighted = sum(matrix[name] * w for name, w in weights.items() if name in matrix.columns)
    return (weighted > 0.5).astype(int)


def rank_weighted(
    signals: dict[str, pd.Series],
    sharpes: dict[str, float],
) -> pd.Series:
    """Weight by inverse rank (best gets highest weight)."""
    if not signals:
        raise ValueError("No signals provided")

    # Sort by Sharpe descending, assign weights by rank
    ranked = sorted(
        [(k, v) for k, v in sharpes.items() if k in signals],
        key=lambda x: x[1], reverse=True,
    )
    n = len(ranked)
    weights = {name: (n - i) / (n * (n + 1) / 2) for i, (name, _) in enumerate(ranked)}

    matrix = pd.DataFrame(signals)
    weighted = sum(matrix[name] * w for name, w in weights.items() if name in matrix.columns)
    return (weighted > 0.5).astype(int)


# ═══════════════════════════════════════════════════════════════════════════
# ENSEMBLE RUNNER
# ═══════════════════════════════════════════════════════════════════════════

class StrategyEnsemble:
    """
    Runs all ensemble methods and compares against individual strategies.

    Parameters:
        train_df: Training data with technical indicators
        test_df:  Test data for evaluation
    """

    def __init__(self, train_df: pd.DataFrame, test_df: pd.DataFrame):
        self.train_df = train_df
        self.test_df = test_df
        self.results: dict[str, EnsembleResult] = {}
        self._individual_sharpes: dict[str, float] = {}

    def _compute_individual_sharpes(self, signals: dict[str, pd.Series]) -> dict[str, float]:
        """Compute Sharpe for each strategy on train data."""
        sharpes = {}
        for name, signal in signals.items():
            metrics = _backtest_signal(self.train_df, signal)
            sharpes[name] = metrics["sharpe"]
        self._individual_sharpes = sharpes
        return sharpes

    def run_all_ensembles(
        self,
        strategies: list[str] | None = None,
        custom_params: dict | None = None,
    ) -> dict[str, EnsembleResult]:
        """Run all three ensemble methods and return results."""
        # Get signals on both train and test
        train_signals = _get_strategy_signals(self.train_df, strategies, custom_params)
        test_signals = _get_strategy_signals(self.test_df, strategies, custom_params)

        if not train_signals or not test_signals:
            logger.warning("No valid strategy signals produced")
            return {}

        # Compute Sharpe on train for weighting
        sharpes = self._compute_individual_sharpes(train_signals)
        logger.info("Individual train Sharpes: %s",
                     {k: f"{v:.2f}" for k, v in sorted(sharpes.items(), key=lambda x: -x[1])})

        # Run each ensemble method
        methods = [
            ("majority_vote", majority_vote, {"signals": test_signals}),
            ("sharpe_weighted", sharpe_weighted, {"signals": test_signals, "sharpes": sharpes}),
            ("rank_weighted", rank_weighted, {"signals": test_signals, "sharpes": sharpes}),
        ]

        for method_name, fn, kwargs in methods:
            try:
                ensemble_signal = fn(**kwargs)
                metrics = _backtest_signal(self.test_df, ensemble_signal)

                # Build weights dict for this method
                if method_name == "majority_vote":
                    weights = {k: 1.0 / len(test_signals) for k in test_signals}
                elif method_name == "sharpe_weighted":
                    positive = {k: max(v, 0) for k, v in sharpes.items() if k in test_signals}
                    total_w = sum(positive.values())
                    weights = {k: round(v / total_w, 3) for k, v in positive.items()} if total_w > 0 else {}
                else:
                    ranked = sorted([(k, v) for k, v in sharpes.items() if k in test_signals], key=lambda x: -x[1])
                    n = len(ranked)
                    weights = {name: round((n - i) / (n * (n + 1) / 2), 3) for i, (name, _) in enumerate(ranked)}

                self.results[method_name] = EnsembleResult(
                    method=method_name,
                    sharpe=metrics["sharpe"],
                    total_return=metrics["total_return"],
                    max_drawdown=metrics["max_drawdown"],
                    win_rate=metrics["win_rate"],
                    n_trades=metrics["n_trades"],
                    weights=weights,
                    signal=ensemble_signal,
                )
                logger.info("  %s: Sharpe=%.2f Return=%.1f%% Trades=%d",
                            method_name, metrics["sharpe"], metrics["total_return"] * 100, metrics["n_trades"])
            except Exception as e:
                logger.warning("Ensemble %s failed: %s", method_name, e)

        return self.results

    def get_best(self) -> Optional[EnsembleResult]:
        """Return ensemble method with highest Sharpe."""
        if not self.results:
            return None
        return max(self.results.values(), key=lambda r: r.sharpe)

    def comparison_table(self) -> pd.DataFrame:
        """Compare ensemble methods against individual strategies."""
        rows = []

        # Individual strategies
        for name, sharpe in self._individual_sharpes.items():
            rows.append({"strategy": name, "type": "individual", "sharpe": sharpe})

        # Ensembles
        for r in self.results.values():
            rows.append({
                "strategy": r.method,
                "type": "ensemble",
                "sharpe": r.sharpe,
                "total_return": r.total_return,
                "max_drawdown": r.max_drawdown,
                "n_trades": r.n_trades,
            })

        return pd.DataFrame(rows).sort_values("sharpe", ascending=False)
