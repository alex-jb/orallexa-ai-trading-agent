"""
eval/decision_eval.py
──────────────────────────────────────────────────────────────────
Decision quality evaluation using historical data.

Metrics:
  1. direction_accuracy — was BUY/SELL correct vs N-day forward return?
  2. confidence_calibration — higher confidence = more accurate?
  3. explanation_consistency — same market → same direction?
  4. strategy_backtest_eval — decisions as signals → backtest vs buy-and-hold

Usage:
    python eval/run_eval.py --tickers NVDA --eval all
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf


_ROOT = Path(__file__).resolve().parent.parent
_DECISION_LOG = _ROOT / "memory_data" / "decision_log.json"


def _load_decisions(days: int = 30) -> list[dict]:
    """Load recent decisions from the decision log."""
    if not _DECISION_LOG.exists():
        return []
    with open(_DECISION_LOG, "r", encoding="utf-8") as f:
        log = json.load(f)

    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for entry in log:
        ts = entry.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts)
            if dt >= cutoff:
                recent.append(entry)
        except (ValueError, TypeError):
            continue
    return recent


def _get_forward_return(ticker: str, date_str: str, forward_days: int = 5) -> Optional[float]:
    """Fetch N-day forward return from yfinance."""
    try:
        start = datetime.fromisoformat(date_str).date()
        end = start + timedelta(days=forward_days + 10)  # buffer for weekends
        df = yf.download(ticker, start=str(start), end=str(end), progress=False)
        if df is None or len(df) < 2:
            return None
        close_col = "Close" if "Close" in df.columns else "Adj Close"
        prices = df[close_col].values
        if hasattr(prices[0], '__len__'):
            prices = [p[0] for p in prices]
        entry_price = float(prices[0])
        # Get price at forward_days (or last available)
        idx = min(forward_days, len(prices) - 1)
        future_price = float(prices[idx])
        return (future_price - entry_price) / entry_price
    except Exception:
        return None


# ── 1. Direction Accuracy ─────────────────────────────────────────────────

def direction_accuracy(
    decisions: list[dict] = None,
    forward_days: int = 5,
    days: int = 30,
) -> dict:
    """
    For each BUY/SELL decision, check if the direction was correct
    based on actual N-day forward return.
    """
    if decisions is None:
        decisions = _load_decisions(days)

    results = []
    correct = 0
    total = 0

    # Group by ticker to batch yfinance calls
    by_ticker = defaultdict(list)
    for d in decisions:
        dec = d.get("decision", "")
        if isinstance(dec, dict):
            dec = dec.get("decision", "")
        if dec in ("BUY", "SELL"):
            by_ticker[d.get("ticker", "")].append(d)

    for ticker, entries in by_ticker.items():
        for entry in entries:
            dec = entry.get("decision", "")
            if isinstance(dec, dict):
                dec = dec.get("decision", "")
            ts = entry.get("timestamp", "")
            fwd_return = _get_forward_return(ticker, ts, forward_days)
            if fwd_return is None:
                continue

            is_correct = (dec == "BUY" and fwd_return > 0) or (dec == "SELL" and fwd_return < 0)
            total += 1
            if is_correct:
                correct += 1

            results.append({
                "ticker": ticker,
                "timestamp": ts,
                "decision": dec,
                "forward_return": round(fwd_return, 4),
                "correct": is_correct,
                "confidence": entry.get("confidence", 0),
            })

    accuracy = correct / total if total > 0 else 0
    return {
        "accuracy": round(accuracy, 3),
        "correct": correct,
        "total": total,
        "forward_days": forward_days,
        "details": results,
    }


# ── 2. Confidence Calibration ────────────────────────────────────────────

def confidence_calibration(
    evaluated_decisions: list[dict] = None,
    forward_days: int = 5,
    days: int = 30,
) -> dict:
    """
    Group decisions by confidence bucket and check accuracy per bucket.
    A well-calibrated system has monotonically increasing accuracy.
    """
    if evaluated_decisions is None:
        result = direction_accuracy(forward_days=forward_days, days=days)
        evaluated_decisions = result["details"]

    buckets = [(0, 30), (30, 50), (50, 65), (65, 82)]
    calibration = []

    for lo, hi in buckets:
        in_bucket = [d for d in evaluated_decisions if lo <= d.get("confidence", 0) < hi]
        if not in_bucket:
            calibration.append({"range": f"{lo}-{hi}", "count": 0, "accuracy": None, "avg_return": None})
            continue

        correct = sum(1 for d in in_bucket if d.get("correct"))
        avg_return = sum(d.get("forward_return", 0) for d in in_bucket) / len(in_bucket)
        calibration.append({
            "range": f"{lo}-{hi}",
            "count": len(in_bucket),
            "accuracy": round(correct / len(in_bucket), 3),
            "avg_return": round(avg_return, 4),
        })

    return {"buckets": calibration, "total_evaluated": len(evaluated_decisions)}


# ── 3. Explanation Consistency ───────────────────────────────────────────

def explanation_consistency(
    ticker: str,
    n_runs: int = 3,
) -> dict:
    """
    Run deep_analysis_lite N times on the same ticker.
    Measure direction agreement and confidence spread.
    """
    from core.brain import OrallexaBrain
    from engine.deep_analysis_lite import run_deep_analysis_lite
    from models.confidence import guard_decision

    decisions = []
    confidences = []

    for i in range(n_runs):
        try:
            brain = OrallexaBrain(ticker.upper())
            result = run_deep_analysis_lite(brain)
            dec = guard_decision(result["decision_output"])
            decisions.append(dec.decision)
            confidences.append(dec.confidence)
            print(f"  Run {i+1}/{n_runs}: {dec.decision} ({dec.confidence:.0f}%)")
        except Exception as e:
            decisions.append("ERROR")
            confidences.append(0)
            print(f"  Run {i+1}/{n_runs}: ERROR — {e}")

    # Agreement: fraction with most common decision
    from collections import Counter
    counts = Counter(decisions)
    most_common = counts.most_common(1)[0][1]
    agreement_rate = most_common / len(decisions) if decisions else 0

    # Confidence spread
    import statistics
    conf_std = statistics.stdev(confidences) if len(confidences) > 1 else 0

    return {
        "ticker": ticker,
        "n_runs": n_runs,
        "decisions": decisions,
        "confidences": [round(c, 1) for c in confidences],
        "agreement_rate": round(agreement_rate, 2),
        "confidence_std": round(conf_std, 1),
        "most_common_decision": counts.most_common(1)[0][0] if counts else "N/A",
    }


# ── 4. Strategy Backtest ─────────────────────────────────────────────────

def strategy_backtest_eval(
    decisions: list[dict] = None,
    days: int = 60,
    initial_cash: float = 10000.0,
) -> dict:
    """
    Convert historical decisions to signals, backtest, compare vs buy-and-hold.
    """
    if decisions is None:
        decisions = _load_decisions(days)

    if not decisions:
        return {"error": "No decisions in log", "alpha": 0, "sharpe": 0}

    # Group by ticker
    by_ticker = defaultdict(list)
    for d in decisions:
        by_ticker[d.get("ticker", "NVDA")].append(d)

    results_by_ticker = {}
    for ticker, entries in by_ticker.items():
        try:
            # Get price data covering the decision period
            dates = [e.get("timestamp", "")[:10] for e in entries]
            start = min(dates)
            end_dt = datetime.strptime(max(dates), "%Y-%m-%d") + timedelta(days=10)

            df = yf.download(ticker, start=start, end=str(end_dt.date()), progress=False)
            if df is None or len(df) < 5:
                continue

            close_col = "Close" if "Close" in df.columns else "Adj Close"

            # Build signal series from decisions
            df["signal"] = 0
            for entry in entries:
                dec = entry.get("decision", "")
                if isinstance(dec, dict):
                    dec = dec.get("decision", "")
                ts = entry.get("timestamp", "")[:10]
                try:
                    date_idx = pd.Timestamp(ts)
                    # Find nearest date in index
                    mask = df.index >= date_idx
                    if mask.any():
                        idx = df.index[mask][0]
                        sig = 1 if dec == "BUY" else (-1 if dec == "SELL" else 0)
                        df.loc[idx:, "signal"] = sig
                except Exception:
                    continue

            # Simple return calculation
            df["return"] = df[close_col].pct_change()
            df["strategy_return"] = df["signal"].shift(1) * df["return"]
            df["bh_return"] = df["return"]

            strat_total = (1 + df["strategy_return"].fillna(0)).prod() - 1
            bh_total = (1 + df["bh_return"].fillna(0)).prod() - 1

            # Sharpe
            strat_returns = df["strategy_return"].dropna()
            sharpe = 0
            if len(strat_returns) > 1 and strat_returns.std() > 0:
                sharpe = (strat_returns.mean() / strat_returns.std()) * (252 ** 0.5)

            results_by_ticker[ticker] = {
                "strategy_return": round(float(strat_total), 4),
                "buy_hold_return": round(float(bh_total), 4),
                "alpha": round(float(strat_total - bh_total), 4),
                "sharpe": round(float(sharpe), 2),
                "n_decisions": len(entries),
                "days_tested": len(df),
            }
        except Exception as e:
            results_by_ticker[ticker] = {"error": str(e)[:100]}

    return {"by_ticker": results_by_ticker}
