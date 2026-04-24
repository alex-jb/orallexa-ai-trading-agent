"""
engine/regime_strategist.py
──────────────────────────────────────────────────────────────────
Regime-conditional strategy proposals (AgentQuant-inspired).

We already detect regime (trending / ranging / volatile) in
engine/strategies._detect_regime. This module picks the right
strategy + tunes its parameters for the detected regime — either via
a rule-based heuristic (fast, deterministic) or optionally via an LLM
(richer justification, requires API key).

Principle:
  trending  → trend-following strategies, earlier entries
  ranging   → mean-reversion, tighter RSI bands
  volatile  → stand aside or use widened breakout bands

Usage:
    from engine.regime_strategist import propose_regime_strategy
    p = propose_regime_strategy("NVDA", regime="trending", df=ta_df)
    # {strategy: "trend_momentum", params: {...}, reasoning: "...",
    #  source: "heuristic"}
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Strategy recipe table — base params per regime, tuned conservatively.
# Params match engine/strategies.py signatures; unknown keys are ignored
# by the strategy functions.
_RECIPES: dict[str, dict] = {
    "trending": {
        "strategy": "trend_momentum",
        "params": {"rsi_min": 40, "rsi_max": 75, "adx_min": 22, "stop_loss": 0.04, "take_profit": 0.10},
        "reasoning": (
            "Trending regime → trend-following strategy with relaxed RSI bounds "
            "(40-75) and higher ADX threshold to confirm trend strength. "
            "Wider take-profit allows runners; stop-loss kept at 4%."
        ),
    },
    "ranging": {
        "strategy": "rsi_reversal",
        "params": {"rsi_min": 30, "rsi_max": 70, "stop_loss": 0.03, "take_profit": 0.05},
        "reasoning": (
            "Ranging regime → mean-reversion. Tight RSI bands (30 oversold / 70 "
            "overbought) catch reversals quickly; 3% stop and 5% target match "
            "typical intraday range."
        ),
    },
    "volatile": {
        "strategy": "dual_thrust",
        "params": {"k_up": 0.7, "k_down": 0.7, "stop_loss": 0.06, "take_profit": 0.08},
        "reasoning": (
            "Volatile regime → breakout-only with wider k coefficients (0.7 each "
            "side) to avoid whipsaws. Wider 6% stop accommodates larger swings."
        ),
    },
}

# Minimum history required before we even attempt a proposal
_MIN_BARS = 50


def propose_regime_strategy(
    ticker: str,
    regime: str,
    df=None,
    *,
    use_llm: bool = False,
    llm_fn=None,
) -> dict:
    """
    Pick a strategy + params tailored to the given regime.

    Parameters
    ----------
    ticker    : symbol (passed through to LLM for context only)
    regime    : "trending" / "ranging" / "volatile" (anything else → neutral)
    df        : optional TA-enriched DataFrame; if provided, we pull a couple
                of features (ADX, ATR/Close) to refine the base recipe.
    use_llm   : if True, call llm_fn to produce a justification + tweaks.
                The LLM result is VALIDATED — if it proposes an unknown
                strategy or numeric-out-of-range param, we fall back to
                the heuristic recipe.
    llm_fn    : optional callable(ticker, regime, base_recipe, df) -> dict.
                Injected for testability.

    Returns
    -------
    {strategy, params, reasoning, source: "heuristic"|"llm"}
    """
    regime_key = str(regime).lower().strip()
    base = _RECIPES.get(regime_key)
    if base is None:
        return {
            "strategy": None,
            "params": {},
            "reasoning": f"Unknown regime '{regime}' — no proposal.",
            "source": "none",
        }

    # Deep copy so we don't mutate the module constant
    recipe = {
        "strategy": base["strategy"],
        "params": dict(base["params"]),
        "reasoning": base["reasoning"],
        "source": "heuristic",
    }

    # Feature-aware tweaks when df is available
    if df is not None and len(df) >= _MIN_BARS:
        recipe = _tune_with_features(recipe, regime_key, df)

    if use_llm and llm_fn is not None:
        try:
            llm_out = llm_fn(ticker=ticker, regime=regime_key, base=recipe, df=df)
            validated = _validate_llm_proposal(llm_out, base_recipe=recipe)
            if validated is not None:
                validated["source"] = "llm"
                return validated
        except Exception as e:
            logger.debug("LLM strategy proposal failed for %s: %s", ticker, e)

    return recipe


def _tune_with_features(recipe: dict, regime: str, df) -> dict:
    """Light, deterministic tuning based on recent ADX + volatility."""
    try:
        tail = df.tail(20)
        if "ADX" in tail.columns and regime == "trending":
            recent_adx = float(tail["ADX"].mean())
            # Very strong trend → widen take-profit
            if recent_adx > 35:
                recipe["params"]["take_profit"] = 0.12
        if "ATR" in tail.columns and "Close" in tail.columns:
            atr_pct = float((tail["ATR"] / tail["Close"]).mean())
            # Higher-than-usual volatility → widen stop-loss proportionally
            if atr_pct > 0.04:
                recipe["params"]["stop_loss"] = round(
                    max(recipe["params"]["stop_loss"], atr_pct * 1.2), 3
                )
    except Exception:
        pass
    return recipe


# ── LLM result validation ─────────────────────────────────────────────────

_KNOWN_STRATEGIES = frozenset({
    "double_ma", "macd_crossover", "bollinger_breakout", "rsi_reversal",
    "trend_momentum", "alpha_combo", "dual_thrust", "ensemble_vote",
    "regime_ensemble",
})

_NUMERIC_BOUNDS = {
    "rsi_min":      (0, 50),
    "rsi_max":      (50, 100),
    "adx_min":      (10, 50),
    "stop_loss":    (0.005, 0.15),
    "take_profit":  (0.01, 0.30),
    "k_up":         (0.1, 2.0),
    "k_down":       (0.1, 2.0),
}


def _validate_llm_proposal(proposal: dict, *, base_recipe: dict) -> Optional[dict]:
    """
    Accept an LLM-generated proposal only if it's well-formed, targets a
    known strategy, and params fall within sane numeric bounds.
    """
    if not isinstance(proposal, dict):
        return None
    strat = proposal.get("strategy")
    params = proposal.get("params", {})
    if strat not in _KNOWN_STRATEGIES or not isinstance(params, dict):
        return None

    cleaned: dict = {}
    for k, v in params.items():
        if k in _NUMERIC_BOUNDS:
            try:
                fv = float(v)
            except (ValueError, TypeError):
                continue
            lo, hi = _NUMERIC_BOUNDS[k]
            if not (lo <= fv <= hi):
                continue
            cleaned[k] = fv
        else:
            # Allow unknown-but-JSON-safe params through unchanged
            if isinstance(v, (int, float, str, bool)):
                cleaned[k] = v

    # Must have at least one recognized numeric param to be meaningful
    if not any(k in _NUMERIC_BOUNDS for k in cleaned):
        return None

    # Merge on top of heuristic base so required keys still exist
    merged_params = {**base_recipe["params"], **cleaned}
    return {
        "strategy": strat,
        "params": merged_params,
        "reasoning": str(proposal.get("reasoning", base_recipe["reasoning"]))[:400],
    }
