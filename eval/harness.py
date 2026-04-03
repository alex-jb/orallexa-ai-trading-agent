"""
eval/harness.py
--------------------------------------------------------------------
EvaluationHarness — orchestrates walk-forward validation, Monte Carlo
simulation, and statistical significance tests across strategies and
tickers. Produces structured results with pass/fail gates.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any

import numpy as np
import pandas as pd
import yfinance as yf

from engine.strategies import STRATEGY_REGISTRY, STRATEGY_DEFAULT_PARAMS
from eval.walk_forward import run_walk_forward, WalkForwardResult
from eval.monte_carlo import run_monte_carlo, MonteCarloResult
from eval.statistical_tests import run_statistical_tests, StatisticalTestResult

logger = logging.getLogger("eval.harness")


@dataclass
class StrategyEvaluation:
    """Complete evaluation of one strategy on one ticker."""
    strategy_name: str
    ticker: str
    walk_forward: WalkForwardResult | None = None
    monte_carlo: MonteCarloResult | None = None
    statistical: StatisticalTestResult | None = None
    overall_pass: bool = False
    verdict: str = "FAIL"
    gates_passed: int = 0


@dataclass
class HarnessResult:
    """Complete evaluation across all strategies and tickers."""
    tickers: List[str]
    strategies: List[str]
    evaluations: List[StrategyEvaluation] = field(default_factory=list)
    skipped_tickers: List[str] = field(default_factory=list)
    num_strategies_tested: int = 0

    # Summary
    total_passed: int = 0
    total_evaluated: int = 0


class EvaluationHarness:
    """
    Orchestrates all evaluation methods across strategies and tickers.

    Usage:
        harness = EvaluationHarness(tickers=["NVDA", "AAPL"])
        result = harness.run()
    """

    def __init__(
        self,
        tickers: List[str],
        initial_train_days: int = 252,
        test_days: int = 63,
        mc_iterations: int = 1000,
        mc_seed: int | None = None,
        data_years: int = 5,
    ):
        self.tickers = [t.upper() for t in tickers]
        self.initial_train_days = initial_train_days
        self.test_days = test_days
        self.mc_iterations = mc_iterations
        self.mc_seed = mc_seed
        self.data_years = data_years
        self.strategies = list(STRATEGY_REGISTRY.keys())
        self.num_strategies = len(self.strategies)

    def _fetch_data(self, ticker: str) -> pd.DataFrame | None:
        """Fetch historical OHLCV data from yfinance."""
        try:
            df = yf.download(
                ticker,
                period=f"{self.data_years}y",
                progress=False,
            )
            if df is None or len(df) < self.initial_train_days + self.test_days * 4:
                logger.warning("Insufficient data for %s (%d bars)", ticker, len(df) if df is not None else 0)
                return None
            # Flatten multi-level columns from yfinance
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
        except Exception as exc:
            logger.warning("Failed to fetch data for %s: %s", ticker, exc)
            return None

    def _evaluate_strategy(
        self,
        df: pd.DataFrame,
        strategy_name: str,
        ticker: str,
        progress_callback=None,
    ) -> StrategyEvaluation:
        """Run all evaluations for one strategy on one ticker."""
        strategy_fn = STRATEGY_REGISTRY[strategy_name]
        params = STRATEGY_DEFAULT_PARAMS.get(strategy_name, {})

        evaluation = StrategyEvaluation(
            strategy_name=strategy_name,
            ticker=ticker,
        )

        # 1. Walk-forward validation
        try:
            wf = run_walk_forward(
                df=df,
                strategy_fn=strategy_fn,
                strategy_name=strategy_name,
                params=params,
                initial_train_days=self.initial_train_days,
                test_days=self.test_days,
            )
            evaluation.walk_forward = wf
        except Exception as exc:
            logger.warning("Walk-forward failed for %s/%s: %s", strategy_name, ticker, exc)

        # 2. Run backtest on full data for Monte Carlo and stats
        try:
            from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2
            from engine.backtest import simple_backtest

            ta = TechnicalAnalysisSkillV2(df)
            ta.add_indicators()
            full_df = ta.copy()
            signals = strategy_fn(full_df, params)
            full_df["signal"] = signals.values
            bt_result = simple_backtest(full_df, params=params, signal_col="signal")

            # 2a. Monte Carlo
            mc = run_monte_carlo(
                backtest_df=bt_result,
                strategy_name=strategy_name,
                ticker=ticker,
                n_iterations=self.mc_iterations,
                seed=self.mc_seed,
            )
            evaluation.monte_carlo = mc

            # 2b. Statistical tests — extract trade returns
            signal_shifted = bt_result["signal"].shift(1).fillna(0)
            mask = signal_shifted != 0
            if "net_strategy_return" in bt_result.columns:
                trade_returns = bt_result.loc[mask, "net_strategy_return"].dropna().values
            elif "strategy_return" in bt_result.columns:
                trade_returns = bt_result.loc[mask, "strategy_return"].dropna().values
            else:
                trade_returns = np.array([])

            st = run_statistical_tests(
                trade_returns=trade_returns,
                strategy_name=strategy_name,
                ticker=ticker,
                num_strategies_tested=self.num_strategies,
                seed=self.mc_seed,
            )
            evaluation.statistical = st

        except Exception as exc:
            logger.warning("Backtest/MC/stats failed for %s/%s: %s", strategy_name, ticker, exc)

        # Gate counting for tiered verdict
        wf_pass = evaluation.walk_forward.passed if evaluation.walk_forward else False
        mc_pass = evaluation.monte_carlo.passed if evaluation.monte_carlo else False
        st_pass = (
            evaluation.statistical.returns_significant
            if evaluation.statistical and evaluation.statistical.sufficient_data
            else False
        )
        gates = sum([wf_pass, mc_pass, st_pass])
        evaluation.gates_passed = gates
        evaluation.overall_pass = gates == 3

        # Tiered verdict based on gates passed + OOS Sharpe
        oos_sharpe = evaluation.walk_forward.avg_oos_sharpe if evaluation.walk_forward else 0
        if gates == 3:
            evaluation.verdict = "STRONG PASS"
        elif gates == 2 and oos_sharpe > 0.5:
            evaluation.verdict = "PASS"
        elif gates >= 1 and oos_sharpe > 0:
            evaluation.verdict = "MARGINAL"
        else:
            evaluation.verdict = "FAIL"

        if progress_callback:
            progress_callback()

        return evaluation

    def run(self, progress_callback=None) -> HarnessResult:
        """
        Run all evaluations.

        Args:
            progress_callback: Optional callable invoked after each strategy/ticker pair.

        Returns:
            HarnessResult with all evaluations.
        """
        result = HarnessResult(
            tickers=self.tickers,
            strategies=self.strategies,
            num_strategies_tested=self.num_strategies,
        )

        for ticker in self.tickers:
            df = self._fetch_data(ticker)
            if df is None:
                result.skipped_tickers.append(ticker)
                continue

            for strategy_name in self.strategies:
                evaluation = self._evaluate_strategy(
                    df=df,
                    strategy_name=strategy_name,
                    ticker=ticker,
                    progress_callback=progress_callback,
                )
                result.evaluations.append(evaluation)
                result.total_evaluated += 1
                if evaluation.overall_pass:
                    result.total_passed += 1

        return result
