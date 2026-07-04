"""
markets/auto/enrich_spacex_decisions.py — post-process SpaceX daily
decisions with insider-signal enrichment.

Ships 2026-07-03 (Tier-2 #13 wire-in follow-up).

Why a separate script (not editing spacex-daily.sh)
---------------------------------------------------
The live spacex-daily.sh cron has been in production for weeks
generating Alex's daily brief. Modifying it in-place risks the
daily brief silently breaking. This script runs INDEPENDENTLY —
reads the same decision log + insider events, calls
`markets.auto.insider_join.enrich_decision_with_insider`, writes
enriched decisions to a NEW file so the original stays untouched.

Once this script proves itself over a week or so, Alex can decide
to make it a launchd cron chained after spacex-daily.sh.

Data flow
---------
Reads:
  ~/.orallexa/markets/decision_log.jsonl       (from run_daily_pilot.py)
  ~/.orallexa/markets/insider_transactions.jsonl  (from news_morning.py)

Writes:
  ~/.orallexa/markets/decision_log_enriched.jsonl

The output has the same shape as the input plus 3 extra fields per
decision (from `enrich_decision_with_insider`):
  insider_p_up_delta        # signed adjustment
  insider_events_n          # count of qualifying events
  insider_cluster           # bool, C-suite cluster fired

Usage
-----
    python3 markets/auto/enrich_spacex_decisions.py

Optional flag:
    --since-days 7   # only enrich decisions from the last N days

Exit codes
----------
0 = ran successfully, output written
1 = failed to build enriched output (no decisions found, source
    files missing, or import error)
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path


HOME = Path.home()
DEFAULT_DECISIONS = HOME / ".orallexa" / "markets" / "decision_log.jsonl"
DEFAULT_INSIDERS = HOME / ".orallexa" / "markets" / "insider_transactions.jsonl"
DEFAULT_OUTPUT = HOME / ".orallexa" / "markets" / "decision_log_enriched.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        with path.open() as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    out.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def _filter_recent(rows: list[dict], since_days: int, ts_field: str = "timestamp") -> list[dict]:
    """Keep rows newer than `since_days` ago based on a timestamp field.
    Rows missing the field are KEPT (defensive — don't silently drop)."""
    if since_days <= 0:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    out = []
    for r in rows:
        ts_str = r.get(ts_field) or r.get("date")
        if not ts_str:
            out.append(r)
            continue
        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                out.append(r)
        except (ValueError, TypeError):
            out.append(r)  # unparseable → keep
    return out


def _group_insiders_by_ticker(events: list[dict]) -> dict[str, list[dict]]:
    """Group insider events by ticker (uppercased)."""
    out: dict[str, list[dict]] = {}
    for ev in events:
        ticker = ev.get("ticker") or ev.get("symbol")
        if not ticker:
            continue
        out.setdefault(str(ticker).upper(), []).append(ev)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS,
                   help="Path to decision_log.jsonl")
    p.add_argument("--insiders", type=Path, default=DEFAULT_INSIDERS,
                   help="Path to insider_transactions.jsonl")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                   help="Path to write enriched decision log")
    p.add_argument("--since-days", type=int, default=30,
                   help="Only enrich decisions from the last N days (0 = all)")
    args = p.parse_args(argv)

    # Add repo root to sys.path so `markets.auto.insider_join` imports work.
    _REPO_ROOT = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(_REPO_ROOT))

    try:
        from markets.auto.insider_join import enrich_decision_with_insider
    except ImportError as exc:
        print(f"[enrich-spacex] FATAL: cannot import insider_join: {exc}",
              file=sys.stderr)
        return 1

    decisions = _read_jsonl(args.decisions)
    insiders = _read_jsonl(args.insiders)
    print(f"[enrich-spacex] loaded {len(decisions)} decisions from "
          f"{args.decisions}", file=sys.stderr)
    print(f"[enrich-spacex] loaded {len(insiders)} insider events from "
          f"{args.insiders}", file=sys.stderr)

    if not decisions:
        print("[enrich-spacex] no decisions to enrich — nothing to write",
              file=sys.stderr)
        return 1

    decisions = _filter_recent(decisions, args.since_days)
    insiders_by_ticker = _group_insiders_by_ticker(insiders)
    print(f"[enrich-spacex] {len(decisions)} decisions within {args.since_days}d "
          f"across {len(insiders_by_ticker)} tickers with insider events",
          file=sys.stderr)

    enriched: list[dict] = []
    stats = {"enriched_nonzero": 0, "cluster_hit": 0}

    for d in decisions:
        ticker = d.get("ticker") or d.get("symbol")
        if not ticker:
            enriched.append(d)
            continue
        events = insiders_by_ticker.get(str(ticker).upper(), [])
        try:
            e = enrich_decision_with_insider(
                ticker=ticker, decision=d, insider_events=events,
            )
        except Exception as exc:
            # Any failure per-decision: keep original + note the error.
            print(f"[enrich-spacex] WARN: enrich failed for {ticker}: {exc}",
                  file=sys.stderr)
            e = dict(d)
            e["insider_enrichment_error"] = str(exc)
        enriched.append(e)
        if abs(e.get("insider_p_up_delta", 0)) > 0.001:
            stats["enriched_nonzero"] += 1
        if e.get("insider_cluster"):
            stats["cluster_hit"] += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("w") as f:
            for e in enriched:
                f.write(json.dumps(e, default=str) + "\n")
    except OSError as exc:
        print(f"[enrich-spacex] FATAL: cannot write output: {exc}",
              file=sys.stderr)
        return 1

    print(f"[enrich-spacex] wrote {len(enriched)} decisions → {args.output}")
    print(f"[enrich-spacex] {stats['enriched_nonzero']}/{len(enriched)} had "
          f"non-zero insider adjustment; {stats['cluster_hit']} had C-suite "
          f"cluster fire.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
