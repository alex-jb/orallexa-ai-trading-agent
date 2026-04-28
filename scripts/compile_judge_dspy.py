"""
scripts/compile_judge_dspy.py
──────────────────────────────────────────────────────────────────
DSPy Phase B compile harness.

Pipeline:
  1. Load eval set (JSONL produced by build_dspy_eval_set.py — either
     real or --synthesize).
  2. Filter to rows with eligible=True and a non-empty ground_truth.
  3. Deterministic 80/20 train/holdout split (seeded).
  4. Run MIPROv2 with the judge_metric defined in build_dspy_eval_set.
  5. Save the compiled program to memory_data/dspy_judge_compiled.json.
  6. Evaluate baseline (uncompiled JudgeSignature) vs compiled on the
     holdout. Print decision-agreement, per-class accuracy, confidence
     calibration delta, and whether the >5% gate from
     docs/DSPY_MIGRATION.md is cleared.

`dspy-ai` is lazy-imported. Without it, the harness exits 0 with a
clear message — CI can run this script and only `pip install dspy-ai`
+ set ANTHROPIC_API_KEY when it actually wants to compile. The shape
of the output (`Phase B status: ...` line) is stable so cron / future
orchestration can grep for it.

Usage:
    python scripts/compile_judge_dspy.py                  # default paths
    python scripts/compile_judge_dspy.py --eval-set /tmp/x.jsonl
    python scripts/compile_judge_dspy.py --auto light     # cheaper compile
    python scripts/compile_judge_dspy.py --dry-run        # split + report only
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path
from typing import Iterable, Optional

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_DEFAULT_EVAL = _ROOT / "memory_data" / "dspy_eval_set.jsonl"
_DEFAULT_OUTPUT = _ROOT / "memory_data" / "dspy_judge_compiled.json"

logger = logging.getLogger(__name__)


def load_eval_set(path: Path) -> list[dict]:
    """Read JSONL (one row per line). Skip blank lines and malformed rows."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def filter_eligible(rows: Iterable[dict]) -> list[dict]:
    return [
        r for r in rows
        if r.get("eligible") and r.get("ground_truth") in ("BUY", "SELL", "WAIT")
        and r.get("bull_argument") and r.get("bear_argument")
    ]


def split_train_holdout(
    rows: list[dict], holdout_frac: float = 0.20, seed: int = 42
) -> tuple[list[dict], list[dict]]:
    """Deterministic shuffle + split. We don't stratify — Phase B is small enough."""
    rng = random.Random(seed)
    shuffled = list(rows)
    rng.shuffle(shuffled)
    cut = int(len(shuffled) * (1 - holdout_frac))
    return shuffled[:cut], shuffled[cut:]


def class_distribution(rows: list[dict]) -> dict[str, int]:
    return {gt: sum(1 for r in rows if r.get("ground_truth") == gt) for gt in ("BUY", "SELL", "WAIT")}


def evaluate_predictor(
    predictor, rows: list[dict], *, label: str = "predictor"
) -> dict:
    """
    Run a callable predictor over rows and return aggregate metrics.

    `predictor` must accept (ticker, bull, bear) and return a dict with at
    least a 'decision' field. None return = abstain (counted as miss).
    """
    n_correct = 0
    n_total = 0
    per_class_correct = {gt: 0 for gt in ("BUY", "SELL", "WAIT")}
    per_class_total = {gt: 0 for gt in ("BUY", "SELL", "WAIT")}
    confidence_deltas: list[float] = []

    for row in rows:
        truth = row["ground_truth"]
        per_class_total[truth] += 1
        n_total += 1

        try:
            out = predictor(
                ticker=row.get("ticker", "UNKNOWN"),
                bull=row["bull_argument"],
                bear=row["bear_argument"],
            )
        except Exception as e:
            logger.warning("%s failed on row %s: %s", label, row.get("ticker"), e)
            continue

        if not out or not isinstance(out, dict):
            continue
        decision = str(out.get("decision", "")).upper()
        if decision == truth:
            n_correct += 1
            per_class_correct[truth] += 1
        if "confidence" in out and row.get("hand_confidence") is not None:
            try:
                confidence_deltas.append(float(out["confidence"]) - float(row["hand_confidence"]))
            except (TypeError, ValueError):
                pass

    accuracy = n_correct / n_total if n_total else 0.0
    per_class_acc = {
        gt: (per_class_correct[gt] / per_class_total[gt] if per_class_total[gt] else 0.0)
        for gt in per_class_total
    }
    return {
        "label":              label,
        "n":                  n_total,
        "accuracy":           round(accuracy, 4),
        "per_class_accuracy": {gt: round(v, 4) for gt, v in per_class_acc.items()},
        "per_class_n":        per_class_total,
        "mean_conf_delta":    (
            round(sum(confidence_deltas) / len(confidence_deltas), 2)
            if confidence_deltas else None
        ),
    }


def _make_baseline_predictor():
    """Wrap llm.dspy_judge.judge_dspy as the baseline (uncompiled JudgeSignature)."""
    from llm.dspy_judge import judge_dspy

    def predict(ticker, bull, bear):
        return judge_dspy(bull, bear, ticker=ticker)

    return predict


def _make_compiled_predictor(compiled_program):
    """Wrap a compiled dspy program into the (ticker, bull, bear) → dict shape."""
    def predict(ticker, bull, bear):
        out = compiled_program(ticker=ticker, bull_argument=bull, bear_argument=bear)
        decision = str(getattr(out, "decision", "WAIT")).upper().strip()
        if decision not in ("BUY", "SELL", "WAIT"):
            decision = "WAIT"
        try:
            confidence = max(0, min(100, int(float(getattr(out, "confidence", 50)))))
        except (TypeError, ValueError):
            confidence = 50
        return {
            "decision":   decision,
            "confidence": confidence,
            "source":     "dspy_compiled",
        }

    return predict


def run_compile(
    eval_path: Path,
    output_path: Path,
    *,
    auto: str = "medium",
    seed: int = 42,
    dry_run: bool = False,
) -> dict:
    """End-to-end harness. Returns a structured report dict."""
    rows = filter_eligible(load_eval_set(eval_path))
    train, holdout = split_train_holdout(rows, seed=seed)

    report: dict = {
        "eval_path":          str(eval_path),
        "n_total_eligible":   len(rows),
        "n_train":            len(train),
        "n_holdout":          len(holdout),
        "train_distribution": class_distribution(train),
        "holdout_distribution": class_distribution(holdout),
        "phase_b_threshold":  100,
        "phase_b_ready":      len(rows) >= 100,
    }

    if not rows:
        report["status"] = "no_eval_data"
        return report
    if not report["phase_b_ready"]:
        report["status"] = "below_threshold"
        return report
    if dry_run:
        report["status"] = "dry_run"
        return report

    try:
        import dspy  # noqa: F401
    except ImportError:
        report["status"] = "dspy_not_installed"
        return report

    from llm.dspy_judge import _ensure_dspy
    from scripts.build_dspy_eval_set import judge_metric

    base_predict_cls = _ensure_dspy()
    JudgeSignature = base_predict_cls.signature

    train_examples = [
        dspy.Example(
            ticker=r.get("ticker", "UNKNOWN"),
            bull_argument=r["bull_argument"],
            bear_argument=r["bear_argument"],
            ground_truth=r["ground_truth"],
        ).with_inputs("ticker", "bull_argument", "bear_argument")
        for r in train
    ]

    optimizer = dspy.MIPROv2(metric=judge_metric, auto=auto)
    compiled = optimizer.compile(
        dspy.Predict(JudgeSignature),
        trainset=train_examples,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    compiled.save(str(output_path))
    report["compiled_artifact"] = str(output_path)

    baseline_eval = evaluate_predictor(_make_baseline_predictor(), holdout, label="baseline")
    compiled_eval = evaluate_predictor(_make_compiled_predictor(compiled), holdout, label="compiled")
    delta = compiled_eval["accuracy"] - baseline_eval["accuracy"]

    report.update({
        "baseline":           baseline_eval,
        "compiled":           compiled_eval,
        "absolute_delta":     round(delta, 4),
        "ship_threshold":     0.05,
        "should_ship":        delta >= 0.05,
        "status":             "compiled",
    })
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, default=_DEFAULT_EVAL)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--auto", default="medium",
                        choices=["light", "medium", "heavy"],
                        help="MIPROv2 auto-tuning preset")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true",
                        help="report eval-set readiness without compiling")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    report = run_compile(
        args.eval_set, args.output,
        auto=args.auto, seed=args.seed, dry_run=args.dry_run,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nPhase B status: {report.get('status')}")
    if report.get("status") == "compiled":
        verdict = "SHIP" if report["should_ship"] else "REJECT (below 5% gate)"
        print(
            f"  baseline={report['baseline']['accuracy']:.3f} "
            f"compiled={report['compiled']['accuracy']:.3f} "
            f"delta={report['absolute_delta']:+.3f} → {verdict}"
        )


if __name__ == "__main__":
    main()
