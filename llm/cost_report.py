"""
llm/cost_report.py
──────────────────────────────────────────────────────────────────
Cost and usage analytics from LLM call logs.

Usage:
    from llm.cost_report import daily_cost_summary, print_cost_report
    print_cost_report()
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from llm.call_logger import load_call_log


def daily_cost_summary(path: str = None) -> dict:
    """Group LLM calls by date, return cost/count/latency breakdown."""
    records = load_call_log(path)
    by_date = defaultdict(lambda: {"total_cost": 0, "call_count": 0, "total_latency_ms": 0,
                                     "input_tokens": 0, "output_tokens": 0, "by_tier": defaultdict(float)})

    for r in records:
        date = r.get("timestamp", "")[:10]
        by_date[date]["total_cost"] += r.get("estimated_cost_usd", 0)
        by_date[date]["call_count"] += 1
        by_date[date]["total_latency_ms"] += r.get("latency_ms", 0)
        by_date[date]["input_tokens"] += r.get("input_tokens", 0)
        by_date[date]["output_tokens"] += r.get("output_tokens", 0)
        by_date[date]["by_tier"][r.get("tier", "UNKNOWN")] += r.get("estimated_cost_usd", 0)

    return dict(by_date)


def session_cost_summary(minutes: int = 60, path: str = None) -> dict:
    """Summarize LLM usage in the last N minutes."""
    records = load_call_log(path)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    recent = []
    for r in records:
        try:
            ts = datetime.fromisoformat(r.get("timestamp", ""))
            if ts >= cutoff:
                recent.append(r)
        except (ValueError, TypeError):
            continue

    total_cost = sum(r.get("estimated_cost_usd", 0) for r in recent)
    total_input = sum(r.get("input_tokens", 0) for r in recent)
    total_output = sum(r.get("output_tokens", 0) for r in recent)
    total_latency = sum(r.get("latency_ms", 0) for r in recent)

    by_type = defaultdict(lambda: {"count": 0, "cost": 0})
    for r in recent:
        rt = r.get("request_type", "unknown")
        by_type[rt]["count"] += 1
        by_type[rt]["cost"] += r.get("estimated_cost_usd", 0)

    return {
        "minutes": minutes,
        "call_count": len(recent),
        "total_cost_usd": round(total_cost, 6),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_latency_ms": total_latency,
        "avg_latency_ms": round(total_latency / len(recent)) if recent else 0,
        "by_request_type": dict(by_type),
    }


def print_cost_report(path: str = None) -> None:
    """Print a formatted cost report to stdout."""
    daily = daily_cost_summary(path)
    if not daily:
        print("No LLM calls logged yet.")
        return

    print(f"\n{'='*55}")
    print("  Oralexxa LLM Cost Report")
    print(f"{'='*55}")
    print(f"{'Date':<12} {'Calls':>6} {'Input':>8} {'Output':>8} {'Cost':>10} {'Latency':>9}")
    print("─" * 55)
    total_cost = 0
    total_calls = 0
    for date in sorted(daily.keys()):
        d = daily[date]
        total_cost += d["total_cost"]
        total_calls += d["call_count"]
        print(f"{date:<12} {d['call_count']:>6} {d['input_tokens']:>8} {d['output_tokens']:>8} "
              f"${d['total_cost']:>9.4f} {d['total_latency_ms']:>7}ms")
    print("─" * 55)
    print(f"{'TOTAL':<12} {total_calls:>6} {'':>8} {'':>8} ${total_cost:>9.4f}")
    print(f"{'='*55}\n")
