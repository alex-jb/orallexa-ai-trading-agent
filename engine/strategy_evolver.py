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
import textwrap
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from core.logger import get_logger

logger = get_logger("strategy_evolver")

RESULTS_DIR = Path("results") / "evolved_strategies"

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
        pd.Series of integers: 1 (long), 0 (flat)
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
- Return pd.Series of 0s and 1s aligned with df.index
- NO print statements, NO side effects, NO file I/O
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
- Return pd.Series of 0s and 1s
- Import ONLY numpy and pandas (available as np and pd)
- Check column existence before using
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

    response, _ = logged_create(
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

    return code, f"Generation {generation}"


# ═══════════════════════════════════════════════════════════════════════════
# SANDBOX EXECUTION
# ═══════════════════════════════════════════════════════════════════════════

def _execute_strategy(code: str, df: pd.DataFrame) -> Optional[pd.Series]:
    """
    Safely execute strategy code in a restricted namespace.
    Returns signal Series or None on failure.
    """
    sandbox = {
        "np": np,
        "pd": pd,
        "pd_Series": pd.Series,
        "pd_DataFrame": pd.DataFrame,
    }

    try:
        exec(code, sandbox)
    except Exception as e:
        logger.warning("Strategy compile error: %s", e)
        return None

    strategy_fn = sandbox.get("strategy")
    if strategy_fn is None or not callable(strategy_fn):
        logger.warning("Strategy code does not define a `strategy` function")
        return None

    try:
        signal = strategy_fn(df)
    except Exception as e:
        logger.warning("Strategy execution error: %s", e)
        return None

    if not isinstance(signal, pd.Series):
        return None

    # Validate: must be same length as df, values in {0, 1}
    if len(signal) != len(df):
        return None

    # Clamp to binary
    signal = signal.clip(0, 1).fillna(0).astype(int)
    return signal


# ═══════════════════════════════════════════════════════════════════════════
# BACKTESTING (reuse from ml_signal)
# ═══════════════════════════════════════════════════════════════════════════

def _backtest(df: pd.DataFrame, signal: pd.Series, tc: float = 0.001) -> dict:
    """Lightweight backtest. Returns metrics dict."""
    returns = df["Close"].pct_change().fillna(0)
    position = signal.shift(1).fillna(0)
    trades = position.diff().abs().fillna(0)

    net = position * returns - trades * tc
    cum = (1 + net).cumprod()
    mkt = (1 + returns).cumprod()

    sharpe = float(net.mean() / net.std() * np.sqrt(252)) if net.std() > 1e-9 else 0.0
    total = float(cum.iloc[-1] - 1)
    maxdd = float(((cum - cum.cummax()) / cum.cummax()).min())
    winrate = float((net[position > 0] > 0).mean()) if (position > 0).any() else 0.0
    n_trades = int(trades[trades > 0].count())

    return {
        "sharpe": round(sharpe, 4),
        "total_return": round(total, 4),
        "max_drawdown": round(maxdd, 4),
        "win_rate": round(winrate, 4),
        "n_trades": n_trades,
        "mkt_return": round(float(mkt.iloc[-1] - 1), 4),
    }


# ═══════════════════════════════════════════════════════════════════════════
# EVOLVER (public API)
# ═══════════════════════════════════════════════════════════════════════════

class StrategyEvolver:
    """
    LLM-driven strategy evolution engine.

    Parameters:
        ticker:      stock symbol
        generations: number of evolution cycles (default 3)
        population:  strategies per generation (default 4)
        top_k:       top strategies to feed forward (default 2)
    """

    def __init__(self, ticker: str = "NVDA"):
        self.ticker = ticker
        self.all_strategies: list[EvolvedStrategy] = []

    def run(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        generations: int = 3,
        population: int = 4,
        top_k: int = 2,
    ) -> dict:
        """
        Run the full evolution loop.
        Returns dict with all strategies, best strategy, and leaderboard.
        """
        logger.info("Starting strategy evolution for %s: %d generations x %d population",
                     self.ticker, generations, population)

        for gen in range(generations):
            logger.info("=== Generation %d ===", gen)

            # Select top performers to evolve from
            top = sorted(
                [s for s in self.all_strategies if not s.error],
                key=lambda s: s.sharpe, reverse=True,
            )[:top_k]

            existing_names = [s.name for s in self.all_strategies]

            for idx in range(population):
                name = f"evo_g{gen}_s{idx}"

                try:
                    code, reasoning = _generate_strategy_code(
                        generation=gen,
                        top_strategies=top,
                        existing_names=existing_names,
                        ticker=self.ticker,
                    )
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

                # Backtest on TEST data for fair evaluation
                test_signal = _execute_strategy(code, test_df)
                if test_signal is None:
                    self.all_strategies.append(EvolvedStrategy(
                        name=name, code=code, generation=gen,
                        error="Test execution failed", reasoning=reasoning,
                    ))
                    continue

                metrics = _backtest(test_df, test_signal)

                strat = EvolvedStrategy(
                    name=name,
                    code=code,
                    generation=gen,
                    parent=top[0].name if top else "",
                    sharpe=metrics["sharpe"],
                    total_return=metrics["total_return"],
                    max_drawdown=metrics["max_drawdown"],
                    win_rate=metrics["win_rate"],
                    n_trades=metrics["n_trades"],
                    reasoning=reasoning,
                )
                self.all_strategies.append(strat)
                logger.info("  %s: Sharpe=%.2f Return=%.1f%% Trades=%d",
                            name, strat.sharpe, strat.total_return * 100, strat.n_trades)

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
            "best": best.to_dict() if best else None,
            "leaderboard": [s.to_dict() for s in leaderboard[:10]],
        }

    def _save(self, leaderboard: list[EvolvedStrategy]) -> None:
        """Save evolution results to JSON."""
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_DIR / f"evolution_{self.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        data = {
            "ticker": self.ticker,
            "timestamp": datetime.now().isoformat(),
            "leaderboard": [s.to_dict() for s in leaderboard],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Saved evolution results to %s", path)
