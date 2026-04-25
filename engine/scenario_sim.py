"""
engine/scenario_sim.py
──────────────────────────────────────────────────────────────────
What-If Scenario Simulation Engine.

Inspired by MiroFish's dynamic variable injection — users describe
hypothetical market scenarios, and Claude decomposes + simulates
the impact on their tickers.

Usage:
    from engine.scenario_sim import run_scenario
    result = run_scenario(
        scenario="Fed raises rates by 50bp unexpectedly",
        tickers=["NVDA", "AAPL", "TLT", "GLD"],
    )
    print(result["impacts"])          # per-ticker impact scores
    print(result["portfolio_delta"])  # overall portfolio effect
"""
from __future__ import annotations

import json
import logging
from datetime import date as _date
from typing import Optional

import llm.claude_client as cc
from llm.claude_client import get_client, _extract_text
from llm.call_logger import logged_create

logger = logging.getLogger(__name__)

# ── Common scenario templates ────────────────────────────────────────────────

SCENARIO_TEMPLATES = {
    "rate_hike": "Fed raises interest rates by {magnitude} unexpectedly",
    "rate_cut": "Fed cuts interest rates by {magnitude}",
    "earnings_miss": "{ticker} misses earnings estimates by {magnitude}",
    "earnings_beat": "{ticker} beats earnings estimates by {magnitude}",
    "geopolitical": "{event} escalates, raising global uncertainty",
    "sector_rotation": "Major rotation from {from_sector} into {to_sector}",
    "black_swan": "Unexpected {event} causes market-wide panic",
    "china_policy": "China announces {policy} affecting tech/trade",
    "inflation_shock": "CPI comes in at {magnitude}, well above expectations",
    "ai_regulation": "New AI regulation: {details}",
}


def _build_current_context(tickers: list[str]) -> str:
    """Fetch current price/indicator data for tickers."""
    lines = []
    try:
        import yfinance as yf
        for tk in tickers[:8]:  # cap at 8 to control cost
            try:
                info = yf.Ticker(tk)
                hist = info.history(period="5d")
                if hist.empty:
                    continue
                close = hist["Close"].iloc[-1]
                prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else close
                change_pct = (close - prev_close) / prev_close * 100
                lines.append(f"{tk}: ${close:.2f} ({change_pct:+.1f}%)")
            except Exception:
                lines.append(f"{tk}: price unavailable")
    except ImportError:
        for tk in tickers:
            lines.append(f"{tk}: price unavailable")
    return "\n".join(lines)


def run_scenario(
    scenario: str,
    tickers: list[str],
    portfolio_weights: Optional[dict[str, float]] = None,
) -> dict:
    """
    Simulate a what-if scenario's impact on given tickers.

    Parameters
    ----------
    scenario          : natural language scenario description
    tickers           : list of ticker symbols to analyze
    portfolio_weights : optional {ticker: weight} for portfolio delta calc

    Returns
    -------
    dict with keys:
        scenario          : the input scenario
        impacts           : list of per-ticker impact dicts
        portfolio_delta   : weighted portfolio impact score
        historical_analog : similar past event reference
        hedging           : suggested hedging actions
        summary           : 2-3 sentence overall assessment
        confidence        : 0-100 confidence in the simulation
    """
    client = get_client()
    current_data = _build_current_context(tickers)

    # Equal weights if not provided
    if not portfolio_weights:
        w = 1.0 / len(tickers)
        portfolio_weights = {tk: w for tk in tickers}

    prompt = f"""You are a senior macro strategist running a scenario simulation.

SCENARIO: {scenario}

CURRENT POSITIONS:
{current_data}

PORTFOLIO WEIGHTS:
{json.dumps(portfolio_weights, indent=2)}

Analyze the impact of this scenario on each ticker. Consider:
1. Direct effects (revenue, margins, demand)
2. Second-order effects (supply chain, competitors, substitutes)
3. Market regime shift (risk-on/off, sector rotation)
4. Historical parallels

Output ONLY valid JSON (no markdown):
{{
  "impacts": [
    {{
      "ticker": "NVDA",
      "impact_pct": -5.2,
      "direction": "bearish",
      "severity": "high",
      "reasoning": "2-3 sentences with specific cause-effect chain",
      "time_horizon": "1-2 weeks",
      "key_level": 850.0
    }}
  ],
  "portfolio_delta_pct": -2.1,
  "historical_analog": {{
    "event": "Dec 2018 surprise rate hike",
    "date": "2018-12",
    "market_reaction": "S&P fell 7% over 2 weeks, tech hardest hit",
    "relevance": "high"
  }},
  "hedging_suggestions": [
    "Reduce tech exposure by 20%",
    "Add GLD position as hedge"
  ],
  "summary": "2-3 sentence overall assessment of portfolio impact",
  "confidence": 65,
  "regime_shift": "risk-off"
}}

Rules:
- impact_pct: estimated price change (negative = loss, positive = gain)
- direction: "bullish", "bearish", or "neutral"
- severity: "low", "medium", "high"
- time_horizon: expected timeframe for impact
- key_level: critical support/resistance level to watch
- confidence: 0-100 overall confidence in this simulation
- Be specific, data-driven. Reference the current prices.
- Include ALL tickers from the positions list."""

    try:
        # What-if scenarios benefit from Opus 4.7's deeper reasoning over
        # historical analogs and second-order effects. xhigh effort.
        response, _ = logged_create(
            client, request_type="scenario_simulation",
            model=cc.OPUS_MODEL, max_tokens=1200, temperature=0.3,
            effort=cc.DEEP_EFFORT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = _extract_text(response).strip()
        text = text.replace("```json", "").replace("```", "").strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        data = json.loads(text)

        # Normalize and validate
        impacts = data.get("impacts", [])
        for imp in impacts:
            imp["direction"] = str(imp.get("direction", "neutral")).lower()
            if imp["direction"] not in ("bullish", "bearish", "neutral"):
                imp["direction"] = "neutral"
            imp["severity"] = str(imp.get("severity", "medium")).lower()
            if imp["severity"] not in ("low", "medium", "high"):
                imp["severity"] = "medium"

        return {
            "scenario": scenario,
            "date": _date.today().isoformat(),
            "impacts": impacts,
            "portfolio_delta_pct": float(data.get("portfolio_delta_pct", 0)),
            "historical_analog": data.get("historical_analog", {}),
            "hedging_suggestions": data.get("hedging_suggestions", []),
            "summary": str(data.get("summary", "")),
            "confidence": max(0, min(100, int(data.get("confidence", 50)))),
            "regime_shift": str(data.get("regime_shift", "neutral")),
        }

    except Exception as e:
        logger.error("Scenario simulation failed: %s", e)
        return {
            "scenario": scenario,
            "date": _date.today().isoformat(),
            "impacts": [
                {"ticker": tk, "impact_pct": 0, "direction": "neutral",
                 "severity": "low", "reasoning": "Simulation unavailable.",
                 "time_horizon": "N/A", "key_level": 0}
                for tk in tickers
            ],
            "portfolio_delta_pct": 0,
            "historical_analog": {},
            "hedging_suggestions": [],
            "summary": f"Scenario simulation failed: {str(e)[:100]}",
            "confidence": 0,
            "regime_shift": "neutral",
        }
