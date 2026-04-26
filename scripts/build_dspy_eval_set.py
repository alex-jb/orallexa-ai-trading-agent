"""
scripts/build_dspy_eval_set.py
──────────────────────────────────────────────────────────────────
Phase B prep: extract a (Bull, Bear, ground_truth) eval set from
memory_data/decision_log.json so MIPROv2 can compile a Judge that
agrees with the eventual N-day market outcome more often than the
hand-tuned baseline.

Pipeline:
  1. Read decision_log entries that have `extra.debate` populated
     (added in commit "feat: stash debate text on decision.extra
     for DSPy Phase B").
  2. For each, pull the forward N-day return via yfinance.
  3. Convert (return → ground_truth direction) using a ±2% threshold:
        return > +2%  → BUY
        return < -2%  → SELL
        otherwise     → WAIT
  4. Emit a JSONL file at memory_data/dspy_eval_set.jsonl with one
     line per eligible record:
       {ticker, bull_argument, bear_argument, hand_decision,
        forward_return, ground_truth, eligible}
     Records where forward data is unavailable are written with
     eligible=false so we can audit later without losing them.

Phase B trigger condition (per docs/DSPY_MIGRATION.md):
  - ≥100 eligible records before running MIPROv2
  - 80/20 train/holdout split
  - Compiled prompt must score >5% absolute improvement on holdout
    against the hand-tuned baseline (decision agreement metric)

Usage:
    python scripts/build_dspy_eval_set.py                    # 5-day window
    python scripts/build_dspy_eval_set.py --days 3
    python scripts/build_dspy_eval_set.py --output /tmp/x.jsonl
    python scripts/build_dspy_eval_set.py --dry-run          # count only
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

_DECISION_LOG = _ROOT / "memory_data" / "decision_log.json"
_DEFAULT_OUTPUT = _ROOT / "memory_data" / "dspy_eval_set.jsonl"


def _parse_iso(s: str) -> Optional[datetime]:
    try:
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _forward_return(ticker: str, ts: datetime, days: int) -> Optional[float]:
    """Closing price at ts → closing price `days` trading days later."""
    try:
        import yfinance as yf
        start = (ts - timedelta(days=2)).strftime("%Y-%m-%d")
        end = (ts + timedelta(days=days + 7)).strftime("%Y-%m-%d")
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
        if hist.empty:
            return None
        ts_naive = ts.replace(tzinfo=None) if ts.tzinfo else ts
        idx = hist.index.tz_localize(None) if hist.index.tz else hist.index
        on_or_after = [i for i, d in enumerate(idx) if d >= ts_naive]
        if not on_or_after:
            return None
        i0 = on_or_after[0]
        i1 = i0 + days
        if i1 >= len(hist):
            return None
        p0 = float(hist["Close"].iloc[i0])
        p1 = float(hist["Close"].iloc[i1])
        if p0 <= 0:
            return None
        return (p1 - p0) / p0
    except Exception:
        return None


def _ground_truth(forward_return: float, threshold: float = 0.02) -> str:
    if forward_return > threshold:
        return "BUY"
    if forward_return < -threshold:
        return "SELL"
    return "WAIT"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=5,
                        help="forward window in trading days")
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true",
                        help="count eligible records without writing")
    parser.add_argument("--threshold", type=float, default=0.02,
                        help="±return threshold for direction labelling")
    args = parser.parse_args()

    if not _DECISION_LOG.exists():
        print(f"Decision log not found at {_DECISION_LOG}")
        sys.exit(1)

    raw = json.loads(_DECISION_LOG.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print("Decision log is not a list — schema mismatch.")
        sys.exit(1)

    print(f"Loaded {len(raw)} decision records")

    cutoff = datetime.now() - timedelta(days=args.days + 1)
    candidates = []
    for r in raw:
        extra = r.get("extra") or {}
        debate = extra.get("debate") if isinstance(extra, dict) else None
        if not isinstance(debate, dict):
            continue
        bull = debate.get("bull_argument", "").strip()
        bear = debate.get("bear_argument", "").strip()
        if len(bull) < 50 or len(bear) < 50:
            continue
        ts = _parse_iso(r.get("timestamp", ""))
        if ts is None or ts > cutoff:
            continue
        candidates.append((r, debate, bull, bear, ts))

    print(f"Candidates with debate text + eligible age: {len(candidates)}")

    eligible_count = 0
    skipped_count = 0
    out_lines: list[str] = []

    for r, debate, bull, bear, ts in candidates:
        ticker = r.get("ticker", "")
        ret = _forward_return(ticker, ts, days=args.days)
        if ret is None:
            skipped_count += 1
            entry = {
                "ticker": ticker,
                "timestamp": r.get("timestamp"),
                "bull_argument": bull,
                "bear_argument": bear,
                "hand_decision": debate.get("judge_decision"),
                "hand_confidence": debate.get("judge_confidence"),
                "forward_return": None,
                "ground_truth": None,
                "eligible": False,
                "reason": "forward_return_unavailable",
            }
        else:
            eligible_count += 1
            entry = {
                "ticker": ticker,
                "timestamp": r.get("timestamp"),
                "bull_argument": bull,
                "bear_argument": bear,
                "hand_decision": debate.get("judge_decision"),
                "hand_confidence": debate.get("judge_confidence"),
                "forward_return": round(ret, 4),
                "ground_truth": _ground_truth(ret, threshold=args.threshold),
                "eligible": True,
            }
        out_lines.append(json.dumps(entry, ensure_ascii=False))

    print()
    print(f"Eligible records (with forward data): {eligible_count}")
    print(f"Skipped (no forward data):             {skipped_count}")

    if eligible_count >= 100:
        print(f"\n✓ Phase B threshold met (≥100 eligible). Ready to run MIPROv2.")
    else:
        needed = 100 - eligible_count
        print(f"\n  Phase B needs {needed} more eligible records before compile is justified.")
        print(f"  Each new deep-analysis call (since the debate-text capture commit) adds one.")

    if args.dry_run:
        print(f"\n--dry-run: would have written {len(out_lines)} lines to {args.output}")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"\nWrote {len(out_lines)} lines to {args.output}")


def judge_metric(example: dict, prediction: dict) -> bool:
    """
    Phase B metric: compiled Judge's decision matches ground truth.

    Used in `dspy.MIPROv2(metric=judge_metric, ...)`. Sees example with
    `ground_truth` field and a prediction object with `.decision`.
    Confidence calibration is a secondary metric; for Phase B we
    optimize on raw decision accuracy.
    """
    truth = example.get("ground_truth")
    pred_decision = getattr(prediction, "decision", None) or prediction.get("decision")
    if not truth or not pred_decision:
        return False
    return str(truth).upper() == str(pred_decision).upper()


if __name__ == "__main__":
    main()
