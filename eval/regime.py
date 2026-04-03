"""
eval/regime.py
--------------------------------------------------------------------
Bull/bear regime detection and segmented performance analysis.

Uses 200-day SMA crossover to classify market regimes.
"""
from __future__ import annotations

from typing import Dict, Any

import numpy as np
import pandas as pd


def detect_regimes(df: pd.DataFrame, lookback: int = 200) -> pd.Series:
    """
    Classify each bar as 'bull' or 'bear' using SMA crossover.

    Bull = Close > SMA(lookback), Bear = Close <= SMA(lookback).

    Args:
        df: DataFrame with 'Close' column.
        lookback: SMA lookback period (default 200).

    Returns:
        pd.Series of 'bull' or 'bear' labels, indexed like df.
    """
    close = df["Close"] if "Close" in df.columns else df["close"]
    sma = close.rolling(window=lookback, min_periods=lookback).mean()
    regimes = pd.Series("bear", index=df.index)
    regimes[close > sma] = "bull"
    regimes[sma.isna()] = "neutral"
    return regimes


def segment_performance(
    backtest_df: pd.DataFrame,
    regimes: pd.Series,
) -> Dict[str, Dict[str, Any]]:
    """
    Compute metrics separately for bull and bear regimes.

    Args:
        backtest_df: Output from simple_backtest() with return columns.
        regimes: Series of 'bull'/'bear' labels aligned with backtest_df.

    Returns:
        {"bull": {sharpe, total_return, max_drawdown, win_rate, n_bars},
         "bear": {sharpe, total_return, max_drawdown, win_rate, n_bars}}
    """
    if "net_strategy_return" in backtest_df.columns:
        ret_col = "net_strategy_return"
    elif "strategy_return" in backtest_df.columns:
        ret_col = "strategy_return"
    else:
        return {"bull": _empty_metrics(), "bear": _empty_metrics()}

    aligned = regimes.reindex(backtest_df.index, method="ffill").fillna("neutral")
    result = {}

    for regime in ("bull", "bear"):
        mask = aligned == regime
        returns = backtest_df.loc[mask, ret_col].dropna()

        if len(returns) < 5:
            result[regime] = _empty_metrics()
            continue

        avg = returns.mean()
        std = returns.std()
        sharpe = float((avg / std) * np.sqrt(252)) if std > 0 else 0.0
        total_return = float((1 + returns).prod() - 1)

        cumulative = (1 + returns).cumprod()
        rolling_max = cumulative.cummax()
        drawdown = (cumulative - rolling_max) / rolling_max.replace(0, 1)
        max_dd = float(drawdown.min()) if len(drawdown) > 0 else 0.0

        win_rate = float((returns > 0).sum() / len(returns))

        result[regime] = {
            "sharpe": round(sharpe, 3),
            "total_return": round(total_return, 4),
            "max_drawdown": round(max_dd, 4),
            "win_rate": round(win_rate, 3),
            "n_bars": int(len(returns)),
        }

    return result


def _empty_metrics() -> Dict[str, Any]:
    return {
        "sharpe": 0.0,
        "total_return": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "n_bars": 0,
    }
