"""
eval/walk_forward.py
--------------------------------------------------------------------
Expanding-window walk-forward validation for trading strategies.

Splits historical data into train/test windows, computes indicators
per-window with a warmup buffer to prevent leakage, runs backtest
on each out-of-sample window, and collects OOS metrics.

Default: 252-day initial train, 63-day test windows, min 4 windows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Any, List

import numpy as np
import pandas as pd


WARMUP_BARS = 50  # Extra bars before each window for indicator warmup
OPTIMIZE_TRIALS_BASE = 20   # Base Optuna trials; scaled by param count
OPTIMIZE_TRIALS_PER_PARAM = 8  # Extra trials per parameter dimension


@dataclass
class WindowResult:
    window_idx: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    num_trades: int
    sharpe: float
    total_return: float
    max_drawdown: float
    win_rate: float
    information_ratio: float


@dataclass
class WalkForwardResult:
    strategy_name: str
    num_windows: int
    windows: List[WindowResult] = field(default_factory=list)
    avg_oos_sharpe: float = 0.0
    pct_positive_sharpe: float = 0.0
    avg_oos_return: float = 0.0
    avg_information_ratio: float = 0.0
    passed: bool = False


def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute technical indicators on a DataFrame slice."""
    from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2
    ta = TechnicalAnalysisSkillV2(df)
    ta.add_indicators()
    return ta.copy()


def _optimize_on_train(
    full_df: pd.DataFrame,
    train_start_idx: int,
    train_end_idx: int,
    strategy_fn: Callable,
    strategy_name: str,
    default_params: Dict[str, Any],
    n_trials: int = 0,
) -> Dict[str, Any]:
    """Optimize strategy params on training window using Optuna.

    Trial count is adaptive: base + extra per parameter dimension.
    Returns best params or default if optimization fails.
    """
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        from engine.param_optimizer import SEARCH_SPACES, _sample_params
        from engine.backtest import simple_backtest
    except ImportError:
        return default_params

    if strategy_name not in SEARCH_SPACES:
        return default_params

    # Adaptive trial count based on search space dimensionality
    if n_trials <= 0:
        n_params = len(SEARCH_SPACES[strategy_name])
        n_trials = OPTIMIZE_TRIALS_BASE + n_params * OPTIMIZE_TRIALS_PER_PARAM

    # Prepare training data with indicators
    train_raw = full_df.iloc[train_start_idx:train_end_idx].copy()
    if len(train_raw) < 60:
        return default_params
    train_df = _compute_indicators(train_raw)

    def objective(trial: optuna.Trial) -> float:
        try:
            params = _sample_params(trial, strategy_name)
        except optuna.TrialPruned:
            return -10.0
        try:
            signal = strategy_fn(train_df, params)
            if signal is None or signal.abs().sum() == 0:
                return -10.0
            bt = train_df.copy()
            bt["signal"] = signal
            result = simple_backtest(bt, signal_col="signal")
            net = result["net_strategy_return"]
            if net.std() < 1e-9:
                return 0.0
            sharpe = float(net.mean() / net.std() * (252 ** 0.5))
            # Penalize very few trades (encourages signal generation)
            n_trades = int(signal.diff().abs().fillna(0).sum())
            if n_trades < 3:
                sharpe *= 0.3
            elif n_trades < 5:
                sharpe *= 0.6
            # Penalize extreme Sharpe on train (likely overfit)
            if sharpe > 3.0:
                sharpe = 3.0
            return sharpe
        except Exception:
            return -10.0

    study = optuna.create_study(direction="maximize")
    # Seed with default params
    try:
        study.enqueue_trial(default_params)
    except Exception:
        pass
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    # Only use optimized params if they meaningfully beat the default
    # This prevents overfitting to noise in small training windows
    default_score = objective(
        type("FakeTrial", (), {
            "suggest_int": lambda s, n, lo, hi: default_params.get(n, lo),
            "suggest_float": lambda s, n, lo, hi: default_params.get(n, lo),
            "suggest_categorical": lambda s, n, choices: default_params.get(n, choices[0]),
        })()
    )
    if study.best_value > default_score + 0.1:
        return study.best_params
    return default_params


def _run_single_window(
    full_df: pd.DataFrame,
    train_start_idx: int,
    train_end_idx: int,
    test_start_idx: int,
    test_end_idx: int,
    strategy_fn: Callable,
    params: Dict[str, Any],
    window_idx: int,
    strategy_name: str = "",
    adaptive: bool = False,
) -> WindowResult:
    """Run backtest on a single walk-forward window."""
    from engine.backtest import simple_backtest
    from engine.evaluation import evaluate

    # Adaptive: optimize params on training window
    if adaptive and strategy_name:
        params = _optimize_on_train(
            full_df, train_start_idx, train_end_idx,
            strategy_fn, strategy_name, params,
        )

    # Include warmup buffer before test window for indicator computation
    warmup_start = max(0, test_start_idx - WARMUP_BARS)
    test_slice_raw = full_df.iloc[warmup_start:test_end_idx].copy()

    # Compute indicators on the slice (prevents future data leakage)
    test_with_indicators = _compute_indicators(test_slice_raw)

    # Trim to actual test period (remove warmup bars)
    actual_test_start = test_start_idx - warmup_start
    test_df = test_with_indicators.iloc[actual_test_start:].copy()

    if len(test_df) < 5:
        return WindowResult(
            window_idx=window_idx,
            train_start=str(full_df.index[train_start_idx].date()),
            train_end=str(full_df.index[train_end_idx - 1].date()),
            test_start=str(full_df.index[test_start_idx].date()),
            test_end=str(full_df.index[min(test_end_idx - 1, len(full_df) - 1)].date()),
            num_trades=0, sharpe=0.0, total_return=0.0,
            max_drawdown=0.0, win_rate=0.0, information_ratio=0.0,
        )

    # Generate signals
    try:
        signals = strategy_fn(test_df, params)
        test_df["signal"] = signals.values
    except Exception:
        test_df["signal"] = 0

    # Run backtest
    bt_result = simple_backtest(test_df, params=params, signal_col="signal")
    metrics = evaluate(bt_result)

    # Information ratio: (strategy return - market return) / tracking error
    if "strategy_return" in bt_result.columns and "market_return" in bt_result.columns:
        excess = bt_result["strategy_return"] - bt_result["market_return"]
        excess = excess.dropna()
        te = excess.std()
        ir = float(excess.mean() / te * np.sqrt(252)) if te > 0 else 0.0
    else:
        ir = 0.0

    num_trades = int((test_df["signal"].diff().abs() > 0).sum())

    return WindowResult(
        window_idx=window_idx,
        train_start=str(full_df.index[train_start_idx].date()),
        train_end=str(full_df.index[train_end_idx - 1].date()),
        test_start=str(full_df.index[test_start_idx].date()),
        test_end=str(full_df.index[min(test_end_idx - 1, len(full_df) - 1)].date()),
        num_trades=num_trades,
        sharpe=metrics["sharpe"],
        total_return=metrics["total_return"],
        max_drawdown=metrics["max_drawdown"],
        win_rate=metrics["win_rate"],
        information_ratio=ir,
    )


def run_walk_forward(
    df: pd.DataFrame,
    strategy_fn: Callable,
    strategy_name: str,
    params: Dict[str, Any],
    initial_train_days: int = 252,
    test_days: int = 63,
    min_windows: int = 4,
    adaptive: bool = False,
) -> WalkForwardResult:
    """
    Run expanding-window walk-forward validation.

    Args:
        df: Raw OHLCV DataFrame (no indicators yet).
        strategy_fn: Strategy function from engine/strategies.py.
        strategy_name: Name for reporting.
        params: Strategy parameters.
        initial_train_days: Initial training window size.
        test_days: Test window size.
        min_windows: Minimum number of windows required.

    Returns:
        WalkForwardResult with per-window metrics and aggregates.
    """
    n = len(df)
    total_needed = initial_train_days + min_windows * test_days

    if n < total_needed:
        return WalkForwardResult(
            strategy_name=strategy_name,
            num_windows=0,
            passed=False,
        )

    windows = []
    window_idx = 0
    test_start = initial_train_days

    while test_start + test_days <= n:
        train_start = 0  # Expanding window
        train_end = test_start
        test_end = min(test_start + test_days, n)

        result = _run_single_window(
            full_df=df,
            train_start_idx=train_start,
            train_end_idx=train_end,
            test_start_idx=test_start,
            test_end_idx=test_end,
            strategy_fn=strategy_fn,
            params=params,
            window_idx=window_idx,
            strategy_name=strategy_name,
            adaptive=adaptive,
        )
        windows.append(result)
        window_idx += 1
        test_start += test_days

    if len(windows) < min_windows:
        return WalkForwardResult(
            strategy_name=strategy_name,
            num_windows=len(windows),
            windows=windows,
            passed=False,
        )

    sharpes = [w.sharpe for w in windows]
    returns = [w.total_return for w in windows]
    irs = [w.information_ratio for w in windows]
    pct_positive = sum(1 for s in sharpes if s > 0) / len(sharpes)

    return WalkForwardResult(
        strategy_name=strategy_name,
        num_windows=len(windows),
        windows=windows,
        avg_oos_sharpe=float(np.mean(sharpes)),
        pct_positive_sharpe=pct_positive,
        avg_oos_return=float(np.mean(returns)),
        avg_information_ratio=float(np.mean(irs)),
        passed=pct_positive > 0.5,  # Pass if >50% windows have positive Sharpe
    )
