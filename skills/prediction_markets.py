"""
skills/prediction_markets.py
──────────────────────────────────────────────────────────────────
Multi-platform prediction-market signal aggregator.

Prediction markets are an independent alpha source — they reflect
"smart money's probability estimate" in binary outcomes. Especially
useful for event-driven tickers (earnings, policy, M&A).

Sources:
  - Polymarket (Gamma public-search, no auth)
  - Kalshi (api.elections.kalshi.com public markets, no auth despite
    the 'elections' subdomain — covers all categories per Kalshi docs)

Both filtered to active, open markets with meaningful liquidity.

Usage:
    from skills.prediction_markets import analyze_prediction_markets
    r = analyze_prediction_markets("NVDA")
    print(r["score"])    # -100..+100 (+ = bullish consensus)
    print(r["markets"])  # list of dicts; 'platform' field tags origin
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_GAMMA_SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
_KALSHI_MARKETS_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"
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
                "platform": "polymarket",
            })
            if len(out) >= limit:
                return out
    return out


def fetch_kalshi_markets(ticker: str, limit: int = 8) -> list[dict]:
    """
    Search Kalshi's public market list for entries mentioning the ticker.
    No authentication required (per Kalshi public docs as of 2026-04).

    Kalshi's API doesn't have a free-text search like Polymarket; we paginate
    open markets and filter client-side by title/subtitle/ticker fields.
    Stops once we have `limit` matches or run out of open markets.
    """
    try:
        import requests
    except ImportError:
        return []

    needle = ticker.lower()
    matches: list[dict] = []
    cursor: Optional[str] = None
    pages_scanned = 0
    MAX_PAGES = 5  # cap to avoid pagination loops

    try:
        while pages_scanned < MAX_PAGES and len(matches) < limit:
            params: dict = {"limit": 200, "status": "open"}
            if cursor:
                params["cursor"] = cursor
            resp = requests.get(_KALSHI_MARKETS_URL, params=params, timeout=5.0)
            if resp.status_code != 200:
                break
            data = resp.json()
            page_markets = data.get("markets", [])
            if not page_markets:
                break

            now = datetime.now(timezone.utc)
            for m in page_markets:
                blob = " ".join(str(m.get(k, "")) for k in
                                ("title", "subtitle", "ticker", "yes_sub_title",
                                 "no_sub_title", "rules_primary"))
                if needle not in blob.lower():
                    continue

                # Kalshi prices are in cents (0-100); convert to 0-1
                try:
                    yes_bid = float(m.get("yes_bid", 0))
                    yes_ask = float(m.get("yes_ask", 100))
                except (ValueError, TypeError):
                    continue
                # Validate per-leg cent range — guards against bad payloads
                # whose midpoint happens to land in [0,1] but with nonsense
                # individual quotes (e.g. bid=-50, ask=200 → mid=0.75).
                if not (0 <= yes_bid <= 100 and 0 <= yes_ask <= 100):
                    continue
                yes_mid = (yes_bid + yes_ask) / 200.0  # cents → prob

                # Skip already-closed markets
                close_time = m.get("close_time")
                try:
                    close_dt = (datetime.fromisoformat(str(close_time).replace("Z", "+00:00"))
                                if close_time else None)
                except Exception:
                    close_dt = None
                if close_dt is not None and close_dt < now:
                    continue

                question = str(m.get("title") or m.get("yes_sub_title") or "")
                if not question:
                    continue

                matches.append({
                    "question": question,
                    "yes_price": yes_mid,
                    "volume_24hr": _safe_float(m.get("volume_24h") or m.get("volume"), 0.0),
                    "liquidity": _safe_float(m.get("liquidity"), 0.0),
                    "end_date": str(close_time or ""),
                    "sign": _bullish_sign(question),
                    "platform": "kalshi",
                })
                if len(matches) >= limit:
                    break

            cursor = data.get("cursor")
            if not cursor:
                break
            pages_scanned += 1
    except Exception as e:
        logger.debug("Kalshi fetch failed for %s: %s", ticker, e)

    return matches


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


def analyze_prediction_markets(
    ticker: str,
    limit: int = 8,
    *,
    include_kalshi: bool = True,
) -> dict:
    """
    Aggregate prediction-market signals across Polymarket + Kalshi for a
    ticker into a fusion-compatible dict.

    Score logic: for each market with a clear bullish/bearish sign, take the
    deviation of yes_price from 0.5 and multiply by the sign. Weight each
    market by log(volume) so liquid markets dominate noise.
    """
    markets = fetch_polymarket_markets(ticker, limit=limit)
    if include_kalshi:
        try:
            markets = markets + fetch_kalshi_markets(ticker, limit=limit)
        except Exception as e:
            logger.debug("Kalshi merge failed for %s: %s", ticker, e)
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
    by_platform: dict[str, int] = {}
    for m in markets:
        p = m.get("platform", "unknown")
        by_platform[p] = by_platform.get(p, 0) + 1
    return {
        "available": True,
        "score": score,
        "weighted_deviation": round(w_avg, 4),
        "n_markets": len(markets),
        "n_directional": directional,
        "n_by_platform": by_platform,
        "total_volume_24hr": round(total_volume, 2),
        "markets": markets[:5],
    }
