"""
skills/prediction_markets.py
──────────────────────────────────────────────────────────────────
Polymarket prediction-market signal aggregator.

Prediction markets are an independent alpha source — they reflect
"smart money's probability estimate" in binary outcomes. Especially
useful for event-driven tickers (earnings, policy, M&A).

Uses the Gamma public-search endpoint (no auth). Filters to active,
open markets with meaningful liquidity.

Usage:
    from skills.prediction_markets import analyze_prediction_markets
    r = analyze_prediction_markets("NVDA")
    print(r["score"])    # -100..+100 (+ = bullish consensus)
    print(r["markets"])  # list of dicts (question, yes_price, volume, endDate)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_GAMMA_SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
_BULLISH_KEYWORDS = (
    "beat", "beats", "above", "exceed", "exceeds", "surge", "rally",
    "hit", "reach", "reaches", "up", "rise", "rises", "high", "breakout",
    "win", "wins", "approve", "approval", "bullish",
)
_BEARISH_KEYWORDS = (
    "miss", "misses", "below", "crash", "plunge", "decline",
    "down", "fall", "falls", "low", "breakdown", "lose", "loses",
    "reject", "rejection", "bearish", "drop", "drops",
)


def _bullish_sign(question: str) -> int:
    """
    Return +1 if the question's 'Yes' outcome implies bullish for the ticker,
    -1 if it implies bearish, 0 if unclear.
    """
    q = question.lower()
    bull = sum(1 for w in _BULLISH_KEYWORDS if w in q)
    bear = sum(1 for w in _BEARISH_KEYWORDS if w in q)
    if bull > bear:
        return 1
    if bear > bull:
        return -1
    return 0


def fetch_polymarket_markets(ticker: str, limit: int = 8) -> list[dict]:
    """
    Search Gamma API for markets mentioning the ticker, filter to active
    and open markets, return lightweight dicts.

    Each item: {question, yes_price, volume_24hr, end_date, sign}.
    """
    try:
        import requests
    except ImportError:
        return []

    try:
        resp = requests.get(
            _GAMMA_SEARCH_URL,
            params={"q": ticker, "limit": min(limit * 3, 25)},
            timeout=5.0,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception as e:
        logger.debug("Polymarket search failed for %s: %s", ticker, e)
        return []

    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for event in data.get("events", []):
        for m in event.get("markets", []):
            if m.get("closed") or m.get("archived") or not m.get("active"):
                continue
            # Parse endDate and skip already-resolved markets
            end_iso = m.get("endDate") or m.get("endDateIso")
            try:
                end_dt = datetime.fromisoformat(str(end_iso).replace("Z", "+00:00")) if end_iso else None
            except Exception:
                end_dt = None
            if end_dt is not None and end_dt < now:
                continue

            outcomes = _parse_json_list(m.get("outcomes"))
            prices = _parse_json_list(m.get("outcomePrices"))
            if len(outcomes) < 2 or len(prices) < 2:
                continue
            yes_idx = _yes_index(outcomes)
            if yes_idx is None:
                continue
            try:
                yes_price = float(prices[yes_idx])
            except (ValueError, TypeError):
                continue
            if not 0.0 <= yes_price <= 1.0:
                continue

            question = str(m.get("question", ""))
            out.append({
                "question": question,
                "yes_price": yes_price,
                "volume_24hr": _safe_float(m.get("volume24hr") or m.get("volumeNum") or m.get("volume"), 0.0),
                "liquidity": _safe_float(m.get("liquidity") or m.get("liquidityNum"), 0.0),
                "end_date": str(end_iso or ""),
                "sign": _bullish_sign(question),
            })
            if len(out) >= limit:
                return out
    return out


def _parse_json_list(v) -> list:
    import json
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _yes_index(outcomes: list) -> Optional[int]:
    """
    Find the index of the 'Yes' / bullish-looking outcome.

    Only matches explicit Yes/No-style outcomes. Binary markets with
    non-standard labels (e.g. ["Google", "NVIDIA"]) are rejected because
    guessing the "bullish" side requires knowing which ticker the caller
    cares about — get that wrong and scoring flips sign.
    """
    for i, o in enumerate(outcomes):
        s = str(o).strip().lower()
        if s in ("yes", "y", "true"):
            return i
    return None


def _safe_float(v, default: float) -> float:
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def analyze_prediction_markets(ticker: str, limit: int = 8) -> dict:
    """
    Aggregate Polymarket signals for a ticker into a fusion-compatible dict.

    Score logic: for each market with a clear bullish/bearish sign, take the
    deviation of yes_price from 0.5 and multiply by the sign. Weight each
    market by log(volume) so liquid markets dominate noise.
    """
    markets = fetch_polymarket_markets(ticker, limit=limit)
    if not markets:
        return {"available": False, "score": 0, "n_markets": 0, "markets": []}

    import math
    weighted_sum = 0.0
    weight_total = 0.0
    directional = 0
    for m in markets:
        if m["sign"] == 0:
            continue  # skip ambiguous questions
        deviation = (m["yes_price"] - 0.5) * m["sign"]  # +0.5 = max bullish
        w = 1.0 + math.log1p(max(m["volume_24hr"], 0.0) / 1000.0)
        weighted_sum += deviation * w
        weight_total += w
        directional += 1

    if weight_total == 0:
        # Markets found but all ambiguous → report availability without score
        return {
            "available": True,
            "score": 0,
            "n_markets": len(markets),
            "n_directional": 0,
            "markets": markets[:5],
            "note": "markets found but sentiment unclear",
        }

    w_avg = weighted_sum / weight_total  # range ≈ -0.5..+0.5
    score = int(max(-100, min(100, w_avg * 200)))

    total_volume = sum(m["volume_24hr"] for m in markets)
    return {
        "available": True,
        "score": score,
        "weighted_deviation": round(w_avg, 4),
        "n_markets": len(markets),
        "n_directional": directional,
        "total_volume_24hr": round(total_volume, 2),
        "markets": markets[:5],
    }
