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
import logging
import sys
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(
        description="Orallexa Evaluation Harness — walk-forward, Monte Carlo, statistical tests",
    )
    parser.add_argument(
        "--tickers", required=True,
        help="Comma-separated ticker symbols (e.g., NVDA,AAPL)",
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
        "--seed", type=int, default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--years", type=int, default=5,
        help="Years of historical data to fetch (default: 5)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

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

    num_strategies = len(STRATEGY_REGISTRY)
    total_tasks = len(tickers) * num_strategies

    print(f"\n{'=' * 60}")
    print(f"  Orallexa Evaluation Harness")
    print(f"  Tickers: {', '.join(tickers)}")
    print(f"  Strategies: {num_strategies}")
    print(f"  MC Iterations: {args.mc_iterations}")
    print(f"  Walk-Forward: {args.train_days}d train / {args.test_days}d test")
    print(f"{'=' * 60}\n")

    harness = EvaluationHarness(
        tickers=tickers,
        initial_train_days=args.train_days,
        test_days=args.test_days,
        mc_iterations=args.mc_iterations,
        mc_seed=args.seed,
        data_years=args.years,
    )

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

    # Generate report
    output_path = args.output or None
    report = generate_report(result, output_path=output_path)

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
    print(f"  Report: {output_path or 'docs/evaluation_report.md'}")
    print(f"  JSON: docs/evaluation_results.json")
    print(f"  Charts: docs/charts/")
    print(f"{'=' * 60}\n")

    # Exit code: 0 if at least one strategy passed, 1 if all failed or no data
    if result.total_evaluated == 0:
        print("Error: No tickers had sufficient data for evaluation.")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
