"""
engine/earnings.py
──────────────────────────────────────────────────────────────────
Earnings calendar + Post-Earnings Announcement Drift (PEAD).

Two signals:
  1. Earnings calendar  — next upcoming earnings date per ticker
  2. PEAD statistics    — historical 5-day drift after each earnings,
                          plus average surprise % and directionality

Usage:
    from engine.earnings import get_earnings_signal
    sig = get_earnings_signal("NVDA")
    print(sig["next_date"])     # "2026-05-20" or None
    print(sig["pead"])           # {"avg_drift_5d": 1.8, "positive_rate": 0.71, ...}
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _earnings_dates_for(ticker: str):
    """
    Return the raw yfinance earnings_dates DataFrame, optionally cached.

    Cache is opt-in: only used when ORALLEXA_USE_CACHE=1. This keeps CI and
    test runs deterministic and isolated from any cached state on disk.
    Without the env var, this falls through to a direct yfinance call —
    same behavior as before the cache was wired in.
    """
    try:
        from engine.historical_cache import get_default_cache, cache_enabled
        if cache_enabled():
            cached = get_default_cache().get_earnings_dates(ticker)
            if cached is not None and not cached.empty:
                return cached
    except Exception as e:  # cache problems must never block the signal
        logger.debug("Earnings cache lookup failed for %s: %s", ticker, e)

    import yfinance as yf
    return yf.Ticker(ticker).earnings_dates


def _to_utc_naive(ts) -> datetime:
    """Normalize a pandas Timestamp (tz-aware or naive) to naive UTC."""
    dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def fetch_earnings_calendar(ticker: str, days_ahead: int = 60) -> list[dict]:
    """
    Return upcoming earnings dates within `days_ahead` days.

    Each entry: {date, days_until, eps_estimate}.
    """
    try:
        ed = _earnings_dates_for(ticker)
        if ed is None or ed.empty:
            return []

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        upcoming = []
        for ts, row in ed.iterrows():
            date = _to_utc_naive(ts)
            delta_days = (date - now).days
            if 0 <= delta_days <= days_ahead:
                est = row.get("EPS Estimate")
                upcoming.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "days_until": delta_days,
                    "eps_estimate": float(est) if est is not None and str(est) != "nan" else None,
                })
        upcoming.sort(key=lambda x: x["days_until"])
        return upcoming
    except Exception as e:
        logger.debug("Earnings calendar fetch failed for %s: %s", ticker, e)
        return []


def compute_pead_stats(ticker: str, lookback_years: int = 2) -> dict:
    """
    Compute post-earnings drift statistics over the past `lookback_years`.

    Returns:
        n_events           : number of past earnings dates
        avg_drift_5d       : mean 5-trading-day return after earnings (%)
        positive_rate      : fraction with positive 5d return (0..1)
        avg_surprise_pct   : mean surprise % (reported vs estimate)
        surprise_drift_corr: Pearson correlation between surprise and drift
        available          : whether enough data to compute
    """
    try:
        import pandas as pd
        import numpy as np

        ed = _earnings_dates_for(ticker)
        if ed is None or ed.empty:
            return {"available": False}

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cutoff = now - timedelta(days=365 * lookback_years)

        past = []
        for ts, row in ed.iterrows():
            date = _to_utc_naive(ts)
            if date < now and date >= cutoff:
                surprise = row.get("Surprise(%)")
                past.append({
                    "date": date,
                    "surprise_pct": float(surprise)
                        if surprise is not None and str(surprise) != "nan" else None,
                })

        if len(past) < 2:
            return {"available": False, "n_events": len(past)}

        # Pull price history spanning oldest earnings to now. Cache-aware
        # when ORALLEXA_USE_CACHE=1 — saves a yfinance round-trip on
        # repeat scans (PEAD lookback is ~2 years of daily bars per call).
        oldest = min(p["date"] for p in past)
        start = (oldest - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        hist = None
        try:
            from engine.historical_cache import get_default_cache, cache_enabled
            if cache_enabled():
                hist = get_default_cache().get_prices(ticker, start=start)
        except Exception as e:
            logger.debug("Price cache lookup failed for %s: %s", ticker, e)
        if hist is None or hist.empty:
            import yfinance as yf
            hist = yf.Ticker(ticker).history(start=start, auto_adjust=True)
        if hist.empty:
            return {"available": False, "n_events": len(past)}

        drifts = []
        surprises_for_corr = []
        drifts_for_corr = []
        for evt in past:
            # Find closest trading day >= event date
            evt_date = pd.Timestamp(evt["date"]).tz_localize(None)
            hist_naive = hist.copy()
            hist_naive.index = hist_naive.index.tz_localize(None) if hist_naive.index.tz else hist_naive.index
            after = hist_naive.loc[hist_naive.index >= evt_date]
            if len(after) < 6:
                continue
            p0 = after["Close"].iloc[0]
            p5 = after["Close"].iloc[5]
            drift = (p5 - p0) / p0 * 100.0
            drifts.append(drift)
            if evt["surprise_pct"] is not None:
                surprises_for_corr.append(evt["surprise_pct"])
                drifts_for_corr.append(drift)

        if not drifts:
            return {"available": False, "n_events": len(past)}

        avg_drift = float(np.mean(drifts))
        positive_rate = float(sum(1 for d in drifts if d > 0) / len(drifts))
        surprises = [e["surprise_pct"] for e in past if e["surprise_pct"] is not None]
        avg_surprise = float(np.mean(surprises)) if surprises else 0.0

        corr = 0.0
        if len(drifts_for_corr) >= 3:
            sx = np.array(surprises_for_corr)
            sy = np.array(drifts_for_corr)
            if sx.std() > 0 and sy.std() > 0:
                corr = float(np.corrcoef(sx, sy)[0, 1])

        return {
            "available": True,
            "n_events": len(drifts),
            "avg_drift_5d": round(avg_drift, 2),
            "positive_rate": round(positive_rate, 2),
            "avg_surprise_pct": round(avg_surprise, 2),
            "surprise_drift_corr": round(corr, 2),
        }
    except Exception as e:
        logger.debug("PEAD stats failed for %s: %s", ticker, e)
        return {"available": False}


def get_earnings_signal(ticker: str, lookback_years: int = 2) -> dict:
    """
    Combined earnings signal: calendar + PEAD.

    Returns dict with:
        ticker, next_date, days_until, eps_estimate, pead, narrative
    """
    calendar = fetch_earnings_calendar(ticker)
    pead = compute_pead_stats(ticker, lookback_years=lookback_years)

    next_event = calendar[0] if calendar else None
    narrative = _build_narrative(ticker, next_event, pead)

    return {
        "ticker": ticker,
        "next_date": next_event["date"] if next_event else None,
        "days_until": next_event["days_until"] if next_event else None,
        "eps_estimate": next_event["eps_estimate"] if next_event else None,
        "pead": pead,
        "narrative": narrative,
    }


def _build_narrative(ticker: str, next_event: Optional[dict], pead: dict) -> str:
    parts = []
    if next_event:
        d = next_event["days_until"]
        eps = next_event["eps_estimate"]
        eps_str = f" (est EPS {eps:.2f})" if eps is not None else ""
        parts.append(f"{ticker} reports in {d} days on {next_event['date']}{eps_str}.")
    else:
        parts.append(f"{ticker}: no earnings scheduled in next 60 days.")

    if pead.get("available"):
        drift = pead["avg_drift_5d"]
        pos = int(pead["positive_rate"] * 100)
        n = pead["n_events"]
        direction = "bullish" if drift > 0.5 else "bearish" if drift < -0.5 else "neutral"
        parts.append(
            f"PEAD history ({n} events): avg {drift:+.1f}% 5d drift, "
            f"{pos}% positive → {direction} bias."
        )
        corr = pead.get("surprise_drift_corr", 0)
        if abs(corr) > 0.3:
            parts.append(f"Surprise↔drift correlation {corr:+.2f} (signal strength).")
    return " ".join(parts)
