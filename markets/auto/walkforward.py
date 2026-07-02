#!/usr/bin/env python3
"""walkforward.py — Walk-forward validation framework for Orallexa entry rule.

Diagnosis P1.2 from research/2026-06-08-markets-stack-deep-diagnosis.md:
The 5/29 backtest hit +60.9% win because it ran on May rally data in-sample.
This script slices decision_log into N sliding (train, test) windows and
reports the *mean* Sharpe-proxy over out-of-sample test windows.

Gate for live trading:
- mean OOS Sharpe > 0.5 across all windows
- worst-window Sharpe > 0
- worst-window max drawdown < 25%

If any of those fail, walk-forward says "don't trade real money".

Usage:
    python3 walkforward.py                    # default 4 windows, 5d lookahead
    python3 walkforward.py --windows 6 --train 14 --test 7
    python3 walkforward.py --use-atr-stops --sector-cap 0.30
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from portfolio_paper import load_decisions, simulate  # noqa: E402

# ROOT/engine for CPCV primitives (Tier-2 #14, shipped 2026-07-02).
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from engine.cpcv import (  # noqa: E402
    generate_cpcv_splits,
    label_windows_from_lookahead,
)


def slice_decisions(decisions: list[dict], train_days: int, test_days: int,
                    n_windows: int) -> list[tuple[list[dict], list[dict]]]:
    """Yield (train_decisions, test_decisions) for N sliding windows.

    Windows are anchored at the end of decision history and slide backward.
    Each test window is `test_days` long, immediately following a `train_days`
    train window. Overlap allowed if n_windows × test_days > total_days.
    """
    if not decisions:
        return []

    # Parse timestamps
    def ts(d):
        try:
            t = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
            return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    decisions = [d for d in decisions if ts(d) is not None]
    decisions.sort(key=lambda d: ts(d))
    if not decisions:
        return []

    first = ts(decisions[0]).date()
    last = ts(decisions[-1]).date()
    total_days = (last - first).days
    needed = train_days + test_days
    if total_days < needed:
        print(f"[walkforward] not enough history: have {total_days}d, "
              f"need {needed}d for one window", file=sys.stderr)
        return []

    # Slide windows backward from last
    windows = []
    stride = max(1, (total_days - needed) // max(1, n_windows - 1))
    for i in range(n_windows):
        test_end = last - timedelta(days=i * stride)
        test_start = test_end - timedelta(days=test_days - 1)
        train_end = test_start - timedelta(days=1)
        train_start = train_end - timedelta(days=train_days - 1)

        if train_start < first:
            break

        train = [d for d in decisions if train_start <= ts(d).date() <= train_end]
        test = [d for d in decisions if test_start <= ts(d).date() <= test_end]
        if not train or not test:
            continue
        windows.append((train, test))

    return windows[::-1]  # oldest first for readability


def summarize_window(result: dict) -> str:
    n = result["n_trades"]
    if n == 0:
        return "(empty window — no tradable decisions)"
    pnl = result["cumulative_pnl"]
    win = result["win_rate"] * 100
    sharpe = result["sharpe_proxy"]
    dd = result["max_drawdown_pct"]
    stops = result["n_stops"]
    return (f"n={n:3d}  P&L=${pnl:>+8.0f}  "
            f"win={win:4.1f}%  Sharpe={sharpe:+.2f}  "
            f"DD={dd:.1f}%  stops={stops}/{n}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--windows", type=int, default=4,
                   help="Number of (train, test) sliding windows")
    p.add_argument("--train", type=int, default=14,
                   help="Days per train window")
    p.add_argument("--test", type=int, default=7,
                   help="Days per test window")
    p.add_argument("--since-days", type=int, default=60,
                   help="How many days of decision_log to pull")
    p.add_argument("--lookahead", type=int, default=5)
    p.add_argument("--account", type=float, default=10000.0)
    p.add_argument("--use-atr-stops", action="store_true")
    p.add_argument("--atr-mult", type=float, default=1.5)
    p.add_argument("--sector-cap", type=float, default=None)
    # Tier-2 #14: opt-in CPCV path (López de Prado 2018 §12.4-12.5).
    # Sliding-window CV is the default because CPCV needs to prove
    # itself over N runs before we deprecate sliding-window.
    p.add_argument("--cpcv", action="store_true",
                   help="Use Combinatorial Purged Cross-Validation instead of "
                        "sliding-window (López de Prado 2018 ch. 12).")
    p.add_argument("--cpcv-groups", type=int, default=6,
                   help="Number of CPCV groups (default 6 → C(6,2)=15 splits).")
    p.add_argument("--cpcv-k-test", type=int, default=2,
                   help="Test groups per CPCV split (default 2).")
    p.add_argument("--cpcv-embargo", type=float, default=0.01,
                   help="Embargo fraction of n_samples (default 1%%, "
                        "López de Prado recommendation).")
    args = p.parse_args()

    decisions = load_decisions(args.since_days)
    if not decisions:
        print(f"[walkforward] no decisions in last {args.since_days}d", file=sys.stderr)
        return 1
    print(f"[walkforward] loaded {len(decisions)} decisions in {args.since_days}d window",
          file=sys.stderr)

    if args.cpcv:
        # Combinatorial Purged CV (Tier-2 #14).
        # Sort decisions by time so index = time-order position.
        def _ts(d):
            try:
                t = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
                return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
            except Exception:
                return None
        decisions_sorted = sorted(
            [d for d in decisions if _ts(d) is not None], key=_ts
        )
        n_samples = len(decisions_sorted)
        if n_samples < args.cpcv_groups:
            print(f"[walkforward] {n_samples} decisions < {args.cpcv_groups} groups — "
                  f"try --cpcv-groups < {n_samples}", file=sys.stderr)
            return 1
        label_windows = label_windows_from_lookahead(n_samples, args.lookahead)
        splits = generate_cpcv_splits(
            n_samples=n_samples,
            n_groups=args.cpcv_groups,
            k_test=args.cpcv_k_test,
            label_windows=label_windows,
            embargo_pct=args.cpcv_embargo,
        )
        print(f"\n=== CPCV: {len(splits)} splits "
              f"(C({args.cpcv_groups}, {args.cpcv_k_test})) ===")
        print(f"Lookahead={args.lookahead}d, embargo={args.cpcv_embargo * 100:.1f}%")
        print(f"Flags: ATR={args.use_atr_stops}, sector_cap={args.sector_cap}\n")

        oos_results = []
        purge_total = 0
        embargo_total = 0
        for i, s in enumerate(splits):
            test_decisions = [decisions_sorted[idx] for idx in s.test_idx]
            r = simulate(test_decisions, args.lookahead, args.account,
                         use_atr_stops=args.use_atr_stops,
                         atr_stop_mult=args.atr_mult,
                         sector_cap_pct=args.sector_cap)
            oos_results.append(r)
            purge_total += s.n_purged
            embargo_total += s.n_embargoed
            print(f"split {i+1}/{len(splits)}: {summarize_window(r)}  "
                  f"(purged {s.n_purged}, embargoed {s.n_embargoed})")

        print(f"\n[cpcv] total purged: {purge_total}, total embargoed: {embargo_total}")

    else:
        windows = slice_decisions(decisions, args.train, args.test, args.windows)
        if not windows:
            print("[walkforward] no windows produced — try smaller --train/--test or larger --since-days",
                  file=sys.stderr)
            return 1

        print(f"\n=== Walk-forward: {len(windows)} windows ===")
        print(f"Per window: {args.train}d train → {args.test}d OOS test, "
              f"lookahead={args.lookahead}d")
        print(f"Flags: ATR={args.use_atr_stops}, sector_cap={args.sector_cap}\n")

        oos_results = []
        for i, (train, test) in enumerate(windows):
            # We don't actually "train" anything in this framework — the entry
            # rule is fixed (lives in skills/prediction.py). We just measure
            # how the rule did out-of-sample. If the rule were data-driven,
            # this would be the place to fit on `train` first.
            r = simulate(test, args.lookahead, args.account,
                         use_atr_stops=args.use_atr_stops,
                         atr_stop_mult=args.atr_mult,
                         sector_cap_pct=args.sector_cap)
            oos_results.append(r)
            print(f"window {i+1}/{len(windows)}: {summarize_window(r)}")

    valid = [r for r in oos_results if r["n_trades"] > 0]
    if not valid:
        print("\n[walkforward] all windows empty — cannot grade", file=sys.stderr)
        return 1

    sharpes = [r["sharpe_proxy"] for r in valid]
    mean_sharpe = sum(sharpes) / len(sharpes)
    worst_sharpe = min(sharpes)
    win_rates = [r["win_rate"] for r in valid]
    mean_win = sum(win_rates) / len(win_rates) * 100
    worst_dd = max(r["max_drawdown_pct"] for r in valid)

    print(f"\n=== Out-of-sample summary ===")
    print(f"  mean Sharpe-proxy  : {mean_sharpe:+.2f}")
    print(f"  worst Sharpe-proxy : {worst_sharpe:+.2f}")
    print(f"  mean win rate      : {mean_win:.1f}%")
    print(f"  worst max DD       : {worst_dd:.1f}%")

    print(f"\n=== Live-trading gate ===")
    g1 = mean_sharpe > 0.5
    g2 = worst_sharpe > 0
    g3 = worst_dd < 25
    print(f"  [{'✓' if g1 else '✗'}] mean Sharpe > 0.5")
    print(f"  [{'✓' if g2 else '✗'}] worst Sharpe > 0")
    print(f"  [{'✓' if g3 else '✗'}] worst max DD < 25%")
    verdict = "PASS — entry rule has out-of-sample edge" if (g1 and g2 and g3) \
        else "FAIL — entry rule does NOT generalize. Do not trade real money."
    print(f"\nVerdict: {verdict}")
    return 0 if (g1 and g2 and g3) else 2


if __name__ == "__main__":
    sys.exit(main())
