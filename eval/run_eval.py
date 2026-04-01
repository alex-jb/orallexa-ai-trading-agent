"""
eval/run_eval.py
──────────────────────────────────────────────────────────────────
CLI: Run decision quality evaluation.

Usage:
    python eval/run_eval.py --tickers NVDA --eval all
    python eval/run_eval.py --tickers NVDA --eval direction_accuracy --forward-days 5
    python eval/run_eval.py --tickers NVDA --eval consistency --runs 3
    python eval/run_eval.py --tickers NVDA,AAPL --eval backtest --days 60
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description="Oralexxa Decision Quality Evaluation")
    parser.add_argument("--tickers", required=True, help="Comma-separated tickers")
    parser.add_argument("--days", type=int, default=30, help="Look back N days in decision log")
    parser.add_argument("--forward-days", type=int, default=5, help="Forward return window for accuracy")
    parser.add_argument("--eval", default="all",
                        choices=["direction_accuracy", "calibration", "consistency", "backtest", "all"])
    parser.add_argument("--runs", type=int, default=3, help="Number of runs for consistency check")
    parser.add_argument("--output", default=None, help="Save results JSON")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    results = {}

    print(f"\n{'='*60}")
    print(f"  Oralexxa Decision Quality Evaluation")
    print(f"  Tickers: {', '.join(tickers)}")
    print(f"  Eval: {args.eval}")
    print(f"{'='*60}\n")

    from eval.decision_eval import (
        direction_accuracy,
        confidence_calibration,
        explanation_consistency,
        strategy_backtest_eval,
    )

    # 1. Direction Accuracy
    if args.eval in ("direction_accuracy", "calibration", "all"):
        print("── Direction Accuracy ──")
        acc = direction_accuracy(forward_days=args.forward_days, days=args.days)
        results["direction_accuracy"] = acc
        print(f"  Accuracy: {acc['accuracy']:.1%} ({acc['correct']}/{acc['total']})")
        print(f"  Forward window: {acc['forward_days']} days")
        if acc["details"]:
            for d in acc["details"][:5]:
                mark = "+" if d["correct"] else "x"
                print(f"    [{mark}] {d['ticker']} {d['decision']} → {d['forward_return']:+.2%} (conf: {d['confidence']:.0f}%)")
        print()

    # 2. Confidence Calibration
    if args.eval in ("calibration", "all"):
        print("── Confidence Calibration ──")
        cal = confidence_calibration(
            evaluated_decisions=results.get("direction_accuracy", {}).get("details"),
            forward_days=args.forward_days, days=args.days,
        )
        results["calibration"] = cal
        for b in cal["buckets"]:
            acc_str = f"{b['accuracy']:.1%}" if b["accuracy"] is not None else "N/A"
            ret_str = f"{b['avg_return']:+.2%}" if b["avg_return"] is not None else "N/A"
            print(f"  [{b['range']}%] n={b['count']:>3}  accuracy={acc_str}  avg_return={ret_str}")
        print()

    # 3. Explanation Consistency
    if args.eval in ("consistency", "all"):
        print("── Explanation Consistency ──")
        for ticker in tickers:
            print(f"  {ticker}:")
            cons = explanation_consistency(ticker, n_runs=args.runs)
            results[f"consistency_{ticker}"] = cons
            print(f"    Agreement: {cons['agreement_rate']:.0%}")
            print(f"    Decisions: {cons['decisions']}")
            print(f"    Confidence std: {cons['confidence_std']:.1f}")
            print(f"    Most common: {cons['most_common_decision']}")
        print()

    # 4. Strategy Backtest
    if args.eval in ("backtest", "all"):
        print("── Strategy Backtest ──")
        bt = strategy_backtest_eval(days=args.days)
        results["backtest"] = bt
        for ticker, data in bt.get("by_ticker", {}).items():
            if "error" in data:
                print(f"  {ticker}: ERROR — {data['error']}")
            else:
                print(f"  {ticker}: strategy={data['strategy_return']:+.2%} "
                      f"B&H={data['buy_hold_return']:+.2%} "
                      f"alpha={data['alpha']:+.2%} "
                      f"sharpe={data['sharpe']:.2f}")
        print()

    print(f"{'='*60}")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
