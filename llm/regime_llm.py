"""
llm/regime_llm.py
──────────────────────────────────────────────────────────────────
Claude-backed `llm_fn` for engine.regime_strategist.propose_regime_strategy.

Produces strictly JSON-shaped proposals — the caller validates everything
(strategy in the registry, numeric params in bounds) before accepting.
On any failure (no API key, parse error, network), the regime strategist
falls back to its deterministic heuristic, so this wrapper is safe to
plug into production paths.

Usage:
    from engine.regime_strategist import propose_regime_strategy
    from llm.regime_llm import llm_regime_fn
    p = propose_regime_strategy("NVDA", regime="trending", df=ta_df,
                                 use_llm=True, llm_fn=llm_regime_fn)
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from llm.claude_client import FAST_MODEL, get_client

logger = logging.getLogger(__name__)


_PROMPT_TEMPLATE = """You tune trading strategy parameters for a specific regime.

Ticker: {ticker}
Detected regime: {regime}

Heuristic baseline (DO NOT change the strategy name unless clearly wrong):
  strategy: {strategy}
  params: {params}

Recent feature snapshot (last 20 bars, if available):
{features}

Your job: propose minor numeric tweaks to the params ONLY if the feature
snapshot suggests a clear reason (e.g., very strong trend → widen TP;
volatility spike → widen SL). If the baseline already fits, return it
unchanged.

Respond with ONLY a JSON object, no prose:
{{
  "strategy": "<one of the project's strategy names>",
  "params": {{"<param_name>": <number>, ...}},
  "reasoning": "<one sentence explaining the tweak (max 200 chars)>"
}}

Numeric bounds (values outside these are silently dropped):
  rsi_min: 0-50, rsi_max: 50-100, adx_min: 10-50
  stop_loss: 0.005-0.15, take_profit: 0.01-0.30, k_up/k_down: 0.1-2.0
"""


def _features_summary(df) -> str:
    """Condense the last 20 bars of a TA-enriched df into a few readable lines."""
    if df is None or len(df) < 20:
        return "(not enough history)"
    try:
        tail = df.tail(20)
        parts = []
        if "Close" in tail.columns:
            first, last = float(tail["Close"].iloc[0]), float(tail["Close"].iloc[-1])
            parts.append(f"close: {first:.2f} → {last:.2f} ({(last/first-1)*100:+.1f}%)")
        if "ADX" in tail.columns:
            parts.append(f"ADX mean: {float(tail['ADX'].mean()):.1f}")
        if "ATR" in tail.columns and "Close" in tail.columns:
            atr_pct = float((tail["ATR"] / tail["Close"]).mean())
            parts.append(f"ATR/Close: {atr_pct*100:.2f}%")
        if "RSI" in tail.columns:
            parts.append(f"RSI last: {float(tail['RSI'].iloc[-1]):.1f}")
        return " | ".join(parts) if parts else "(no recognized indicators)"
    except Exception:
        return "(feature extraction failed)"


def _parse_json(text: str) -> Optional[dict]:
    """Extract the first JSON object from Claude's response. Tolerates fences."""
    # Strip common markdown fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Last resort: find the outermost {...} block
        m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def llm_regime_fn(*, ticker: str, regime: str, base: dict, df=None) -> dict:
    """
    Drop-in llm_fn for engine.regime_strategist.propose_regime_strategy.

    Returns {strategy, params, reasoning} on success, or a fallback dict
    that will fail validation (triggering the heuristic path). Never raises.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"strategy": None, "params": {}, "reasoning": "no API key"}

    prompt = _PROMPT_TEMPLATE.format(
        ticker=ticker,
        regime=regime,
        strategy=base.get("strategy"),
        params=json.dumps(base.get("params", {})),
        features=_features_summary(df),
    )

    try:
        from llm.call_logger import logged_create
        client = get_client()
        response, _ = logged_create(
            client,
            request_type="regime_strategy",
            model=FAST_MODEL,
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
            ticker=ticker,
        )
        text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text += block.text

        parsed = _parse_json(text)
        if not parsed or not isinstance(parsed, dict):
            logger.debug("Regime LLM returned un-parseable output for %s: %r", ticker, text[:200])
            return {"strategy": None, "params": {}, "reasoning": "parse failed"}
        return parsed
    except Exception as e:
        logger.debug("Regime LLM call failed for %s: %s", ticker, e)
        return {"strategy": None, "params": {}, "reasoning": "call failed"}
