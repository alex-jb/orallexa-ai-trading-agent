"""
scripts/build_multimodal_eval_set.py
──────────────────────────────────────────────────────────────────
Multimodal debate evaluation — Day 7. Mirrors build_dspy_eval_set.py.

Reads memory_data/decision_log.json, pulls every record that has the
text-vs-vision diff stashed at extra.multimodal_diff (added in commit
7d63c25), attaches the eventual N-day forward return, and labels each
pair (text_decision, vision_decision, ground_truth).

Output is JSONL at memory_data/multimodal_eval_set.jsonl, one line per
(role, ticker, timestamp) pair. The companion script
eval_multimodal_lift.py consumes this file and reports whether vision
beats text on agreement-with-ground-truth.

Synthetic mode (--synthesize N) emits N rows with deterministic
forward labels so the lift evaluator can be smoke-tested without
waiting for production data.

Usage:
    python scripts/build_multimodal_eval_set.py                # 5d window
    python scripts/build_multimodal_eval_set.py --days 3
    python scripts/build_multimodal_eval_set.py --synthesize 200
    python scripts/build_multimodal_eval_set.py --dry-run      # count only
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# Reuse the same forward-return + ground-truth helpers as DSPy Phase B —
# the labelling rule is identical (±2% threshold over N trading days).
from scripts.build_dspy_eval_set import (
    _forward_return,
    _ground_truth,
    _parse_iso,
)

_DECISION_LOG = _ROOT / "memory_data" / "decision_log.json"
_DEFAULT_OUTPUT = _ROOT / "memory_data" / "multimodal_eval_set.jsonl"


def _bias_to_decision(bias: str) -> str:
    """Map BULLISH/BEARISH/NEUTRAL → BUY/SELL/WAIT for ground-truth comparison."""
    bias = (bias or "").upper()
    if bias == "BULLISH":
        return "BUY"
    if bias == "BEARISH":
        return "SELL"
    return "WAIT"


def synthesize_eval_set(n: int, seed: int = 42) -> list[dict]:
    """
    Build N synthetic (text_bias, vision_bias, ground_truth) pairs.

    Distribution: ~40% pairs where vision agrees with text and both match
    truth, ~30% where they disagree and vision is correct, ~30% where they
    disagree and text is correct. This way the lift evaluator should report
    ~50/50 baseline agreement and a measurable but ambiguous vision lift —
    which is exactly the regime we'd want the harness to handle gracefully.
    """
    import random

    rng = random.Random(seed)
    biases = ["BULLISH", "BEARISH", "NEUTRAL"]
    tickers = ["NVDA", "AAPL", "MSFT", "TSLA", "META", "AMD", "GOOG"]

    rows = []
    for i in range(n):
        roll = rng.random()
        if roll < 0.40:
            # Both agree, both correct
            truth_bias = rng.choice(biases)
            text_bias = vision_bias = truth_bias
            forward_return = (
                0.04 if truth_bias == "BULLISH"
                else -0.04 if truth_bias == "BEARISH"
                else 0.005
            )
        elif roll < 0.70:
            # Disagree, vision correct
            truth_bias = rng.choice(biases)
            vision_bias = truth_bias
            text_bias = rng.choice([b for b in biases if b != truth_bias])
            forward_return = (
                0.04 if truth_bias == "BULLISH"
                else -0.04 if truth_bias == "BEARISH"
                else 0.005
            )
        else:
            # Disagree, text correct
            truth_bias = rng.choice(biases)
            text_bias = truth_bias
            vision_bias = rng.choice([b for b in biases if b != truth_bias])
            forward_return = (
                0.04 if truth_bias == "BULLISH"
                else -0.04 if truth_bias == "BEARISH"
                else 0.005
            )

        rows.append({
            "ticker": tickers[rng.randrange(len(tickers))],
            "timestamp": None,
            "role": "Quant Researcher",
            "text_bias": text_bias,
            "text_score": rng.randint(-80, 80),
            "text_conviction": rng.randint(40, 80),
            "vision_bias": vision_bias,
            "vision_score": rng.randint(-80, 80),
            "vision_conviction": rng.randint(40, 80),
            "forward_return": round(forward_return, 4),
            "ground_truth": _ground_truth(forward_return),
            "eligible": True,
            "synthetic": True,
        })
    return rows


def extract_pairs_from_log(records: list[dict], cutoff: datetime) -> list[dict]:
    """Pull every (role, ticker, timestamp) text-vs-vision pair from the log."""
    pairs = []
    for r in records:
        extra = r.get("extra") or {}
        if not isinstance(extra, dict):
            continue
        diff = extra.get("multimodal_diff")
        if not isinstance(diff, dict):
            continue
        ts = _parse_iso(r.get("timestamp", ""))
        if ts is None or ts > cutoff:
            continue
        ticker = r.get("ticker", "")
        for pair in diff.get("pairs", []):
            text = pair.get("text") or {}
            vision = pair.get("vision") or {}
            if not text or not vision:
                continue
            pairs.append({
                "ticker": ticker,
                "timestamp": r.get("timestamp"),
                "role": pair.get("role", "?"),
                "text_bias": text.get("bias"),
                "text_score": text.get("score"),
                "text_conviction": text.get("conviction"),
                "vision_bias": vision.get("bias"),
                "vision_score": vision.get("score"),
                "vision_conviction": vision.get("conviction"),
                "_ts": ts,
            })
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=5,
                        help="forward window in trading days")
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true",
                        help="count eligible pairs without writing")
    parser.add_argument("--threshold", type=float, default=0.02,
                        help="±return threshold for direction labelling")
    parser.add_argument("--synthesize", type=int, default=0,
                        help="emit N synthetic pairs instead of reading the log")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed for synthetic mode")
    args = parser.parse_args()

    if args.synthesize > 0:
        rows = synthesize_eval_set(args.synthesize, seed=args.seed)
        out_lines = [json.dumps(r, ensure_ascii=False) for r in rows]
        gt_counts = {gt: sum(1 for r in rows if r["ground_truth"] == gt)
                     for gt in ("BUY", "SELL", "WAIT")}
        print(f"Synthesized {len(rows)} pairs (seed={args.seed})")
        print(f"  ground_truth distribution: {gt_counts}")
        if args.dry_run:
            print(f"--dry-run: would have written {len(out_lines)} lines to {args.output}")
            return 0
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        print(f"Wrote {len(out_lines)} synthetic lines to {args.output}")
        return 0

    if not _DECISION_LOG.exists():
        print(f"Decision log not found at {_DECISION_LOG}")
        return 1

    raw = json.loads(_DECISION_LOG.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print("Decision log is not a list — schema mismatch.")
        return 1

    print(f"Loaded {len(raw)} decision records")

    cutoff = datetime.now() - timedelta(days=args.days + 1)
    candidates = extract_pairs_from_log(raw, cutoff)
    print(f"Pairs with multimodal stash + eligible age: {len(candidates)}")

    eligible_count = 0
    skipped_count = 0
    out_lines: list[str] = []

    for c in candidates:
        ret = _forward_return(c["ticker"], c["_ts"], days=args.days)
        if ret is None:
            skipped_count += 1
            entry = {
                **{k: v for k, v in c.items() if k != "_ts"},
                "forward_return": None,
                "ground_truth": None,
                "eligible": False,
                "reason": "forward_return_unavailable",
            }
        else:
            eligible_count += 1
            entry = {
                **{k: v for k, v in c.items() if k != "_ts"},
                "forward_return": round(ret, 4),
                "ground_truth": _ground_truth(ret, threshold=args.threshold),
                "eligible": True,
            }
        out_lines.append(json.dumps(entry, ensure_ascii=False))

    print()
    print(f"Eligible pairs (with forward data): {eligible_count}")
    print(f"Skipped (no forward data):           {skipped_count}")

    if eligible_count >= 50:
        print(f"\nPhase B-style threshold met (>=50 pairs). Run eval_multimodal_lift.py.")
    else:
        print(f"\n  Need {50 - eligible_count} more eligible pairs before lift eval is meaningful.")

    if args.dry_run:
        print(f"\n--dry-run: would have written {len(out_lines)} lines to {args.output}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"\nWrote {len(out_lines)} lines to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
