"""
eval/harness.py
--------------------------------------------------------------------
EvaluationHarness — orchestrates walk-forward validation, Monte Carlo
simulation, and statistical significance tests across strategies and
tickers. Produces structured results with pass/fail gates.
"""
from __future__ import annotations

import logging
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any

import numpy as np
import pandas as pd
import yfinance as yf

from engine.strategies import STRATEGY_REGISTRY, STRATEGY_DEFAULT_PARAMS
from eval.walk_forward import run_walk_forward, WalkForwardResult
from eval.monte_carlo import run_monte_carlo, MonteCarloResult
from eval.statistical_tests import adjust_pvalues, run_statistical_tests, StatisticalTestResult

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
    # Enriched data for advanced report
    backtest_df: pd.DataFrame | None = None
    signals: pd.Series | None = None
    regime_performance: dict | None = None
    sortino: float = 0.0
    calmar: float = 0.0
    omega: float = 0.0


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

    # ML model evaluation
    ml_results: dict = field(default_factory=dict)  # ticker -> {model_name -> metrics}

    # Advanced report data
    benchmark_df: pd.DataFrame | None = None  # SPY OHLCV for comparison
    raw_data: Dict[str, pd.DataFrame] = field(default_factory=dict)  # ticker -> raw DataFrame
    data_sha256: Dict[str, str] = field(default_factory=dict)


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
        data_dir: str | Path | None = None,
        strategies: List[str] | None = None,
    ):
        self.tickers = [t.upper() for t in tickers]
        self.initial_train_days = initial_train_days
        self.test_days = test_days
        self.mc_iterations = mc_iterations
        self.mc_seed = mc_seed
        self.data_years = data_years
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.data_sha256: Dict[str, str] = {}
        self.expected_sha256: Dict[str, str] = {}
        if self.data_dir is not None and (self.data_dir / "manifest.json").is_file():
            manifest = json.loads((self.data_dir / "manifest.json").read_text(encoding="utf-8"))
            if not isinstance(manifest.get("sha256"), dict) or not manifest["sha256"]:
                raise ValueError("Snapshot manifest is missing per-ticker SHA-256 hashes")
            self.expected_sha256 = manifest["sha256"]
        self.strategies = list(strategies) if strategies is not None else list(STRATEGY_REGISTRY.keys())
        if not self.strategies or len(set(self.strategies)) != len(self.strategies):
            raise ValueError("Specify at least one unique strategy")
        unknown = set(self.strategies) - STRATEGY_REGISTRY.keys()
        if unknown:
            raise ValueError(f"Unknown strategies: {sorted(unknown)}")
        self.num_strategies = len(self.strategies)
        self.adaptive = True  # Enable walk-forward parameter optimization

    def _fetch_data(self, ticker: str) -> pd.DataFrame | None:
        """Load pinned CSV if provided; never silently fall back to live data."""
        try:
            if self.data_dir is not None:
                path = self.data_dir / f"{ticker}.csv"
                if not path.is_file():
                    logger.warning("Missing snapshot for %s: %s", ticker, path)
                    return None
                self.data_sha256[ticker] = hashlib.sha256(path.read_bytes()).hexdigest()
                if self.expected_sha256 and self.expected_sha256.get(ticker) != self.data_sha256[ticker]:
                    raise ValueError(f"Snapshot SHA-256 differs from manifest for {ticker}")
                df = pd.read_csv(path, index_col="Date", parse_dates=["Date"])
                required = {"Open", "High", "Low", "Close", "Volume"}
                if not required.issubset(df.columns) or df.index.has_duplicates or not df.index.is_monotonic_increasing:
                    raise ValueError("Snapshot must contain sorted unique dates and OHLCV columns")
                values = df[list(required)].to_numpy(dtype=float)
                if (not np.isfinite(values).all() or (df[["Open", "High", "Low", "Close"]] <= 0).any().any()
                        or (df["Volume"] < 0).any()):
                    raise ValueError("Snapshot must contain finite positive prices and nonnegative volume")
            else:
                df = yf.download(ticker, period=f"{self.data_years}y", progress=False)
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
                adaptive=self.adaptive,
            )
            evaluation.walk_forward = wf
        except Exception as exc:
            logger.warning("Walk-forward failed for %s/%s: %s", strategy_name, ticker, exc)

        # 2. Run backtest on full data for Monte Carlo and stats
        try:
            from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2
            from engine.backtest import simple_backtest
            from eval.regime import detect_regimes, segment_performance

            ta = TechnicalAnalysisSkillV2(df)
            ta.add_indicators()
            full_df = ta.copy()
            signals = strategy_fn(full_df, params)
            if (not isinstance(signals, pd.Series) or not signals.index.equals(full_df.index)
                    or signals.isna().any() or not signals.isin([0, 1]).all()):
                raise ValueError("Strategy must return aligned long/flat signals")
            full_df["signal"] = signals
            bt_result = simple_backtest(full_df, params=params, signal_col="signal",
                                        execution_mode="next_open")

            # Store enriched data for advanced charts
            evaluation.backtest_df = bt_result
            evaluation.signals = signals

            # Extract extended metrics
            from engine.evaluation import evaluate as eval_metrics
            full_metrics = eval_metrics(bt_result)
            evaluation.sortino = full_metrics.get("net", full_metrics).get("sortino", 0.0)
            evaluation.calmar = full_metrics.get("net", full_metrics).get("calmar", 0.0)
            evaluation.omega = full_metrics.get("net", full_metrics).get("omega", 0.0)

            # Regime analysis
            try:
                regimes = detect_regimes(df)
                evaluation.regime_performance = segment_performance(bt_result, regimes)
            except Exception:
                pass

            # 2a. Monte Carlo
            mc = run_monte_carlo(
                backtest_df=bt_result,
                strategy_name=strategy_name,
                ticker=ticker,
                n_iterations=self.mc_iterations,
                seed=self.mc_seed,
            )
            evaluation.monte_carlo = mc

            # Test OOS daily *net* returns, including flat days; full-data
            # backtest above is descriptive and cannot supply OOS p-values.
            oos_returns = np.asarray(evaluation.walk_forward.oos_returns) if evaluation.walk_forward else np.array([])
            st = run_statistical_tests(
                trade_returns=oos_returns,
                strategy_name=strategy_name,
                ticker=ticker,
                num_strategies_tested=self.num_strategies * len(self.tickers),
                seed=self.mc_seed,
            )
            evaluation.statistical = st

        except Exception as exc:
            logger.warning("Backtest/MC/stats failed for %s/%s: %s", strategy_name, ticker, exc)

        if (evaluation.walk_forward is None or evaluation.walk_forward.num_windows < 4
                or evaluation.statistical is None or not evaluation.statistical.sufficient_data):
            evaluation.verdict = "NOT EVALUATED"

        # Final significance gate is assigned across the whole family in run().
        return evaluation

    @staticmethod
    def _assign_verdict(evaluation: StrategyEvaluation) -> None:
        if evaluation.verdict == "NOT EVALUATED":
            return
        wf_pass = evaluation.walk_forward.passed if evaluation.walk_forward else False
        bonf_pass = (
            evaluation.statistical.bonferroni_significant
            if evaluation.statistical and evaluation.statistical.sufficient_data
            else False
        )
        bh_pass = evaluation.statistical.bh_significant if evaluation.statistical else False
        gates = sum([wf_pass, bonf_pass])
        evaluation.gates_passed = gates
        evaluation.overall_pass = gates == 2

        # Monte Carlo shuffle is descriptive and does not supply an
        # independent hypothesis test or an additional pass gate.
        if evaluation.overall_pass:
            evaluation.verdict = "PASS"
        elif wf_pass and bh_pass:
            evaluation.verdict = "MARGINAL"
        else:
            evaluation.verdict = "FAIL"

    @staticmethod
    def _correct_family(result: HarnessResult) -> None:
        """Apply corrections across the predeclared ticker × strategy family."""
        expected = len(result.tickers) * len(result.strategies)
        if len(result.evaluations) != expected:
            raise ValueError(f"Expected {expected} pair records, found {len(result.evaluations)}")
        raw = [e.statistical.p_value if (e.verdict != "NOT EVALUATED"
               and e.statistical and e.statistical.sufficient_data) else 1.0
               for e in result.evaluations]
        bonferroni, bh = adjust_pvalues(raw)
        result.total_passed = 0
        for ev, p_bonf, p_bh in zip(result.evaluations, bonferroni, bh):
            if ev.statistical and ev.verdict != "NOT EVALUATED":
                ev.statistical.p_bonferroni = p_bonf
                ev.statistical.p_bh = p_bh
                ev.statistical.bonferroni_significant = p_bonf < 0.05
                ev.statistical.bh_significant = p_bh < 0.05
            EvaluationHarness._assign_verdict(ev)
            result.total_passed += int(ev.overall_pass)

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
        if self.data_dir is not None and not self.data_dir.is_dir():
            raise ValueError(f"Snapshot directory does not exist: {self.data_dir}")

        # Fetch SPY benchmark for comparison charts
        try:
            if self.data_dir is None:
                spy_df = yf.download("SPY", period=f"{self.data_years}y", progress=False)
            elif (self.data_dir / "SPY.csv").is_file():
                spy_df = self._fetch_data("SPY")
            else:
                spy_df = None
            if spy_df is not None and len(spy_df) > 0:
                if isinstance(spy_df.columns, pd.MultiIndex):
                    spy_df.columns = spy_df.columns.get_level_values(0)
                result.benchmark_df = spy_df
        except Exception as exc:
            logger.warning("Failed to fetch SPY benchmark: %s", exc)

        for ticker in self.tickers:
            df = self._fetch_data(ticker)
            if df is None:
                result.skipped_tickers.append(ticker)
                for strategy_name in self.strategies:
                    result.evaluations.append(StrategyEvaluation(strategy_name, ticker, verdict="NOT EVALUATED"))
                    if progress_callback:
                        progress_callback()
                continue
            result.raw_data[ticker] = df

            for strategy_name in self.strategies:
                evaluation = self._evaluate_strategy(
                    df=df,
                    strategy_name=strategy_name,
                    ticker=ticker,
                    progress_callback=progress_callback,
                )
                result.evaluations.append(evaluation)
                if evaluation.verdict != "NOT EVALUATED":
                    result.total_evaluated += 1
                if progress_callback:
                    progress_callback()

            # The pinned 90-pair family excludes separate ML trials. Do not
            # publish those uncorrected performance metrics in its report.
            if self.data_dir is None:
                ml = self._evaluate_ml_models(df, ticker)
                if ml:
                    result.ml_results[ticker] = ml

        result.data_sha256 = self.data_sha256.copy()
        self._correct_family(result)
        return result

    def _evaluate_ml_models(self, df: pd.DataFrame, ticker: str) -> dict | None:
        """Run classical ML models with train/test split and return metrics."""
        try:
            from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2
            from engine.ml_signal import MLSignalGenerator

            ta = TechnicalAnalysisSkillV2(df)
            ta.add_indicators()
            enriched = ta.copy()

            # 80/20 split
            split = int(len(enriched) * 0.8)
            train_df = enriched.iloc[:split]
            test_df = enriched.iloc[split:]

            if len(test_df) < 50:
                return None

            gen = MLSignalGenerator(train_df, test_df, ticker=ticker)
            results = gen.run_all()

            # Extract metrics only (drop signal series for serialization)
            ml_metrics = {}
            for model_name, data in results.items():
                if isinstance(data, dict) and "metrics" in data:
                    ml_metrics[model_name] = data["metrics"]

            if ml_metrics:
                logger.info("ML models for %s: %s", ticker,
                    ", ".join(f"{m}={d['sharpe']:.2f}" for m, d in ml_metrics.items()))

            return ml_metrics
        except Exception as exc:
            logger.warning("ML evaluation failed for %s: %s", ticker, exc)
            return None
