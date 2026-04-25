"""
scripts/update_source_outcomes.py
──────────────────────────────────────────────────────────────────
Close the dynamic-weights feedback loop.

Reads pending records from the SourceAccuracy ledger (records with
correct=None whose timestamp is at least N trading days old), pulls
forward returns from yfinance, and calls update_outcomes to fill in
the per-source hit/miss verdicts.

Run periodically (cron, GitHub Action, manual) — once a day is plenty.
After enough cycles the rolling accuracy stabilizes and
fuse_signals(use_dynamic_weights=True) starts paying off.

Usage:
    python scripts/update_source_outcomes.py             # 5-day window
    python scripts/update_source_outcomes.py --days 3
    python scripts/update_source_outcomes.py --dry-run   # preview only
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def _parse_iso(s: str) -> Optional[datetime]:
    try:
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _forward_return(ticker: str, ts: datetime, days: int) -> Optional[float]:
    """
    Closing price at ts → closing price `days` trading days later.
    Returns None if we can't get both endpoints.
    """
    try:
        import yfinance as yf
        # Pull a generous window so we have buffer if `ts` lands on a weekend
        start = (ts - timedelta(days=2)).strftime("%Y-%m-%d")
        end = (ts + timedelta(days=days + 7)).strftime("%Y-%m-%d")
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
        if hist.empty:
            return None

        # Find the first close >= ts
        ts_naive = ts.replace(tzinfo=None) if ts.tzinfo else ts
        idx = hist.index.tz_localize(None) if hist.index.tz else hist.index
        on_or_after = [i for i, d in enumerate(idx) if d >= ts_naive]
        if not on_or_after:
            return None
        i0 = on_or_after[0]
        i1 = i0 + days
        if i1 >= len(hist):
            return None
        p0 = float(hist["Close"].iloc[i0])
        p1 = float(hist["Close"].iloc[i1])
        if p0 <= 0:
            return None
        return (p1 - p0) / p0
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=5,
                        help="forward window in trading days")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would update without writing")
    args = parser.parse_args()

    from engine.source_accuracy import SourceAccuracy
    sa = SourceAccuracy()

    cutoff = datetime.now() - timedelta(days=args.days + 1)
    pending_by_ticker: dict[str, list[dict]] = {}
    for r in sa._records:
        if r.get("correct") is not None:
            continue
        ts = _parse_iso(r.get("timestamp", ""))
        if ts is None or ts > cutoff:
            continue
        pending_by_ticker.setdefault(r["ticker"], []).append(r)

    if not pending_by_ticker:
        print("No pending records ready for outcome backfill.")
        return

    print(f"Pending tickers ready for {args.days}-day backfill: "
          f"{len(pending_by_ticker)}")
    total_updated = 0
    for ticker, recs in sorted(pending_by_ticker.items()):
        # Use the earliest pending timestamp per ticker so we backfill
        # everything in one update_outcomes call (it processes all pending
        # records for that ticker against the same forward_return — slightly
        # lossy if records span multiple days, but acceptable for daily runs).
        earliest = min(_parse_iso(r["timestamp"]) for r in recs if _parse_iso(r["timestamp"]))
        ret = _forward_return(ticker, earliest, days=args.days)
        if ret is None:
            print(f"  {ticker}: skipped (no forward price)")
            continue
        if args.dry_run:
            print(f"  {ticker}: would update {len(recs)} records "
                  f"with return {ret*100:+.2f}% (dry-run)")
            continue
        n = sa.update_outcomes(ticker, forward_return=ret)
        total_updated += n
        print(f"  {ticker}: updated {n} records, return {ret*100:+.2f}%")

    if not args.dry_run:
        print(f"\nDone. Total records updated: {total_updated}")
        # Show resulting rolling accuracy
        acc = sa.get_rolling_accuracy(min_samples=3)
        if acc:
            print("\nCurrent rolling accuracy (≥3 samples):")
            for src, a in sorted(acc.items(), key=lambda kv: -kv[1]):
                print(f"  {src:20s} {a*100:.1f}%")


if __name__ == "__main__":
    main()
