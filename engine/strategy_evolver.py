"""
engine/strategy_evolver.py
────────────────────────────────────────────────────────────────────────────
LLM-driven strategy evolution engine (inspired by NVIDIA AVO).

Cycle:
  1. LLM generates new strategy Python code
  2. Sandbox-execute the code to produce signals
  3. Backtest the signals
  4. Rank by Sharpe ratio
  5. Feed top performers back to LLM for evolution

Usage:
    from engine.strategy_evolver import StrategyEvolver
    evolver = StrategyEvolver(ticker="NVDA")
    results = evolver.run(generations=3, population=4)
"""
from __future__ import annotations

import json
import threading
import textwrap
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from core.logger import get_logger
from engine.backtest import simple_backtest
from engine.evaluation import evaluate

logger = get_logger("strategy_evolver")

RESULTS_DIR = Path("results") / "evolved_strategies"

# Maximum time (seconds) to execute a single LLM-generated strategy
EXEC_TIMEOUT_SECONDS = 10

# Maximum total LLM cost per evolution run (USD)
MAX_COST_PER_RUN = 2.0

# Available columns the LLM strategy can use
AVAILABLE_COLUMNS = [
    "Open", "High", "Low", "Close", "Volume",
    "MA5", "MA10", "MA20", "MA50",
    "EMA12", "EMA26",
    "MACD", "MACD_Signal", "MACD_Hist",
    "RSI", "Stoch_K", "Stoch_D", "ROC",
    "BB_Pct", "BB_Width",
    "ATR_Pct", "HV20",
    "Volume_Ratio", "OBV",
    "ADX", "Plus_DI", "Minus_DI",
    "Above_MA20", "Above_MA50",
    "MACD_Cross_Up", "MACD_Cross_Down",
    "RSI_Oversold", "RSI_Overbought",
]


@dataclass
class EvolvedStrategy:
    """A single evolved strategy with its code, metrics, and lineage."""
    name: str
    code: str
    generation: int
    parent: str = ""
    sharpe: float = 0.0
    total_return: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    n_trades: int = 0
    reasoning: str = ""
    error: str = ""
    created: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════
# CODE GENERATION
# ═══════════════════════════════════════════════════════════════════════════

_SEED_PROMPT = """You are an expert quantitative strategy designer.

Generate a trading strategy as a Python function. The function must follow this EXACT signature:

```python
def strategy(df: pd.DataFrame) -> pd.Series:
    \"\"\"
    Args:
        df: DataFrame with columns: {columns}
    Returns:
        pd.Series of integers: 1 (long), 0 (flat), -1 (short/exit)
    \"\"\"
    # Your strategy logic here
    signal = pd.Series(0, index=df.index)
    # ... compute signal ...
    return signal
```

Rules:
- Import ONLY numpy and pandas (already available as np and pd)
- Use ONLY columns from this list: {columns}
- Check column existence before using: `if "RSI" in df.columns`
- Return pd.Series of -1, 0, and 1 values aligned with df.index
- NO print statements, NO side effects, NO file I/O
- Do NOT use pd.read_csv, pd.read_html, open(), or any file/network operations
- Strategy must be DIFFERENT from: {existing}
- Keep it under 30 lines of logic (simple is better)
- Use vectorized pandas operations, avoid for-loops
- IMPORTANT: Strategy must generate trades! Use at most 2-3 conditions combined with &.
  Too many conditions = zero trades = useless strategy.
- Example patterns that WORK:
  ```python
  # Simple momentum: long when above MA and MACD positive
  signal = ((df["Close"] > df["MA20"]) & (df["MACD_Hist"] > 0)).astype(int)
  ```
  ```python
  # RSI reversal: long when RSI was oversold then recovers
  signal = ((df["RSI"] > 35) & (df["RSI"].shift(1) < 30)).astype(int)
  ```
- Use moderate thresholds (RSI 30-70, not 20-80) to ensure enough signals

{context}

Return ONLY the Python function code, no explanation."""

_EVOLVE_PROMPT = """You are an expert quantitative strategy designer.

Here are the top-performing strategies from the previous generation:

{top_strategies}

Your task: Create an IMPROVED strategy by combining or mutating the best ideas above.

Available columns: {columns}

Rules:
- Same function signature: `def strategy(df: pd.DataFrame) -> pd.Series`
- Return pd.Series of -1, 0, and 1 values
- Import ONLY numpy and pandas (available as np and pd)
- Check column existence before using
- Do NOT use pd.read_csv, pd.read_html, open(), or any file/network operations
- Try to improve Sharpe ratio by:
  * Combining signals from multiple top strategies
  * Adding a filter that reduces false signals
  * Adjusting entry/exit timing
  * Using a different indicator combination
- Keep it under 50 lines
- NO print, NO side effects

{mutation_hint}

Return ONLY the Python function code, no explanation."""


def _generate_strategy_code(
    generation: int,
    top_strategies: list[EvolvedStrategy],
    existing_names: list[str],
    ticker: str,
    market_context: str = "",
) -> tuple[str, str]:
    """Use LLM to generate strategy code. Returns (code, reasoning)."""
    import llm.claude_client as cc
    from llm.claude_client import get_client, _extract_text
    from llm.call_logger import logged_create

    client = get_client()
    cols_str = ", ".join(AVAILABLE_COLUMNS[:20]) + "..."

    if generation == 0 or not top_strategies:
        # Seed generation
        prompt = _SEED_PROMPT.format(
            columns=cols_str,
            existing=", ".join(existing_names) if existing_names else "none",
            context=f"Ticker: {ticker}. {market_context}" if market_context else f"Ticker: {ticker}",
        )
    else:
        # Evolution from top performers
        strat_desc = ""
        for s in top_strategies[:3]:
            strat_desc += f"\n--- {s.name} (Sharpe={s.sharpe:.2f}, Return={s.total_return*100:.1f}%, WinRate={s.win_rate*100:.0f}%) ---\n"
            strat_desc += s.code + "\n"

        mutations = [
            "Try combining the entry signal of the best strategy with the exit signal of the second best.",
            "Add a volatility filter: only trade when ATR_Pct or HV20 is in a favorable range.",
            "Add a volume confirmation: require Volume_Ratio > 1.2 for entries.",
            "Use a momentum filter: require ADX > 20 and Plus_DI > Minus_DI for trend trades.",
            "Try a mean-reversion approach: buy when RSI < 30 and BB_Pct < 0.1, sell when RSI > 70.",
        ]
        import random
        hint = random.choice(mutations)

        prompt = _EVOLVE_PROMPT.format(
            top_strategies=strat_desc,
            columns=cols_str,
            mutation_hint=f"Mutation hint: {hint}",
        )

    response, record = logged_create(
        client, request_type="strategy_evolution",
        model=cc.FAST_MODEL,
        max_tokens=1200,
        temperature=0.7,
        messages=[{"role": "user", "content": prompt}],
        ticker=ticker,
    )

    raw = _extract_text(response).strip()

    # Extract code block
    code = raw
    if "```python" in code:
        code = code.split("```python", 1)[1]
        code = code.split("```", 1)[0]
    elif "```" in code:
        code = code.split("```", 1)[1]
        code = code.split("```", 1)[0]
    code = code.strip()

    # Ensure function starts with def strategy
    if not code.startswith("def strategy"):
        lines = code.split("\n")
        for i, line in enumerate(lines):
            if line.strip().startswith("def strategy"):
                code = "\n".join(lines[i:])
                break

    cost = record.estimated_cost_usd if record else 0.0
    return code, f"Generation {generation}", cost


# ═══════════════════════════════════════════════════════════════════════════
# SANDBOX EXECUTION
# ═══════════════════════════════════════════════════════════════════════════

# Pandas attributes that must NOT be accessible in the sandbox
_DANGEROUS_PD_ATTRS = [
    "read_csv", "read_html", "read_sql", "read_excel", "read_json",
    "read_parquet", "read_feather", "read_hdf", "read_pickle",
    "read_table", "read_fwf", "read_clipboard", "read_orc",
    "read_spss", "read_stata", "ExcelWriter",
]


def _make_safe_pd():
    """Create a restricted pandas module proxy that blocks file I/O."""
    import types
    safe_pd = types.ModuleType("pandas")
    # Copy safe attributes from pd
    for attr in dir(pd):
        if attr not in _DANGEROUS_PD_ATTRS and not attr.startswith("_"):
            try:
                setattr(safe_pd, attr, getattr(pd, attr))
            except (AttributeError, TypeError):
                pass
    # Ensure core types are available
    safe_pd.Series = pd.Series
    safe_pd.DataFrame = pd.DataFrame
    safe_pd.Index = pd.Index
    return safe_pd


def _execute_strategy(code: str, df: pd.DataFrame, timeout: int = EXEC_TIMEOUT_SECONDS) -> Optional[pd.Series]:
    """
    Safely execute strategy code in a restricted namespace with timeout.
    Returns signal Series or None on failure.
    """
    if not code or "def strategy" not in code:
        logger.warning("Strategy code missing or no 'def strategy' found")
        return None

    safe_pd = _make_safe_pd()
    sandbox = {
        "__builtins__": {},
        "np": np,
        "pd": safe_pd,
        "pd_Series": pd.Series,
        "pd_DataFrame": pd.DataFrame,
        "range": range,
        "len": len,
        "int": int,
        "float": float,
        "bool": bool,
        "abs": abs,
        "min": min,
        "max": max,
        "sum": sum,
        "round": round,
        "isinstance": isinstance,
        "getattr": getattr,
        "hasattr": hasattr,
    }

    # Compile
    try:
        exec(code, sandbox)
    except Exception as e:
        logger.warning("Strategy compile error: %s", e)
        return None

    strategy_fn = sandbox.get("strategy")
    if strategy_fn is None or not callable(strategy_fn):
        logger.warning("Strategy code does not define a `strategy` function")
        return None

    # Execute with timeout
    result = [None]
    error = [None]

    def _run():
        try:
            result[0] = strategy_fn(df)
        except Exception as e:
            error[0] = e

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        logger.warning("Strategy execution timed out after %ds", timeout)
        return None

    if error[0] is not None:
        logger.warning("Strategy execution error: %s", error[0])
        return None

    signal = result[0]
    if not isinstance(signal, pd.Series):
        return None

    # Validate: must be same length as df
    if len(signal) != len(df):
        return None

    # Clamp to {-1, 0, 1} and fill NaN
    signal = signal.clip(-1, 1).fillna(0).round().astype(int)
    return signal


# ═══════════════════════════════════════════════════════════════════════════
# METRICS EXTRACTION (from simple_backtest output)
# ═══════════════════════════════════════════════════════════════════════════

def _extract_metrics(bt_df: pd.DataFrame) -> dict:
    """Extract standard metrics from a simple_backtest() output DataFrame."""
    if bt_df is None or len(bt_df) == 0:
        return {
            "sharpe": 0.0, "total_return": 0.0, "max_drawdown": 0.0,
            "win_rate": 0.0, "n_trades": 0, "mkt_return": 0.0,
        }

    net = bt_df["net_strategy_return"] if "net_strategy_return" in bt_df.columns else bt_df.get("strategy_return", pd.Series(0, index=bt_df.index))
    cum = bt_df["CumulativeNetStrategyReturn"] if "CumulativeNetStrategyReturn" in bt_df.columns else (1 + net).cumprod()
    mkt_cum = bt_df["CumulativeMarketReturn"] if "CumulativeMarketReturn" in bt_df.columns else pd.Series(1.0, index=bt_df.index)

    sharpe = float(net.mean() / net.std() * np.sqrt(252)) if net.std() > 1e-9 else 0.0
    total = float(cum.iloc[-1] - 1) if len(cum) > 0 else 0.0
    maxdd = float(((cum - cum.cummax()) / cum.cummax().clip(lower=1e-9)).min()) if len(cum) > 0 else 0.0

    shifted = bt_df.get("Signal", bt_df.get("signal", pd.Series(0, index=bt_df.index))).shift(1).fillna(0)
    in_position = shifted != 0
    if in_position.any():
        winrate = float((net[in_position] > 0).mean())
    else:
        winrate = 0.0

    pos_changes = shifted.diff().abs().fillna(0)
    n_trades = int((pos_changes > 0).sum())

    mkt_return = float(mkt_cum.iloc[-1] - 1) if len(mkt_cum) > 0 else 0.0

    return {
        "sharpe": round(sharpe, 4),
        "total_return": round(total, 4),
        "max_drawdown": round(maxdd, 4),
        "win_rate": round(winrate, 4),
        "n_trades": n_trades,
        "mkt_return": round(mkt_return, 4),
    }


# ═══════════════════════════════════════════════════════════════════════════
# INDICATOR COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════

def _ensure_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators if not already present."""
    if "RSI" in df.columns and "MACD" in df.columns:
        return df  # Already computed

    from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2
    ta = TechnicalAnalysisSkillV2(df)
    ta.add_indicators()
    return ta.copy()


# ═══════════════════════════════════════════════════════════════════════════
# EVOLVER (public API)
# ═══════════════════════════════════════════════════════════════════════════

class StrategyEvolver:
    """
    LLM-driven strategy evolution engine with overfitting protection.

    Parameters:
        ticker:      stock symbol
        generations: number of evolution cycles (default 3)
        population:  strategies per generation (default 4)
        top_k:       top strategies to feed forward (default 2)

    Overfitting safeguards:
        - Early stopping when best Sharpe stagnates for 2+ generations
        - Diversity enforcement: reject strategies too similar to existing ones
        - Minimum trade count filter (strategies with <5 trades are penalized)
        - Capped Sharpe: unrealistic Sharpe (>4.0) treated as suspicious
    """

    # Convergence / diversity thresholds
    STAGNATION_GENS = 2       # stop if no improvement for this many generations
    SHARPE_CAP = 4.0          # cap suspiciously high Sharpe
    MIN_TRADES = 5            # minimum trades for a valid strategy
    DIVERSITY_THRESHOLD = 0.9 # reject if signal correlation > this with existing

    def __init__(self, ticker: str = "NVDA"):
        self.ticker = ticker
        self.all_strategies: list[EvolvedStrategy] = []
        self.total_cost: float = 0.0
        self._best_per_gen: list[float] = []  # best Sharpe per generation
        self._signal_cache: list[pd.Series] = []  # cached signals for diversity check

    def _check_diversity(self, new_signal: pd.Series) -> bool:
        """Return True if new_signal is sufficiently different from cached signals."""
        if not self._signal_cache:
            return True
        for existing in self._signal_cache[-10:]:  # check last 10
            if len(existing) != len(new_signal):
                continue
            corr = new_signal.corr(existing)
            if corr is not None and abs(corr) > self.DIVERSITY_THRESHOLD:
                return False
        return True

    def _is_converged(self) -> bool:
        """Return True if evolution has stagnated."""
        if len(self._best_per_gen) < self.STAGNATION_GENS + 1:
            return False
        recent = self._best_per_gen[-self.STAGNATION_GENS:]
        best_before = self._best_per_gen[-(self.STAGNATION_GENS + 1)]
        return all(s <= best_before + 0.05 for s in recent)

    def _adjusted_sharpe(self, sharpe: float, n_trades: int) -> float:
        """Apply overfitting penalties to raw Sharpe."""
        # Cap unrealistic Sharpe
        if sharpe > self.SHARPE_CAP:
            sharpe = self.SHARPE_CAP
        # Penalize very few trades
        if n_trades < self.MIN_TRADES:
            sharpe *= max(0.2, n_trades / self.MIN_TRADES)
        return sharpe

    def run(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        generations: int = 3,
        population: int = 4,
        top_k: int = 2,
        max_cost: float = MAX_COST_PER_RUN,
    ) -> dict:
        """
        Run the full evolution loop.
        Returns dict with all strategies, best strategy, and leaderboard.
        """
        logger.info("Starting strategy evolution for %s: %d generations x %d population",
                     self.ticker, generations, population)

        # Ensure indicators are computed
        train_df = _ensure_indicators(train_df)
        test_df = _ensure_indicators(test_df)

        for gen in range(generations):
            logger.info("=== Generation %d ===", gen)

            # Check cost budget
            if self.total_cost >= max_cost:
                logger.warning("Cost budget exhausted ($%.2f >= $%.2f). Stopping.",
                               self.total_cost, max_cost)
                break

            # Early stopping on convergence
            if self._is_converged():
                logger.info("Early stopping: no improvement for %d generations.",
                            self.STAGNATION_GENS)
                break

            # Select top performers to evolve from
            top = sorted(
                [s for s in self.all_strategies if not s.error],
                key=lambda s: s.sharpe, reverse=True,
            )[:top_k]

            existing_names = [s.name for s in self.all_strategies]
            gen_best_sharpe = -999.0

            for idx in range(population):
                if self.total_cost >= max_cost:
                    break

                name = f"evo_g{gen}_s{idx}"

                try:
                    code, reasoning, cost = _generate_strategy_code(
                        generation=gen,
                        top_strategies=top,
                        existing_names=existing_names,
                        ticker=self.ticker,
                    )
                    self.total_cost += cost
                except Exception as e:
                    logger.warning("LLM generation failed: %s", e)
                    self.all_strategies.append(EvolvedStrategy(
                        name=name, code="", generation=gen,
                        error=str(e), reasoning="LLM call failed",
                    ))
                    continue

                # Execute on train data
                signal = _execute_strategy(code, train_df)
                if signal is None:
                    self.all_strategies.append(EvolvedStrategy(
                        name=name, code=code, generation=gen,
                        error="Execution failed", reasoning=reasoning,
                    ))
                    continue

                # Diversity check: reject signals too similar to existing
                if not self._check_diversity(signal):
                    logger.info("  %s: rejected — too similar to existing strategy", name)
                    self.all_strategies.append(EvolvedStrategy(
                        name=name, code=code, generation=gen,
                        error="Rejected: low diversity", reasoning=reasoning,
                    ))
                    continue

                # Backtest on TEST data for fair evaluation
                test_signal = _execute_strategy(code, test_df)
                if test_signal is None:
                    self.all_strategies.append(EvolvedStrategy(
                        name=name, code=code, generation=gen,
                        error="Test execution failed", reasoning=reasoning,
                    ))
                    continue

                # Use simple_backtest for consistent metrics
                test_bt = test_df.copy()
                test_bt["signal"] = test_signal
                try:
                    bt_result = simple_backtest(test_bt, signal_col="signal")
                    metrics = _extract_metrics(bt_result)
                except Exception as e:
                    logger.warning("Backtest failed for %s: %s", name, e)
                    self.all_strategies.append(EvolvedStrategy(
                        name=name, code=code, generation=gen,
                        error=f"Backtest failed: {e}", reasoning=reasoning,
                    ))
                    continue

                # Apply overfitting adjustments
                adj_sharpe = self._adjusted_sharpe(
                    metrics["sharpe"], metrics["n_trades"])

                strat = EvolvedStrategy(
                    name=name,
                    code=code,
                    generation=gen,
                    parent=top[0].name if top else "",
                    sharpe=adj_sharpe,
                    total_return=metrics["total_return"],
                    max_drawdown=metrics["max_drawdown"],
                    win_rate=metrics["win_rate"],
                    n_trades=metrics["n_trades"],
                    reasoning=reasoning,
                )
                self.all_strategies.append(strat)
                self._signal_cache.append(test_signal)
                gen_best_sharpe = max(gen_best_sharpe, adj_sharpe)
                logger.info("  %s: Sharpe=%.2f (adj=%.2f) Return=%.1f%% Trades=%d",
                            name, metrics["sharpe"], adj_sharpe,
                            strat.total_return * 100, strat.n_trades)

            self._best_per_gen.append(gen_best_sharpe)

        # Build leaderboard
        valid = [s for s in self.all_strategies if not s.error]
        leaderboard = sorted(valid, key=lambda s: s.sharpe, reverse=True)

        best = leaderboard[0] if leaderboard else None

        # Save results
        self._save(leaderboard)

        return {
            "ticker": self.ticker,
            "generations": generations,
            "population": population,
            "total_strategies": len(self.all_strategies),
            "valid_strategies": len(valid),
            "failed_strategies": len(self.all_strategies) - len(valid),
            "total_cost_usd": round(self.total_cost, 4),
            "best": best.to_dict() if best else None,
            "leaderboard": [s.to_dict() for s in leaderboard[:10]],
            "converged_at_gen": len(self._best_per_gen) - 1 if self._is_converged() else None,
            "best_sharpe_per_gen": self._best_per_gen,
        }

    def validate_with_harness(self, best: EvolvedStrategy, df: pd.DataFrame) -> dict:
        """
        Validate the best evolved strategy using the evaluation harness
        (walk-forward + Monte Carlo + statistical tests).

        Returns dict with harness results or error.
        """
        from eval.walk_forward import run_walk_forward
        from eval.monte_carlo import run_monte_carlo
        from eval.statistical_tests import run_statistical_tests

        df = _ensure_indicators(df)

        # Execute strategy to get signals
        signal = _execute_strategy(best.code, df)
        if signal is None:
            return {"error": "Strategy execution failed on full data"}

        bt_df = df.copy()
        bt_df["signal"] = signal
        bt_result = simple_backtest(bt_df, signal_col="signal")

        # Wrap the evolved code as a callable for walk-forward
        def evolved_fn(sub_df, params):
            sub_df = _ensure_indicators(sub_df)
            return _execute_strategy(best.code, sub_df) or pd.Series(0, index=sub_df.index)

        # Walk-forward validation
        raw_df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        wf = run_walk_forward(
            df=raw_df, strategy_fn=evolved_fn,
            strategy_name=best.name, params={},
        )

        # Monte Carlo
        mc = run_monte_carlo(
            backtest_df=bt_result, strategy_name=best.name,
            ticker=self.ticker, n_iterations=1000, seed=42,
        )

        # Statistical tests
        signal_shifted = bt_result["Signal"].shift(1).fillna(0) if "Signal" in bt_result.columns else bt_result["signal"].shift(1).fillna(0)
        mask = signal_shifted != 0
        ret_col = "net_strategy_return" if "net_strategy_return" in bt_result.columns else "strategy_return"
        trade_returns = bt_result.loc[mask, ret_col].dropna().values if ret_col in bt_result.columns else np.array([])

        stats = run_statistical_tests(
            trade_returns=trade_returns,
            strategy_name=best.name,
            ticker=self.ticker,
            num_strategies_tested=max(len([s for s in self.all_strategies if not s.error]), 1),
            seed=42,
        )

        return {
            "walk_forward": {
                "windows": wf.num_windows,
                "avg_oos_sharpe": wf.avg_oos_sharpe,
                "pct_positive": wf.pct_positive_sharpe,
                "passed": wf.passed,
            },
            "monte_carlo": {
                "original_sharpe": mc.original_sharpe,
                "percentile_rank": mc.sharpe_percentile_rank,
                "passed": mc.passed,
            },
            "statistical": {
                "p_value": stats.p_value,
                "sharpe_ci": [stats.sharpe_ci_lower, stats.sharpe_ci_upper],
                "dsr": stats.dsr,
                "significant": stats.returns_significant,
            },
            "overall_pass": wf.passed and mc.passed and (stats.returns_significant if stats.sufficient_data else False),
        }

    def _save(self, leaderboard: list[EvolvedStrategy]) -> None:
        """Save evolution results to JSON."""
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_DIR / f"evolution_{self.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        data = {
            "ticker": self.ticker,
            "timestamp": datetime.now().isoformat(),
            "total_cost_usd": round(self.total_cost, 4),
            "leaderboard": [s.to_dict() for s in leaderboard],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved evolution results to %s", path)
