"""
eval/run_harness.py
--------------------------------------------------------------------
CLI entry point for the Orallexa evaluation harness.

Usage:
    python eval/run_harness.py --tickers NVDA,AAPL
    python eval/run_harness.py --tickers NVDA --mc-iterations 5000
    python eval/run_harness.py --tickers NVDA,AAPL,TSLA --output results/eval.md
"""
from __future__ import annotations

import argparse
import json
import re
import logging
import sys
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DECLARED_90_STRATEGIES = (
    "double_ma", "macd_crossover", "bollinger_breakout", "rsi_reversal",
    "trend_momentum", "alpha_combo", "dual_thrust", "ensemble_vote", "regime_ensemble",
)


def main():
    parser = argparse.ArgumentParser(
        description="Orallexa Evaluation Harness — walk-forward, Monte Carlo, statistical tests",
    )
    parser.add_argument(
        "--tickers", required=True,
        help="Comma-separated ticker symbols (e.g., NVDA,AAPL)",
    )
    parser.add_argument(
        "--strategies", default=None,
        help="Comma-separated predeclared strategies (default: all registered strategies)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output path for markdown report (default: docs/evaluation_report.md)",
    )
    parser.add_argument(
        "--mc-iterations", type=int, default=1000,
        help="Monte Carlo iterations (default: 1000)",
    )
    parser.add_argument(
        "--train-days", type=int, default=252,
        help="Initial training window in days (default: 252)",
    )
    parser.add_argument(
        "--test-days", type=int, default=63,
        help="Test window in days (default: 63)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for bootstrap and Monte Carlo (default: 42)",
    )
    parser.add_argument(
        "--data-dir", default=None,
        help="Directory of pinned TICKER.csv OHLCV snapshots (Date,Open,High,Low,Close,Volume)",
    )
    parser.add_argument(
        "--years", type=int, default=5,
        help="Years of historical data to fetch (default: 5)",
    )
    parser.add_argument(
        "--no-adaptive", action="store_true",
        help="Disable adaptive parameter optimization (use fixed default params)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    data_path = Path(args.data_dir) if args.data_dir else None
    if data_path:
        from eval.freeze_alpaca_data import PROTOCOL_IDS, TICKERS, START, END_INCLUSIVE

        requested_tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        requested_strategies = ([s.strip() for s in args.strategies.split(",") if s.strip()]
                                if args.strategies else [])
        if (requested_tickers != list(TICKERS)
                or requested_strategies != list(DECLARED_90_STRATEGIES)
                or args.train_days != 252 or args.test_days != 63
                or args.seed != 42 or args.mc_iterations != 1000
                or not args.no_adaptive):
            parser.error("Pinned evaluation must match the declared 90-pair protocol: "
                         "ten tickers, nine strategies in protocol order, 252/63 windows, "
                         "seed 42, 1000 Monte Carlo iterations, and --no-adaptive")
    manifest_path = data_path / "manifest.json" if data_path else None
    if data_path and not manifest_path.is_file():
        parser.error("Pinned evaluation requires the freeze manifest with per-ticker hashes")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path and manifest_path.is_file() else {}
    except (OSError, ValueError) as exc:
        parser.error(f"Invalid snapshot manifest: {exc}")
    if data_path:
        if not isinstance(manifest, dict):
            parser.error("Snapshot manifest must be a JSON object")
        hashes = manifest.get("sha256")
        if (manifest.get("tickers") != list(TICKERS)
                or not isinstance(hashes, dict) or set(hashes) != set(TICKERS)
                or any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
                       for value in hashes.values())):
            parser.error("Snapshot manifest must declare all ten tickers and their SHA-256 hashes")
        protocol = manifest.get("protocol_id")
        if protocol in PROTOCOL_IDS.values():
            params = manifest.get("parameters", {})
            feed = params.get("feed") if isinstance(params, dict) else None
            if (manifest.get("source") != "Alpaca Historical Stock Bars GET API"
                    or feed not in PROTOCOL_IDS or protocol != PROTOCOL_IDS[feed]
                    or params.get("adjustment") != "split,dividend"
                    or params.get("start") != START or params.get("last_session_required") != END_INCLUSIVE):
                parser.error("Alpaca manifest does not match the declared cohort")
        elif (manifest.get("source") != "yfinance download, auto_adjust=True"
              or manifest.get("start") != START or manifest.get("end_exclusive") != "2026-09-29"):
            parser.error("Unknown or mismatched snapshot protocol")
    output_path = Path(args.output) if args.output else (
        data_path / "evaluation_report.md" if data_path else Path("results/unpinned/evaluation_report.md")
    )
    repo = Path(__file__).resolve().parents[1]
    resolved = output_path.resolve()
    ignored_roots = [repo / "eval/snapshots", repo / "eval/private_snapshots", repo / "results"]
    if resolved.is_relative_to(repo) and not any(resolved.is_relative_to(root) for root in ignored_roots):
        parser.error("Numerical evaluation output must stay outside tracked repo paths")

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        print("Error: No valid tickers provided.")
        sys.exit(1)

    # Progress bar
    try:
        from tqdm import tqdm
        has_tqdm = True
    except ImportError:
        has_tqdm = False

    from eval.harness import EvaluationHarness
    from eval.report_generator import generate_report
    from engine.strategies import STRATEGY_REGISTRY

    strategies = ([s.strip() for s in args.strategies.split(",") if s.strip()]
                  if args.strategies else list(STRATEGY_REGISTRY))
    num_strategies = len(strategies)
    total_tasks = len(tickers) * num_strategies

    print(f"\n{'=' * 60}")
    print(f"  Orallexa Evaluation Harness")
    print(f"  Tickers: {', '.join(tickers)}")
    print(f"  Strategies: {num_strategies}")
    print(f"  MC Iterations: {args.mc_iterations}")
    adaptive = not args.no_adaptive
    print(f"  Walk-Forward: {args.train_days}d train / {args.test_days}d test")
    print(f"  Adaptive Params: {'ON' if adaptive else 'OFF'}")
    print(f"{'=' * 60}\n")

    harness = EvaluationHarness(
        tickers=tickers,
        initial_train_days=args.train_days,
        test_days=args.test_days,
        mc_iterations=args.mc_iterations,
        mc_seed=args.seed,
        data_years=args.years,
        data_dir=args.data_dir,
        strategies=strategies,
    )
    harness.adaptive = adaptive

    # Run with progress bar
    if has_tqdm:
        pbar = tqdm(total=total_tasks, desc="Evaluating", unit="strategy")
        result = harness.run(progress_callback=lambda: pbar.update(1))
        pbar.close()
    else:
        completed = [0]
        def _progress():
            completed[0] += 1
            print(f"  [{completed[0]}/{total_tasks}] evaluating...", end="\r")
        result = harness.run(progress_callback=_progress)
        print()

    # An exception in a strategy or statistical calculation must not leave
    # numerical artifacts in the tracked docs directory as a 'complete' run.
    if result.total_evaluated != total_tasks:
        print(f"Incomplete evaluation: {result.total_evaluated}/{total_tasks} pairs have valid OOS calculations. "
              "No report was written; do not publish performance claims from this run.")
        sys.exit(2)

    # Generate report
    generate_report(result, output_path=output_path, generate_charts=False)

    # Summary
    verdicts = [e.verdict for e in result.evaluations]
    print(f"\n{'=' * 60}")
    print(f"  RESULTS")
    print(f"  Evaluated: {result.total_evaluated} strategy-ticker pairs")
    print(f"  STRONG PASS: {verdicts.count('STRONG PASS')} | "
          f"PASS: {verdicts.count('PASS')} | "
          f"MARGINAL: {verdicts.count('MARGINAL')} | "
          f"FAIL: {verdicts.count('FAIL')}")
    if result.skipped_tickers:
        print(f"  Skipped tickers: {', '.join(result.skipped_tickers)} (insufficient data)")
    print(f"  Report: {output_path}")
    print(f"  JSON: {output_path.parent / 'evaluation_results.json'}")
    family_label = "predeclared" if data_path else "exploratory"
    print(f"  Family: {len(tickers) * num_strategies} {family_label} pairs "
          "(missing pairs remain N/A)")
    print("  Charts: disabled for this evaluation run")
    print(f"{'=' * 60}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
