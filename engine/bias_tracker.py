"""
engine/bias_tracker.py
──────────────────────────────────────────────────────────────────
Prediction Bias Self-Correction Engine.

Analyzes historical predictions vs actual outcomes to detect
systematic biases. Feeds bias awareness back into the analysis
pipeline so the model can self-correct over time.

Inspired by MiroFish's persistent memory + belief evolution —
the system learns from its own mistakes.

Usage:
    from engine.bias_tracker import get_bias_profile, get_bias_context
    profile = get_bias_profile()           # full bias analysis
    context = get_bias_context("NVDA")     # compact string for LLM injection
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_DECISION_LOG = _ROOT / "memory_data" / "decision_log.json"
_BIAS_CACHE = _ROOT / "memory_data" / "bias_profile.json"


# ── Core: evaluate predictions against actual returns ────────────────────────

def _load_decisions(days: int = 90) -> list[dict]:
    """Load recent decisions from log."""
    if not _DECISION_LOG.exists():
        return []
    try:
        with open(_DECISION_LOG, "r", encoding="utf-8") as f:
            log = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    cutoff = datetime.now() - timedelta(days=days)
    result = []
    for entry in log:
        ts = entry.get("timestamp", "")
        try:
            if datetime.fromisoformat(ts) >= cutoff:
                result.append(entry)
        except (ValueError, TypeError):
            continue
    return result


def _get_forward_returns_batch(
    ticker: str,
    dates: list[str],
    forward_days: int = 5,
) -> dict[str, Optional[float]]:
    """Batch fetch forward returns for a ticker. Returns {date_str: return}."""
    try:
        import yfinance as yf
        if not dates:
            return {}

        sorted_dates = sorted(dates)
        start = sorted_dates[0][:10]
        end_dt = datetime.strptime(sorted_dates[-1][:10], "%Y-%m-%d") + timedelta(days=forward_days + 15)

        df = yf.download(ticker, start=start, end=str(end_dt.date()), progress=False)
        if df is None or len(df) < 2:
            return {d: None for d in dates}

        close_col = "Close" if "Close" in df.columns else "Adj Close"
        results = {}

        for date_str in dates:
            try:
                target = datetime.fromisoformat(date_str).date()
                # Find entry price (nearest trading day >= target)
                mask = df.index.date >= target
                if not mask.any():
                    results[date_str] = None
                    continue
                entry_idx = df.index[mask][0]
                entry_pos = df.index.get_loc(entry_idx)

                # Find exit price (forward_days later)
                exit_pos = min(entry_pos + forward_days, len(df) - 1)
                if exit_pos <= entry_pos:
                    results[date_str] = None
                    continue

                entry_price = float(df[close_col].iloc[entry_pos])
                exit_price = float(df[close_col].iloc[exit_pos])

                if hasattr(entry_price, '__len__'):
                    entry_price = float(entry_price[0])
                if hasattr(exit_price, '__len__'):
                    exit_price = float(exit_price[0])

                results[date_str] = (exit_price - entry_price) / entry_price
            except Exception:
                results[date_str] = None

        return results
    except Exception as e:
        logger.warning("Forward returns fetch failed for %s: %s", ticker, e)
        return {d: None for d in dates}


def _evaluate_decisions(
    decisions: list[dict],
    forward_days: int = 5,
) -> list[dict]:
    """Evaluate each BUY/SELL decision against actual forward returns."""
    # Group by ticker for batch fetching
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for d in decisions:
        dec = d.get("decision", "")
        if isinstance(dec, dict):
            dec = dec.get("decision", "")
        if dec in ("BUY", "SELL"):
            by_ticker[d.get("ticker", "")].append(d)

    evaluated = []
    for ticker, entries in by_ticker.items():
        dates = [e.get("timestamp", "") for e in entries]
        returns = _get_forward_returns_batch(ticker, dates, forward_days)

        for entry in entries:
            ts = entry.get("timestamp", "")
            fwd_return = returns.get(ts)
            if fwd_return is None:
                continue

            dec = entry.get("decision", "")
            if isinstance(dec, dict):
                dec = dec.get("decision", "")

            is_correct = (dec == "BUY" and fwd_return > 0) or (dec == "SELL" and fwd_return < 0)

            evaluated.append({
                "ticker": ticker,
                "timestamp": ts,
                "decision": dec,
                "confidence": float(entry.get("confidence", 50)),
                "risk_level": entry.get("risk_level", "MEDIUM"),
                "forward_return": round(fwd_return, 4),
                "correct": is_correct,
                "mode": entry.get("mode", ""),
                "source": entry.get("source", ""),
            })

    return evaluated


# ── Bias Profile Builder ─────────────────────────────────────────────────────

def get_bias_profile(
    days: int = 90,
    forward_days: int = 5,
    force_refresh: bool = False,
) -> dict:
    """
    Build comprehensive bias profile from historical predictions.

    Returns dict with:
        overall       : overall accuracy stats
        by_direction  : accuracy split by BUY vs SELL
        by_ticker     : per-ticker accuracy
        by_confidence : accuracy per confidence bucket
        calibration   : is higher confidence = more accurate?
        patterns      : detected systematic biases
        recommendations : self-correction suggestions
        updated_at    : when this profile was generated
    """
    # Check cache (refresh max once per day unless forced)
    if not force_refresh and _BIAS_CACHE.exists():
        try:
            with open(_BIAS_CACHE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            cached_at = cached.get("updated_at", "")
            if cached_at[:10] == datetime.now().isoformat()[:10]:
                return cached
        except (json.JSONDecodeError, OSError):
            pass

    decisions = _load_decisions(days)
    evaluated = _evaluate_decisions(decisions, forward_days)

    if len(evaluated) < 5:
        profile = {
            "status": "insufficient_data",
            "total_evaluated": len(evaluated),
            "minimum_required": 5,
            "updated_at": datetime.now().isoformat(),
        }
        _save_cache(profile)
        return profile

    # Overall accuracy
    correct = sum(1 for e in evaluated if e["correct"])
    total = len(evaluated)
    avg_return = sum(e["forward_return"] for e in evaluated) / total

    # By direction
    buys = [e for e in evaluated if e["decision"] == "BUY"]
    sells = [e for e in evaluated if e["decision"] == "SELL"]
    buy_acc = sum(1 for e in buys if e["correct"]) / len(buys) if buys else 0
    sell_acc = sum(1 for e in sells if e["correct"]) / len(sells) if sells else 0

    # By ticker
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for e in evaluated:
        by_ticker[e["ticker"]].append(e)

    ticker_stats = {}
    for tk, entries in by_ticker.items():
        tk_correct = sum(1 for e in entries if e["correct"])
        tk_avg_ret = sum(e["forward_return"] for e in entries) / len(entries)
        ticker_stats[tk] = {
            "accuracy": round(tk_correct / len(entries), 3),
            "count": len(entries),
            "avg_return": round(tk_avg_ret, 4),
            "buy_count": sum(1 for e in entries if e["decision"] == "BUY"),
            "sell_count": sum(1 for e in entries if e["decision"] == "SELL"),
        }

    # Confidence calibration
    buckets = [(0, 35, "very_low"), (35, 50, "low"), (50, 65, "moderate"), (65, 100, "high")]
    calibration = []
    for lo, hi, label in buckets:
        in_bucket = [e for e in evaluated if lo <= e["confidence"] < hi]
        if not in_bucket:
            calibration.append({"range": f"{lo}-{hi}", "label": label, "count": 0, "accuracy": None})
            continue
        bk_correct = sum(1 for e in in_bucket if e["correct"])
        bk_avg_ret = sum(e["forward_return"] for e in in_bucket) / len(in_bucket)
        calibration.append({
            "range": f"{lo}-{hi}",
            "label": label,
            "count": len(in_bucket),
            "accuracy": round(bk_correct / len(in_bucket), 3),
            "avg_return": round(bk_avg_ret, 4),
        })

    # Detect patterns / biases
    patterns = _detect_patterns(evaluated, buy_acc, sell_acc, calibration, ticker_stats)

    # Build recommendations
    recommendations = _build_recommendations(patterns, buy_acc, sell_acc, correct / total)

    profile = {
        "status": "ready",
        "overall": {
            "accuracy": round(correct / total, 3),
            "correct": correct,
            "total": total,
            "avg_return": round(avg_return, 4),
            "forward_days": forward_days,
            "days_analyzed": days,
        },
        "by_direction": {
            "buy": {"accuracy": round(buy_acc, 3), "count": len(buys)},
            "sell": {"accuracy": round(sell_acc, 3), "count": len(sells)},
        },
        "by_ticker": ticker_stats,
        "calibration": calibration,
        "patterns": patterns,
        "recommendations": recommendations,
        "updated_at": datetime.now().isoformat(),
    }

    _save_cache(profile)
    return profile


def _detect_patterns(
    evaluated: list[dict],
    buy_acc: float,
    sell_acc: float,
    calibration: list[dict],
    ticker_stats: dict,
) -> list[dict]:
    """Detect systematic biases from evaluated decisions."""
    patterns = []

    # 1. Directional bias
    if buy_acc > 0 and sell_acc > 0:
        diff = buy_acc - sell_acc
        if abs(diff) > 0.15:
            better = "BUY" if diff > 0 else "SELL"
            worse = "SELL" if diff > 0 else "BUY"
            patterns.append({
                "type": "directional_bias",
                "severity": "high" if abs(diff) > 0.25 else "medium",
                "description": f"{worse} calls are significantly less accurate than {better} calls ({worse} acc: {min(buy_acc, sell_acc):.0%} vs {better} acc: {max(buy_acc, sell_acc):.0%})",
                "bias_direction": worse,
                "magnitude": round(abs(diff), 3),
            })

    # 2. Overconfidence
    cal_with_data = [c for c in calibration if c["count"] and c["accuracy"] is not None]
    if len(cal_with_data) >= 2:
        high_conf = [c for c in cal_with_data if c["label"] in ("high",)]
        low_conf = [c for c in cal_with_data if c["label"] in ("very_low", "low")]
        if high_conf and low_conf:
            high_acc = high_conf[0]["accuracy"]
            low_acc = max(c["accuracy"] for c in low_conf)
            if high_acc is not None and low_acc is not None and high_acc < low_acc:
                patterns.append({
                    "type": "overconfidence",
                    "severity": "high",
                    "description": f"High-confidence calls ({high_acc:.0%} acc) are LESS accurate than low-confidence ones ({low_acc:.0%}). System is poorly calibrated.",
                    "magnitude": round(low_acc - high_acc, 3),
                })
            elif high_acc is not None and high_acc < 0.55:
                patterns.append({
                    "type": "overconfidence",
                    "severity": "medium",
                    "description": f"High-confidence calls have only {high_acc:.0%} accuracy — barely above random.",
                    "magnitude": round(0.6 - high_acc, 3),
                })

    # 3. Ticker-specific weakness
    for tk, stats in ticker_stats.items():
        if stats["count"] >= 3 and stats["accuracy"] < 0.35:
            patterns.append({
                "type": "ticker_weakness",
                "severity": "medium",
                "ticker": tk,
                "description": f"{tk} predictions are poor: {stats['accuracy']:.0%} accuracy over {stats['count']} calls",
                "magnitude": round(0.5 - stats["accuracy"], 3),
            })

    # 4. Bull bias (too many BUY calls)
    buy_ratio = sum(1 for e in evaluated if e["decision"] == "BUY") / len(evaluated)
    if buy_ratio > 0.75:
        patterns.append({
            "type": "bull_bias",
            "severity": "medium",
            "description": f"System issues BUY {buy_ratio:.0%} of the time — possible bull bias",
            "magnitude": round(buy_ratio - 0.5, 3),
        })
    elif buy_ratio < 0.25:
        patterns.append({
            "type": "bear_bias",
            "severity": "medium",
            "description": f"System issues SELL {1-buy_ratio:.0%} of the time — possible bear bias",
            "magnitude": round(0.5 - buy_ratio, 3),
        })

    return patterns


def _build_recommendations(
    patterns: list[dict],
    buy_acc: float,
    sell_acc: float,
    overall_acc: float,
) -> list[str]:
    """Build actionable self-correction recommendations."""
    recs = []

    for p in patterns:
        if p["type"] == "directional_bias":
            worse = p["bias_direction"]
            recs.append(f"Reduce confidence on {worse} calls by ~15% until accuracy improves")
        elif p["type"] == "overconfidence":
            recs.append("Scale down all confidence scores by 10-20% — system is overconfident")
        elif p["type"] == "ticker_weakness":
            tk = p.get("ticker", "")
            recs.append(f"Consider defaulting to WAIT for {tk} unless signal strength >70")
        elif p["type"] == "bull_bias":
            recs.append("Apply stricter criteria for BUY signals — require RSI < 65 and positive MACD")
        elif p["type"] == "bear_bias":
            recs.append("Review SELL criteria — may be too aggressive on bearish signals")

    if overall_acc < 0.45:
        recs.append("Overall accuracy is below 45% — consider reducing position sizes across the board")

    if not recs:
        recs.append("No significant biases detected — continue monitoring")

    return recs


# ── LLM Context Injection ────────────────────────────────────────────────────

def get_bias_context(ticker: Optional[str] = None) -> str:
    """
    Generate a compact bias awareness string for LLM prompt injection.

    This is injected into the Judge/Risk Manager prompts to help
    the model self-correct based on historical performance.
    """
    profile = get_bias_profile()

    if profile.get("status") != "ready":
        return ""

    overall = profile.get("overall", {})
    by_dir = profile.get("by_direction", {})
    patterns = profile.get("patterns", [])
    recommendations = profile.get("recommendations", [])

    lines = ["HISTORICAL BIAS AWARENESS:"]
    lines.append(
        f"Overall accuracy: {overall.get('accuracy', 0):.0%} "
        f"({overall.get('correct', 0)}/{overall.get('total', 0)} correct over "
        f"{overall.get('days_analyzed', 0)} days)"
    )

    buy_data = by_dir.get("buy", {})
    sell_data = by_dir.get("sell", {})
    if buy_data.get("count", 0) > 0 and sell_data.get("count", 0) > 0:
        lines.append(
            f"BUY accuracy: {buy_data['accuracy']:.0%} ({buy_data['count']} calls) | "
            f"SELL accuracy: {sell_data['accuracy']:.0%} ({sell_data['count']} calls)"
        )

    # Ticker-specific
    if ticker:
        tk_stats = profile.get("by_ticker", {}).get(ticker)
        if tk_stats and tk_stats.get("count", 0) >= 3:
            lines.append(
                f"{ticker} specific: {tk_stats['accuracy']:.0%} accuracy over "
                f"{tk_stats['count']} calls (avg return: {tk_stats['avg_return']:+.2%})"
            )

    # Key patterns
    for p in patterns[:3]:
        lines.append(f"⚠ {p['description']}")

    # Top recommendation
    if recommendations:
        lines.append(f"Correction: {recommendations[0]}")

    return "\n".join(lines)


# ── Cache Management ─────────────────────────────────────────────────────────

def _save_cache(profile: dict) -> None:
    """Save bias profile to cache file."""
    try:
        _BIAS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(_BIAS_CACHE, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logger.warning("Failed to save bias cache: %s", e)
