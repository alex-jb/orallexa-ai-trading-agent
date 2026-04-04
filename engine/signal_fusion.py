"""
engine/signal_fusion.py
──────────────────────────────────────────────────────────────────
Multi-Source Signal Fusion Engine.

Aggregates heterogeneous signals into a unified conviction score
using dynamic Bayesian-inspired weighting based on recent accuracy.

Signal sources:
  1. Technical indicators  (existing: TechnicalAnalysisSkillV2)
  2. News sentiment        (existing: sentiment.py)
  3. ML model ensemble     (existing: ml_signal.py)
  4. Options flow          (NEW: unusual options activity)
  5. Institutional data    (NEW: insider transactions + fund flows)
  6. Factor engine         (existing: factor_engine.py)

Usage:
    from engine.signal_fusion import fuse_signals
    result = fuse_signals("NVDA", summary=summary, ml_result=ml_result)
    print(result["conviction"])      # -100 to +100
    print(result["sources"])         # per-source breakdown
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── Signal Source: Options Flow ──────────────────────────────────────────────

def _fetch_options_flow(ticker: str) -> dict:
    """
    Fetch options flow signals from yfinance options chain.
    Analyzes put/call ratio, unusual volume, and max pain.
    """
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        expirations = tk.options
        if not expirations:
            return {"available": False}

        # Use nearest expiration
        nearest = expirations[0]
        chain = tk.option_chain(nearest)
        calls = chain.calls
        puts = chain.puts

        if calls.empty and puts.empty:
            return {"available": False}

        # Put/Call ratio (volume-based)
        call_vol = calls["volume"].sum() if "volume" in calls.columns else 0
        put_vol = puts["volume"].sum() if "volume" in puts.columns else 0
        pc_ratio = put_vol / call_vol if call_vol > 0 else 1.0

        # Put/Call OI ratio
        call_oi = calls["openInterest"].sum() if "openInterest" in calls.columns else 0
        put_oi = puts["openInterest"].sum() if "openInterest" in puts.columns else 0
        pc_oi_ratio = put_oi / call_oi if call_oi > 0 else 1.0

        # Unusual activity: options with volume > 3x open interest
        unusual_calls = []
        unusual_puts = []
        if "volume" in calls.columns and "openInterest" in calls.columns:
            mask = (calls["volume"] > 0) & (calls["openInterest"] > 0)
            unusual = calls[mask & (calls["volume"] > 3 * calls["openInterest"])]
            for _, row in unusual.head(3).iterrows():
                unusual_calls.append({
                    "strike": float(row["strike"]),
                    "volume": int(row["volume"]),
                    "oi": int(row["openInterest"]),
                    "ratio": round(float(row["volume"] / row["openInterest"]), 1),
                })

        if "volume" in puts.columns and "openInterest" in puts.columns:
            mask = (puts["volume"] > 0) & (puts["openInterest"] > 0)
            unusual = puts[mask & (puts["volume"] > 3 * puts["openInterest"])]
            for _, row in unusual.head(3).iterrows():
                unusual_puts.append({
                    "strike": float(row["strike"]),
                    "volume": int(row["volume"]),
                    "oi": int(row["openInterest"]),
                    "ratio": round(float(row["volume"] / row["openInterest"]), 1),
                })

        # Max Pain calculation (simplified)
        max_pain = _calculate_max_pain(calls, puts)

        # Score: low P/C = bullish, high P/C = bearish
        if pc_ratio < 0.5:
            score = 60    # very bullish options flow
        elif pc_ratio < 0.7:
            score = 30
        elif pc_ratio < 1.0:
            score = 10
        elif pc_ratio < 1.3:
            score = -10
        elif pc_ratio < 1.8:
            score = -30
        else:
            score = -60   # very bearish options flow

        # Boost if unusual call activity
        if len(unusual_calls) > len(unusual_puts):
            score += 15
        elif len(unusual_puts) > len(unusual_calls):
            score -= 15

        return {
            "available": True,
            "score": max(-100, min(100, score)),
            "pc_ratio": round(pc_ratio, 2),
            "pc_oi_ratio": round(pc_oi_ratio, 2),
            "call_volume": int(call_vol),
            "put_volume": int(put_vol),
            "unusual_calls": unusual_calls,
            "unusual_puts": unusual_puts,
            "max_pain": max_pain,
            "expiration": nearest,
        }
    except Exception as e:
        logger.debug("Options flow fetch failed for %s: %s", ticker, e)
        return {"available": False}


def _calculate_max_pain(calls, puts) -> Optional[float]:
    """Calculate max pain price (strike where option writers lose least)."""
    try:
        all_strikes = sorted(set(calls["strike"].tolist() + puts["strike"].tolist()))
        if not all_strikes:
            return None

        min_pain = float("inf")
        max_pain_strike = all_strikes[0]

        for strike in all_strikes:
            # Call pain: sum of intrinsic value * OI for all ITM calls
            call_pain = 0
            for _, row in calls.iterrows():
                if strike > row["strike"]:
                    call_pain += (strike - row["strike"]) * row.get("openInterest", 0)

            # Put pain
            put_pain = 0
            for _, row in puts.iterrows():
                if strike < row["strike"]:
                    put_pain += (row["strike"] - strike) * row.get("openInterest", 0)

            total_pain = call_pain + put_pain
            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = strike

        return round(float(max_pain_strike), 2)
    except Exception:
        return None


# ── Signal Source: Institutional Data ────────────────────────────────────────

def _fetch_institutional_signals(ticker: str) -> dict:
    """
    Fetch institutional ownership signals from yfinance.
    Includes insider transactions and major holder changes.
    """
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)

        # Insider transactions
        insider_score = 0
        insider_transactions = []
        try:
            insiders = tk.insider_transactions
            if insiders is not None and not insiders.empty:
                recent = insiders.head(10)
                buys = 0
                sells = 0
                for _, row in recent.iterrows():
                    text = str(row.get("Text", "")).lower()
                    shares = abs(int(row.get("Shares", 0)))
                    if "purchase" in text or "buy" in text or "acquisition" in text:
                        buys += shares
                        insider_transactions.append({
                            "type": "buy",
                            "shares": shares,
                            "text": str(row.get("Text", ""))[:80],
                        })
                    elif "sale" in text or "sell" in text:
                        sells += shares
                        insider_transactions.append({
                            "type": "sell",
                            "shares": shares,
                            "text": str(row.get("Text", ""))[:80],
                        })

                if buys + sells > 0:
                    buy_ratio = buys / (buys + sells)
                    insider_score = int((buy_ratio - 0.5) * 120)  # -60 to +60
        except Exception:
            pass

        # Institutional holders
        inst_pct = 0.0
        top_holders = []
        try:
            holders = tk.institutional_holders
            if holders is not None and not holders.empty:
                for _, row in holders.head(5).iterrows():
                    top_holders.append({
                        "holder": str(row.get("Holder", ""))[:40],
                        "shares": int(row.get("Shares", 0)),
                        "pct": round(float(row.get("% Out", 0)) * 100, 2) if row.get("% Out") else 0,
                    })
                inst_pct = sum(h["pct"] for h in top_holders)
        except Exception:
            pass

        # Short interest (from info)
        short_pct = 0.0
        try:
            info = tk.info
            short_pct = float(info.get("shortPercentOfFloat", 0)) * 100
        except Exception:
            pass

        # Institutional score
        inst_score = insider_score
        if short_pct > 10:
            inst_score -= 20  # high short interest = bearish pressure
        elif short_pct > 5:
            inst_score -= 10
        elif short_pct < 2:
            inst_score += 10  # low short interest = less bearish pressure

        return {
            "available": True,
            "score": max(-100, min(100, inst_score)),
            "insider_score": insider_score,
            "insider_transactions": insider_transactions[:5],
            "institutional_pct": round(inst_pct, 1),
            "top_holders": top_holders,
            "short_pct": round(short_pct, 1),
        }
    except Exception as e:
        logger.debug("Institutional data failed for %s: %s", ticker, e)
        return {"available": False}


# ── Signal Source: Technical Score ───────────────────────────────────────────

def _score_technical(summary: dict) -> dict:
    """Convert technical indicator summary to a -100 to +100 score."""
    score = 0
    signals = []

    rsi = summary.get("rsi")
    if rsi:
        if rsi > 70:
            score -= 25
            signals.append("RSI overbought")
        elif rsi < 30:
            score += 25
            signals.append("RSI oversold")
        elif rsi > 50:
            score += 10
        else:
            score -= 10

    macd_hist = summary.get("macd_hist")
    if macd_hist:
        score += max(-20, min(20, int(macd_hist * 200)))
        signals.append(f"MACD {'positive' if macd_hist > 0 else 'negative'}")

    close = summary.get("close", 0)
    ma20 = summary.get("ma20")
    ma50 = summary.get("ma50")
    if close and ma20 and ma50:
        if close > ma20 > ma50:
            score += 20
            signals.append("Bullish MA alignment")
        elif close < ma20 < ma50:
            score -= 20
            signals.append("Bearish MA alignment")

    adx = summary.get("adx")
    if adx and adx > 25:
        score = int(score * 1.2)  # amplify in trending market
        signals.append("Strong trend (ADX)")

    vol_ratio = summary.get("volume_ratio")
    if vol_ratio and vol_ratio > 1.5:
        signals.append("Above-avg volume")

    return {
        "score": max(-100, min(100, score)),
        "signals": signals,
    }


# ── Signal Source: ML Consensus ──────────────────────────────────────────────

def _score_ml(ml_result: Optional[dict]) -> dict:
    """Convert ML model results to a consensus score."""
    if not ml_result:
        return {"score": 0, "available": False, "agreement": 0}

    results = ml_result.get("results", {})
    scores = []

    for name in ("random_forest", "xgboost", "logistic_regression",
                 "chronos2", "moirai2", "emaformer", "diffusion", "gnn", "rl_ppo"):
        data = results.get(name)
        if data and data.get("status", "ok") == "ok":
            metrics = data["metrics"]
            sharpe = metrics.get("sharpe", 0)
            ret = metrics.get("total_return", 0)
            # Convert to directional score
            model_score = int(np.sign(sharpe) * min(abs(sharpe) * 20, 30))
            model_score += int(np.sign(ret) * min(abs(ret) * 50, 20))
            scores.append(max(-50, min(50, model_score)))

    if not scores:
        return {"score": 0, "available": False, "agreement": 0}

    avg_score = sum(scores) / len(scores)
    # Agreement: how many models agree on direction
    bullish = sum(1 for s in scores if s > 0)
    bearish = sum(1 for s in scores if s < 0)
    agreement = max(bullish, bearish) / len(scores) * 100

    return {
        "score": max(-100, min(100, int(avg_score * 2))),
        "available": True,
        "agreement": round(agreement),
        "n_models": len(scores),
    }


# ── Signal Source: News Sentiment ────────────────────────────────────────────

def _score_news(news_items: list) -> dict:
    """Convert news items to a sentiment score."""
    if not news_items:
        return {"score": 0, "available": False}

    scores = [item.get("score", 0) for item in news_items]
    avg = sum(scores) / len(scores)
    # Scale to -100..+100
    score = int(avg * 200)

    bullish = sum(1 for s in scores if s > 0.1)
    bearish = sum(1 for s in scores if s < -0.1)

    return {
        "score": max(-100, min(100, score)),
        "available": True,
        "avg_sentiment": round(avg, 3),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "total": len(scores),
    }


# ── Main Fusion ──────────────────────────────────────────────────────────────

# Default weights — can be dynamically adjusted based on bias tracker
DEFAULT_WEIGHTS = {
    "technical":     0.25,
    "ml_ensemble":   0.25,
    "news_sentiment": 0.15,
    "options_flow":  0.20,
    "institutional": 0.15,
}


def fuse_signals(
    ticker: str,
    summary: dict = None,
    ml_result: dict = None,
    news_items: list = None,
    weights: dict = None,
) -> dict:
    """
    Fuse all signal sources into a unified conviction score.

    Parameters
    ----------
    ticker      : stock symbol
    summary     : technical indicator summary dict
    ml_result   : ML analysis result dict
    news_items  : list of news items with sentiment scores
    weights     : optional custom weights per source

    Returns
    -------
    dict with keys:
        conviction    : -100 (max bearish) to +100 (max bullish)
        direction     : "BULLISH" / "BEARISH" / "NEUTRAL"
        confidence    : 0-100 (based on source agreement)
        sources       : per-source scores and details
        fusion_detail : explanation of how conviction was derived
    """
    if weights is None:
        weights = dict(DEFAULT_WEIGHTS)

    sources = {}

    # 1. Technical indicators
    if summary:
        tech = _score_technical(summary)
        sources["technical"] = {
            "score": tech["score"],
            "weight": weights.get("technical", 0.25),
            "available": True,
            "signals": tech.get("signals", []),
        }
    else:
        sources["technical"] = {"score": 0, "weight": 0, "available": False}

    # 2. ML ensemble
    ml = _score_ml(ml_result)
    sources["ml_ensemble"] = {
        "score": ml["score"],
        "weight": weights.get("ml_ensemble", 0.25) if ml.get("available") else 0,
        "available": ml.get("available", False),
        "agreement": ml.get("agreement", 0),
        "n_models": ml.get("n_models", 0),
    }

    # 3. News sentiment
    news = _score_news(news_items or [])
    sources["news_sentiment"] = {
        "score": news["score"],
        "weight": weights.get("news_sentiment", 0.15) if news.get("available") else 0,
        "available": news.get("available", False),
    }

    # 4. Options flow (live fetch)
    options = _fetch_options_flow(ticker)
    sources["options_flow"] = {
        "score": options.get("score", 0),
        "weight": weights.get("options_flow", 0.20) if options.get("available") else 0,
        "available": options.get("available", False),
        "pc_ratio": options.get("pc_ratio"),
        "unusual_calls": options.get("unusual_calls", []),
        "unusual_puts": options.get("unusual_puts", []),
        "max_pain": options.get("max_pain"),
    }

    # 5. Institutional data (live fetch)
    inst = _fetch_institutional_signals(ticker)
    sources["institutional"] = {
        "score": inst.get("score", 0),
        "weight": weights.get("institutional", 0.15) if inst.get("available") else 0,
        "available": inst.get("available", False),
        "insider_transactions": inst.get("insider_transactions", []),
        "short_pct": inst.get("short_pct", 0),
        "institutional_pct": inst.get("institutional_pct", 0),
    }

    # Normalize weights for available sources
    total_weight = sum(s["weight"] for s in sources.values())
    if total_weight > 0:
        for s in sources.values():
            s["normalized_weight"] = round(s["weight"] / total_weight, 3)
    else:
        for s in sources.values():
            s["normalized_weight"] = 0

    # Weighted conviction
    conviction = 0.0
    for s in sources.values():
        conviction += s["score"] * s["normalized_weight"]
    conviction = max(-100, min(100, int(conviction)))

    # Direction
    if conviction > 15:
        direction = "BULLISH"
    elif conviction < -15:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    # Confidence based on source agreement
    available_sources = [s for s in sources.values() if s["available"]]
    if available_sources:
        directions = [1 if s["score"] > 10 else (-1 if s["score"] < -10 else 0)
                      for s in available_sources]
        if directions:
            agree_pct = max(
                sum(1 for d in directions if d == 1),
                sum(1 for d in directions if d == -1),
            ) / len(directions)
        else:
            agree_pct = 0
        confidence = int(agree_pct * 80 + len(available_sources) / 5 * 20)
    else:
        confidence = 0

    # Build explanation
    ranked = sorted(
        [(name, s) for name, s in sources.items() if s["available"]],
        key=lambda x: abs(x[1]["score"]),
        reverse=True,
    )
    detail_parts = []
    for name, s in ranked[:3]:
        label = name.replace("_", " ").title()
        dir_word = "bullish" if s["score"] > 10 else "bearish" if s["score"] < -10 else "neutral"
        detail_parts.append(f"{label}: {dir_word} ({s['score']:+d})")

    return {
        "conviction": conviction,
        "direction": direction,
        "confidence": min(100, confidence),
        "n_sources": len(available_sources),
        "sources": sources,
        "fusion_detail": " | ".join(detail_parts),
    }
