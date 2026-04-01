"""
eval/run_experiment.py
──────────────────────────────────────────────────────────────────
CLI: Run comparative experiments across model configurations.

Usage:
    python eval/run_experiment.py --tickers NVDA,AAPL
    python eval/run_experiment.py --tickers NVDA --configs all_fast,dual_tier
    python eval/run_experiment.py --tickers NVDA,AAPL,MSFT --output results.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.experiment import ModelConfig, run_experiment_matrix, compare_results


def main():
    parser = argparse.ArgumentParser(description="Oralexxa Model Comparison Experiment")
    parser.add_argument("--tickers", required=True, help="Comma-separated tickers (e.g. NVDA,AAPL)")
    parser.add_argument("--configs", default="all_fast,all_deep,dual_tier",
                        help="Comma-separated configs: all_fast, all_deep, dual_tier")
    parser.add_argument("--output", default=None, help="Save results JSON to this path")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    config_map = {c.value: c for c in ModelConfig}
    configs = [config_map[c.strip()] for c in args.configs.split(",") if c.strip() in config_map]

    if not configs:
        print("No valid configs. Use: all_fast, all_deep, dual_tier")
        return

    print(f"\n{'='*60}")
    print(f"  Oralexxa Model Comparison Experiment")
    print(f"  Tickers: {', '.join(tickers)}")
    print(f"  Configs: {', '.join(c.value for c in configs)}")
    print(f"{'='*60}\n")

    results = run_experiment_matrix(tickers, configs)

    print(f"\n{'='*60}")
    print(compare_results(results))
    print(f"{'='*60}\n")

    if args.output:
        from dataclasses import asdict
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in results], f, indent=2)
        print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
