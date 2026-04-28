"""
scripts/eval_multimodal_lift.py
──────────────────────────────────────────────────────────────────
Day 7 lift evaluator. Consumes the JSONL produced by
build_multimodal_eval_set.py and reports whether the vision modality
predicts forward outcomes better than the text-only modality.

Three numbers drive the ship/reject decision:

  text_accuracy   : fraction of pairs where text_bias → ground_truth
  vision_accuracy : fraction of pairs where vision_bias → ground_truth
  absolute_lift   : vision_accuracy - text_accuracy

Ship gate (default): absolute_lift >= 0.05 AND vision_accuracy > text_accuracy
on at least 50 pairs.

Stable status field for cron / CI / future automation:
  no_eval_data | below_threshold | dry_run | reject_no_lift |
  reject_text_better | ship

Usage:
    python scripts/eval_multimodal_lift.py
    python scripts/eval_multimodal_lift.py --eval-set /tmp/x.jsonl
    python scripts/eval_multimodal_lift.py --threshold 0.03  # 3% gate
    python scripts/eval_multimodal_lift.py --dry-run         # report only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_DEFAULT_EVAL = _ROOT / "memory_data" / "multimodal_eval_set.jsonl"


def load_eval_set(path: Path) -> list[dict]:
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


def filter_eligible(rows: list[dict]) -> list[dict]:
    valid_truths = {"BUY", "SELL", "WAIT"}
    return [
        r for r in rows
        if r.get("eligible")
        and r.get("ground_truth") in valid_truths
        and r.get("text_bias") and r.get("vision_bias")
    ]


def _bias_to_decision(bias: str) -> str:
    bias = (bias or "").upper()
    if bias == "BULLISH":
        return "BUY"
    if bias == "BEARISH":
        return "SELL"
    return "WAIT"


def evaluate(rows: list[dict]) -> dict:
    """Compute per-modality accuracy + lift + per-class breakdown."""
    if not rows:
        return {
            "n": 0,
            "text_accuracy": 0.0, "vision_accuracy": 0.0,
            "absolute_lift": 0.0,
            "agreement_rate": 0.0,
            "per_class": {},
        }

    text_correct = 0
    vision_correct = 0
    both_agree = 0
    per_class_total = {gt: 0 for gt in ("BUY", "SELL", "WAIT")}
    per_class_text = {gt: 0 for gt in ("BUY", "SELL", "WAIT")}
    per_class_vision = {gt: 0 for gt in ("BUY", "SELL", "WAIT")}

    for r in rows:
        truth = r["ground_truth"]
        text_dec = _bias_to_decision(r["text_bias"])
        vision_dec = _bias_to_decision(r["vision_bias"])

        per_class_total[truth] += 1
        if text_dec == truth:
            text_correct += 1
            per_class_text[truth] += 1
        if vision_dec == truth:
            vision_correct += 1
            per_class_vision[truth] += 1
        if text_dec == vision_dec:
            both_agree += 1

    n = len(rows)
    text_acc = text_correct / n
    vision_acc = vision_correct / n

    per_class = {}
    for gt in per_class_total:
        if per_class_total[gt] > 0:
            per_class[gt] = {
                "n": per_class_total[gt],
                "text_accuracy": round(per_class_text[gt] / per_class_total[gt], 3),
                "vision_accuracy": round(per_class_vision[gt] / per_class_total[gt], 3),
            }
        else:
            per_class[gt] = {"n": 0, "text_accuracy": 0.0, "vision_accuracy": 0.0}

    return {
        "n": n,
        "text_accuracy": round(text_acc, 4),
        "vision_accuracy": round(vision_acc, 4),
        "absolute_lift": round(vision_acc - text_acc, 4),
        "agreement_rate": round(both_agree / n, 4),
        "per_class": per_class,
    }


def decide(metrics: dict, *, ship_threshold: float, min_n: int) -> str:
    """Return the verdict string used by the status line."""
    if metrics["n"] == 0:
        return "no_eval_data"
    if metrics["n"] < min_n:
        return "below_threshold"
    if metrics["absolute_lift"] < 0:
        return "reject_text_better"
    if metrics["absolute_lift"] < ship_threshold:
        return "reject_no_lift"
    return "ship"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, default=_DEFAULT_EVAL)
    parser.add_argument("--threshold", type=float, default=0.05,
                        help="absolute lift required to ship vision (default 5%)")
    parser.add_argument("--min-n", type=int, default=50,
                        help="minimum eligible pairs before verdict is meaningful")
    parser.add_argument("--dry-run", action="store_true",
                        help="report metrics without printing the ship verdict")
    args = parser.parse_args()

    rows = filter_eligible(load_eval_set(args.eval_set))
    metrics = evaluate(rows)
    verdict = decide(metrics, ship_threshold=args.threshold, min_n=args.min_n)

    report = {
        "eval_path": str(args.eval_set),
        "n_total_eligible": metrics["n"],
        "ship_threshold": args.threshold,
        "min_n_required": args.min_n,
        **metrics,
        "status": "dry_run" if args.dry_run else verdict,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if not args.dry_run:
        print(f"\nMultimodal lift status: {verdict}")
        if verdict == "ship":
            print(f"  vision={metrics['vision_accuracy']:.3f} "
                  f"text={metrics['text_accuracy']:.3f} "
                  f"lift={metrics['absolute_lift']:+.3f} -> SHIP")
        elif verdict in {"reject_no_lift", "reject_text_better"}:
            print(f"  vision={metrics['vision_accuracy']:.3f} "
                  f"text={metrics['text_accuracy']:.3f} "
                  f"lift={metrics['absolute_lift']:+.3f} -> KEEP TEXT-ONLY")

    return 0


if __name__ == "__main__":
    sys.exit(main())
