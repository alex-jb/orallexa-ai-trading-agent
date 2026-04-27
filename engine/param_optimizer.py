"""
engine/param_optimizer.py
────────────────────────────────────────────────────────────────────────────
Optuna-based Bayesian hyperparameter optimization for existing strategies.

Optimizes strategy parameters to maximize out-of-sample Sharpe ratio
using walk-forward-aware train/test splitting.

Usage:
    from engine.param_optimizer import StrategyOptimizer
    optimizer = StrategyOptimizer(train_df, test_df)
    results = optimizer.optimize_all(n_trials=50)
    best = optimizer.get_best()
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np
import pandas as pd

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
except ImportError:
    optuna = None

from core.logger import get_logger
from engine.strategies import STRATEGY_REGISTRY, STRATEGY_DEFAULT_PARAMS, get_strategy
from engine.backtest import simple_backtest

logger = get_logger("param_optimizer")


# ═══════════════════════════════════════════════════════════════════════════
# SEARCH SPACES
# ═══════════════════════════════════════════════════════════════════════════

SEARCH_SPACES = {
    "double_ma": {
        "fast_period": ("int", 5, 30),
        "slow_period": ("int", 30, 100),
        "use_volume": ("categorical", [True, False]),
    },
    "macd_crossover": {
        "confirm_bars": ("int", 1, 5),
        "use_trend_filter": ("categorical", [True, False]),
        "hist_threshold": ("float", 0.0, 0.5),
    },
    "bollinger_breakout": {
        "require_squeeze": ("categorical", [True, False]),
        "rsi_filter_max": ("int", 60, 85),
    },
    "rsi_reversal": {
        "oversold": ("int", 15, 40),
        "overbought": ("int", 60, 85),
        "exit_rsi": ("int", 40, 65),
        "use_adx_filter": ("categorical", [True, False]),
    },
    "trend_momentum": {
        "rsi_min": ("int", 30, 50),
        "rsi_max": ("int", 60, 80),
        "use_macd": ("categorical", [True, False]),
        "use_volume": ("categorical", [True, False]),
        "stop_loss": ("float", 0.02, 0.10),
    },
    "alpha_combo": {
        "score_threshold": ("float", 2.0, 5.0),
        "momentum_period": ("int", 5, 20),
    },
    "dual_thrust": {
        "lookback": ("int", 2, 10),
        "k_up": ("float", 0.3, 1.0),
        "k_down": ("float", 0.3, 1.0),
    },
    "ensemble_vote": {
        "min_agree": ("int", 2, 5),
    },
    "regime_ensemble": {
        "trend_min_agree": ("int", 1, 4),
        "range_min_agree": ("int", 3, 6),
        "adx_trend": ("int", 15, 30),
    },
    "vwap_reversion": {
        "threshold":      ("float", 0.003, 0.03),
        "rsi_oversold":   ("int", 20, 40),
        "rsi_overbought": ("int", 60, 80),
    },
}


def _sample_params(trial: "optuna.Trial", strategy_name: str) -> dict:
    """Sample parameters from the search space for a given strategy."""
    space = SEARCH_SPACES.get(strategy_name, {})
    params = {}
    for name, spec in space.items():
        kind = spec[0]
        if kind == "int":
            params[name] = trial.suggest_int(name, spec[1], spec[2])
        elif kind == "float":
            params[name] = trial.suggest_float(name, spec[1], spec[2])
        elif kind == "categorical":
            params[name] = trial.suggest_categorical(name, spec[1])

    # Enforce constraints
    if strategy_name == "double_ma":
        if params.get("fast_period", 20) >= params.get("slow_period", 50):
            raise optuna.TrialPruned()
    if strategy_name == "rsi_reversal":
        if params.get("oversold", 30) >= params.get("overbought", 70):
            raise optuna.TrialPruned()
        if not (params.get("oversold", 30) < params.get("exit_rsi", 55) < params.get("overbought", 70)):
            raise optuna.TrialPruned()
    if strategy_name == "trend_momentum":
        if params.get("rsi_min", 40) >= params.get("rsi_max", 70):
            raise optuna.TrialPruned()

    return params


# ═══════════════════════════════════════════════════════════════════════════
# RESULT TYPES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class OptimizationResult:
    """Result of optimizing one strategy."""
    strategy_name: str
    default_params: dict
    best_params: dict
    default_sharpe: float
    optimized_sharpe: float
    improvement: float  # percentage improvement
    n_trials: int
    best_metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════
# BACKTEST HELPER
# ═══════════════════════════════════════════════════════════════════════════

def _run_and_score(strategy_fn, df: pd.DataFrame, params: dict) -> float:
    """Run strategy with params, backtest, return Sharpe ratio."""
    try:
        signal = strategy_fn(df, params)
        if signal is None or signal.sum() == 0:
            return -10.0  # Penalize zero-trade strategies

        bt_df = df.copy()
        bt_df["signal"] = signal
        result = simple_backtest(bt_df, signal_col="signal")

        net = result["net_strategy_return"]
        if net.std() < 1e-9:
            return 0.0
        sharpe = float(net.mean() / net.std() * np.sqrt(252))

        # Penalize strategies with very few trades
        n_trades = int(signal.diff().abs().fillna(0).sum())
        if n_trades < 5:
            sharpe *= 0.5

        return sharpe
    except Exception:
        return -10.0


# ═══════════════════════════════════════════════════════════════════════════
# OPTIMIZER
# ═══════════════════════════════════════════════════════════════════════════

class StrategyOptimizer:
    """
    Optuna-based hyperparameter optimizer for all registered strategies.

    Parameters:
        train_df: Training data with technical indicators
        test_df:  Test data for out-of-sample evaluation
    """

    def __init__(self, train_df: pd.DataFrame, test_df: pd.DataFrame):
        if optuna is None:
            raise ImportError("optuna is required: pip install optuna")
        self.train_df = train_df
        self.test_df = test_df
        self.results: dict[str, OptimizationResult] = {}

    def optimize_strategy(
        self,
        strategy_name: str,
        n_trials: int = 50,
    ) -> OptimizationResult:
        """Optimize a single strategy's parameters."""
        strategy_fn = get_strategy(strategy_name)
        if strategy_fn is None:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        default_params = STRATEGY_DEFAULT_PARAMS.get(strategy_name, {})

        # Baseline: default params on test data
        default_sharpe = _run_and_score(strategy_fn, self.test_df, default_params)

        # Optuna objective: maximize Sharpe on TRAIN data
        def objective(trial):
            params = _sample_params(trial, strategy_name)
            return _run_and_score(strategy_fn, self.train_df, params)

        study = optuna.create_study(direction="maximize")
        # Seed with default params
        study.enqueue_trial({
            k: v for k, v in default_params.items()
            if k in SEARCH_SPACES.get(strategy_name, {})
        })
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        best_params = {**default_params, **study.best_params}

        # Evaluate best params on TEST data (out-of-sample)
        optimized_sharpe = _run_and_score(strategy_fn, self.test_df, best_params)

        # Full test metrics for the best params
        signal = strategy_fn(self.test_df, best_params)
        best_metrics = {}
        if signal is not None and signal.sum() > 0:
            bt_df = self.test_df.copy()
            bt_df["signal"] = signal
            bt_result = simple_backtest(bt_df, signal_col="signal")
            net = bt_result["net_strategy_return"]
            cum = bt_result["CumulativeNetStrategyReturn"]
            best_metrics = {
                "sharpe": round(optimized_sharpe, 4),
                "total_return": round(float(cum.iloc[-1] - 1), 4),
                "max_drawdown": round(float(((cum - cum.cummax()) / cum.cummax().clip(lower=1e-9)).min()), 4),
                "n_trades": int(signal.diff().abs().fillna(0).sum()),
            }

        improvement = ((optimized_sharpe - default_sharpe) / abs(default_sharpe) * 100) if abs(default_sharpe) > 1e-6 else 0.0

        result = OptimizationResult(
            strategy_name=strategy_name,
            default_params=default_params,
            best_params=best_params,
            default_sharpe=round(default_sharpe, 4),
            optimized_sharpe=round(optimized_sharpe, 4),
            improvement=round(improvement, 1),
            n_trials=n_trials,
            best_metrics=best_metrics,
        )
        self.results[strategy_name] = result

        logger.info(
            "%s: default Sharpe=%.2f -> optimized=%.2f (%+.1f%%)",
            strategy_name, default_sharpe, optimized_sharpe, improvement,
        )
        return result

    def optimize_all(
        self,
        n_trials: int = 50,
        strategies: list[str] | None = None,
    ) -> dict[str, OptimizationResult]:
        """Optimize all (or specified) strategies."""
        targets = strategies or list(STRATEGY_REGISTRY.keys())
        for name in targets:
            if name not in SEARCH_SPACES:
                logger.warning("No search space defined for %s, skipping", name)
                continue
            self.optimize_strategy(name, n_trials=n_trials)
        return self.results

    def get_best(self) -> Optional[OptimizationResult]:
        """Return the strategy with the highest optimized Sharpe."""
        if not self.results:
            return None
        return max(self.results.values(), key=lambda r: r.optimized_sharpe)

    def summary_table(self) -> pd.DataFrame:
        """Return a comparison DataFrame of default vs optimized performance."""
        rows = []
        for r in self.results.values():
            rows.append({
                "strategy": r.strategy_name,
                "default_sharpe": r.default_sharpe,
                "optimized_sharpe": r.optimized_sharpe,
                "improvement_%": r.improvement,
                "n_trials": r.n_trials,
                "n_trades": r.best_metrics.get("n_trades", 0),
            })
        return pd.DataFrame(rows).sort_values("optimized_sharpe", ascending=False)
