"""
eval/daily_eval.py
--------------------------------------------------------------------
Daily evaluation runner.

Runs the evaluation harness, saves timestamped results,
and tracks Sharpe drift over time.

Usage:
    python eval/daily_eval.py                          # Run once
    python eval/daily_eval.py --history                # Show Sharpe drift
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_ROOT = Path(__file__).resolve().parent.parent
_HISTORY_DIR = _ROOT / "eval" / "history"
_DEFAULT_TICKERS = ["NVDA", "AAPL", "TSLA", "MSFT", "GOOG", "AMZN", "META", "AMD", "INTC", "JPM"]

logger = logging.getLogger("eval.daily")


def run_daily_eval(tickers: list[str] | None = None, seed: int = 42) -> dict:
    """Run evaluation harness and save timestamped results."""
    from eval.harness import EvaluationHarness
    from eval.report_generator import generate_report, _result_to_dict

    tickers = tickers or _DEFAULT_TICKERS
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Running daily eval on %d tickers", len(tickers))
    harness = EvaluationHarness(tickers=tickers, mc_seed=seed)

    try:
        from tqdm import tqdm
        pbar = tqdm(total=len(tickers) * len(harness.strategies), desc="Daily eval", unit="pair")
        result = harness.run(progress_callback=lambda: pbar.update(1))
        pbar.close()
    except ImportError:
        result = harness.run()

    # Generate report (overwrites latest)
    generate_report(result)

    # Save timestamped snapshot
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    snapshot = _result_to_dict(result)
    snapshot["run_date"] = date_str
    snapshot["run_timestamp"] = now.isoformat()

    # Per-strategy summary for drift tracking
    strategy_summary = {}
    for ev in result.evaluations:
        key = f"{ev.strategy_name}_{ev.ticker}"
        wf = ev.walk_forward
        strategy_summary[key] = {
            "strategy": ev.strategy_name,
            "ticker": ev.ticker,
            "oos_sharpe": wf.avg_oos_sharpe if wf else 0,
            "pct_positive": wf.pct_positive_sharpe if wf else 0,
            "info_ratio": wf.avg_information_ratio if wf else 0,
            "passed": ev.overall_pass,
        }
    snapshot["strategy_summary"] = strategy_summary

    snapshot_path = _HISTORY_DIR / f"eval_{date_str}.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    logger.info("Snapshot saved to %s", snapshot_path)

    # Append to drift log (one line per day for easy parsing)
    drift_path = _HISTORY_DIR / "drift.jsonl"
    drift_entry = {
        "date": date_str,
        "total_evaluated": result.total_evaluated,
        "total_passed": result.total_passed,
        "top_sharpe": max(
            (ev.walk_forward.avg_oos_sharpe for ev in result.evaluations if ev.walk_forward),
            default=0,
        ),
        "avg_sharpe": sum(
            ev.walk_forward.avg_oos_sharpe for ev in result.evaluations if ev.walk_forward
        ) / max(result.total_evaluated, 1),
    }
    with open(drift_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(drift_entry, default=str) + "\n")

    return snapshot


def show_drift_history():
    """Print Sharpe drift over time."""
    drift_path = _HISTORY_DIR / "drift.jsonl"
    if not drift_path.exists():
        print("No drift history yet. Run `python eval/daily_eval.py` first.")
        return

    print(f"\n{'=' * 60}")
    print(f"  Orallexa — Sharpe Drift History")
    print(f"{'=' * 60}\n")
    print(f"  {'Date':<12} {'Pairs':<8} {'Passed':<8} {'Top Sharpe':<12} {'Avg Sharpe':<12}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*12} {'-'*12}")

    with open(drift_path, "r", encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            print(
                f"  {entry['date']:<12} "
                f"{entry['total_evaluated']:<8} "
                f"{entry['total_passed']:<8} "
                f"{entry['top_sharpe']:<12.3f} "
                f"{entry['avg_sharpe']:<12.3f}"
            )

    print(f"\n{'=' * 60}\n")


def main():
    parser = argparse.ArgumentParser(description="Orallexa Daily Evaluation Runner")
    parser.add_argument("--tickers", default=None, help="Comma-separated tickers (default: 10 major)")
    parser.add_argument("--history", action="store_true", help="Show Sharpe drift history")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

    if args.history:
        show_drift_history()
        return

    tickers = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else None
    run_daily_eval(tickers, seed=args.seed)


if __name__ == "__main__":
    main()
