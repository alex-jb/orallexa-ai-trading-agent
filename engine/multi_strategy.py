"""
engine/multi_strategy.py
────────────────────────────────────────────────────────────────────────────
Multi-strategy runner for Orallexa.
Runs all strategies in parallel on the same data,
ranks by Sharpe ratio, and returns the best.

Integrates with:
  - engine/strategies.py       (strategy library)
  - skills/technical_analysis_v2.py  (enhanced indicators)
  - engine/backtest.py         (existing backtest engine)
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple

from engine.strategies import STRATEGY_REGISTRY, STRATEGY_DEFAULT_PARAMS, STRATEGY_DESCRIPTIONS


# ══════════════════════════════════════════════════════════════════════════
# LIGHTWEIGHT BACKTEST (compatible with existing engine)
# ══════════════════════════════════════════════════════════════════════════

def _run_strategy_backtest(
    df: pd.DataFrame,
    signal: pd.Series,
    transaction_cost: float = 0.001,
    slippage: float = 0.001,
) -> Dict[str, float]:
    """
    Vectorised backtest given a pre-computed signal series.
    Returns a dict of performance metrics.
    """
    cost = transaction_cost + slippage
    returns = df["Close"].pct_change().fillna(0)

    # Position: signal shifted by 1 (no look-ahead)
    position = signal.shift(1).fillna(0)

    # Detect trades (position changes)
    trades = position.diff().abs().fillna(0)
    cost_series = trades * cost

    gross_ret = position * returns
    net_ret   = gross_ret - cost_series

    cum_gross = (1 + gross_ret).cumprod()
    cum_net   = (1 + net_ret).cumprod()
    cum_mkt   = (1 + returns).cumprod()

    # Metrics
    n_trades  = int(trades[trades > 0].count())
    total_ret = float(cum_net.iloc[-1] - 1)
    mkt_ret   = float(cum_mkt.iloc[-1] - 1)

    # Sharpe (annualised, daily returns)
    if net_ret.std() > 1e-9:
        sharpe = float(net_ret.mean() / net_ret.std() * np.sqrt(252))
    else:
        sharpe = 0.0

    # Max drawdown
    rolling_max = cum_net.cummax()
    drawdown    = (cum_net - rolling_max) / (rolling_max + 1e-9)
    max_dd      = float(drawdown.min())

    # Win rate (on individual trade returns)
    trade_rets = net_ret[position > 0]
    win_rate   = float((trade_rets > 0).mean()) if len(trade_rets) > 0 else 0.0

    # Calmar ratio
    calmar = total_ret / abs(max_dd) if abs(max_dd) > 1e-9 else 0.0

    return {
        "total_return":   round(total_ret, 4),
        "market_return":  round(mkt_ret, 4),
        "sharpe":         round(sharpe, 4),
        "max_drawdown":   round(max_dd, 4),
        "win_rate":       round(win_rate, 4),
        "n_trades":       n_trades,
        "calmar":         round(calmar, 4),
        "excess_return":  round(total_ret - mkt_ret, 4),
    }


# ══════════════════════════════════════════════════════════════════════════
# MULTI-STRATEGY RUNNER
# ══════════════════════════════════════════════════════════════════════════

class MultiStrategyRunner:
    """
    Runs all registered strategies on train/test data,
    ranks by Sharpe on train, validates on test.

    Usage:
        runner = MultiStrategyRunner(train_df, test_df)
        results = runner.run_all()
        best = runner.get_best()
        summary = runner.summary_table()
    """

    def __init__(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        transaction_cost: float = 0.001,
        slippage: float = 0.001,
        strategies_to_run: Optional[List[str]] = None,
        custom_params: Optional[Dict[str, Dict]] = None,
    ):
        self.train_df = train_df
        self.test_df  = test_df
        self.tc       = transaction_cost
        self.sl       = slippage
        self.strategies = strategies_to_run or list(STRATEGY_REGISTRY.keys())
        self.custom_params = custom_params or {}
        self.results: Dict[str, Dict] = {}

    def _get_params(self, name: str) -> Dict[str, Any]:
        base   = STRATEGY_DEFAULT_PARAMS.get(name, {}).copy()
        custom = self.custom_params.get(name, {})
        base.update(custom)
        return base

    def run_all(self) -> Dict[str, Dict]:
        """Run every strategy on train + test. Store results."""
        for name in self.strategies:
            if name not in STRATEGY_REGISTRY:
                continue
            fn     = STRATEGY_REGISTRY[name]
            params = self._get_params(name)
            try:
                train_signal = fn(self.train_df, params)
                test_signal  = fn(self.test_df,  params)

                train_metrics = _run_strategy_backtest(self.train_df, train_signal, self.tc, self.sl)
                test_metrics  = _run_strategy_backtest(self.test_df,  test_signal,  self.tc, self.sl)

                self.results[name] = {
                    "strategy":       name,
                    "description":    STRATEGY_DESCRIPTIONS.get(name, ""),
                    "params":         params,
                    "train_metrics":  train_metrics,
                    "test_metrics":   test_metrics,
                    "train_signal":   train_signal,
                    "test_signal":    test_signal,
                    "error":          None,
                }
            except Exception as e:
                self.results[name] = {
                    "strategy": name,
                    "error":    str(e),
                }

        return self.results

    def get_best(self, rank_by: str = "sharpe", split: str = "train") -> Dict:
        """
        Return the best strategy result.

        rank_by: 'sharpe', 'total_return', 'calmar', 'win_rate'
        split:   'train' or 'test'
        """
        valid = {k: v for k, v in self.results.items() if v.get("error") is None}
        if not valid:
            return {}

        metric_key = f"{split}_metrics"
        best_name  = max(
            valid,
            key=lambda k: valid[k][metric_key].get(rank_by, float("-inf"))
        )
        return valid[best_name]

    def summary_table(self) -> pd.DataFrame:
        """Return a DataFrame comparing all strategies on train and test."""
        rows = []
        for name, res in self.results.items():
            if res.get("error"):
                rows.append({"strategy": name, "error": res["error"]})
                continue
            row = {
                "strategy":         name,
                "description":      res["description"][:40],
                "train_sharpe":     res["train_metrics"]["sharpe"],
                "train_return":     res["train_metrics"]["total_return"],
                "train_maxdd":      res["train_metrics"]["max_drawdown"],
                "test_sharpe":      res["test_metrics"]["sharpe"],
                "test_return":      res["test_metrics"]["total_return"],
                "test_maxdd":       res["test_metrics"]["max_drawdown"],
                "test_win_rate":    res["test_metrics"]["win_rate"],
                "test_n_trades":    res["test_metrics"]["n_trades"],
                "test_calmar":      res["test_metrics"]["calmar"],
                "overfitting_flag": (
                    res["train_metrics"]["sharpe"] - res["test_metrics"]["sharpe"] > 1.5
                ),
            }
            rows.append(row)
        return pd.DataFrame(rows)

    def get_strategy_ranking(self) -> List[Tuple[str, float]]:
        """Return strategies ranked by test Sharpe."""
        valid = {k: v for k, v in self.results.items() if v.get("error") is None}
        ranked = sorted(
            valid.items(),
            key=lambda kv: kv[1]["test_metrics"]["sharpe"],
            reverse=True
        )
        return [(name, res["test_metrics"]["sharpe"]) for name, res in ranked]


# ══════════════════════════════════════════════════════════════════════════
# STRATEGY ENSEMBLE (optional advanced mode)
# ══════════════════════════════════════════════════════════════════════════

def ensemble_signal(
    df: pd.DataFrame,
    strategy_names: List[str],
    params_map: Optional[Dict[str, Dict]] = None,
    vote_threshold: float = 0.5,
) -> pd.Series:
    """
    Combine multiple strategies by majority vote.
    Enter when >= vote_threshold fraction of strategies signal long.

    Example:
        signal = ensemble_signal(df, ["double_ma", "macd_crossover", "trend_momentum"])
    """
    params_map = params_map or {}
    signals = []

    for name in strategy_names:
        if name not in STRATEGY_REGISTRY:
            continue
        fn     = STRATEGY_REGISTRY[name]
        params = {**STRATEGY_DEFAULT_PARAMS.get(name, {}), **params_map.get(name, {})}
        try:
            s = fn(df, params)
            signals.append(s)
        except Exception:
            pass

    if not signals:
        return pd.Series(0, index=df.index)

    combined = pd.concat(signals, axis=1).mean(axis=1)
    return (combined >= vote_threshold).astype(int)


# ══════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION — drop-in for existing app
# ══════════════════════════════════════════════════════════════════════════

def run_multi_strategy_analysis(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    ticker: str,
    transaction_cost: float = 0.001,
    slippage: float = 0.001,
) -> Dict:
    """
    One-call wrapper used by app_ui.py / StrategyLoop.
    Returns a summary dict compatible with Orallexa's result format.
    """
    runner = MultiStrategyRunner(
        train_df=train_df,
        test_df=test_df,
        transaction_cost=transaction_cost,
        slippage=slippage,
    )
    runner.run_all()
    best    = runner.get_best(rank_by="sharpe", split="train")
    ranking = runner.get_strategy_ranking()
    table   = runner.summary_table()

    if not best:
        return {
            "ticker":          ticker,
            "best_strategy":   None,
            "best_params":     {},
            "train_metrics":   {},
            "test_metrics":    {},
            "ranking":         [],
            "summary_table":   pd.DataFrame(),
            "all_results":     {},
        }

    return {
        "ticker":          ticker,
        "best_strategy":   best["strategy"],
        "best_description":best["description"],
        "best_params":     best["params"],
        "train_metrics":   best["train_metrics"],
        "test_metrics":    best["test_metrics"],
        "ranking":         ranking,
        "summary_table":   table,
        "all_results":     runner.results,
    }
