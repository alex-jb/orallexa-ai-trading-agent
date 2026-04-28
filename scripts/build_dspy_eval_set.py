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

Synthetic mode (--synthesize N):
  Until production runs accumulate 100 eligible records with debate
  text + forward outcomes, the compile harness is unrunnable on real
  data. `--synthesize 200` emits 200 plausible (bull, bear, truth)
  rows seeded on direction templates so the harness can be end-to-end
  validated. Synthetic rows carry `synthetic=True` so they're easy to
  filter out later.

Usage:
    python scripts/build_dspy_eval_set.py                    # 5-day window
    python scripts/build_dspy_eval_set.py --days 3
    python scripts/build_dspy_eval_set.py --output /tmp/x.jsonl
    python scripts/build_dspy_eval_set.py --dry-run          # count only
    python scripts/build_dspy_eval_set.py --synthesize 200   # synthetic eval set
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


# ── Synthetic eval-set generation ─────────────────────────────────────────
# Used for end-to-end harness validation when production data is sparse.
# Each template returns a realistic-looking debate paragraph keyed off a
# numeric "strength" so the harness can verify the compiled judge picks up
# on the lopsided cases.

_BULL_TEMPLATES = [
    "{ticker} is breaking out of a multi-week consolidation on volume {vol:.1f}× the 30-day average. "
    "RSI at {rsi} confirms momentum without overextension. The MACD histogram has been positive for "
    "{streak} consecutive sessions while institutional accumulation showed a net inflow of "
    "${flow:.0f}M last week. Sector rotation favors this name as {sector} regains relative strength "
    "vs the broader index. Earnings revisions trended {revision_dir} for three consecutive quarters, "
    "a leading signal historically associated with multi-month returns of +{ret:.1f}%.",

    "Strong fundamental backdrop for {ticker}: revenue growth of {growth:.1f}% YoY, gross margin "
    "expansion of {margin:.1f} percentage points, and a fortress balance sheet with ${cash:.1f}B in "
    "net cash. The chart shows a textbook cup-and-handle with measured-move target {ret:.0f}% above "
    "current price. Options flow leans bullish with put/call at {pc:.2f} and unusual call volume "
    "concentrated in the {strike} strike for next month. Risk/reward at current levels is "
    "asymmetric to the upside.",
]

_BEAR_TEMPLATES = [
    "{ticker} just broke the {ma}-day moving average on {vol:.1f}× volume — the first decisive break "
    "since {month}. RSI at {rsi} suggests the move has further to fall before becoming oversold. "
    "Sector breadth is deteriorating and the relative strength line versus {sector} has rolled over. "
    "Insider transactions over the trailing six months show {insider_count} sales worth ${insider:.0f}M "
    "and zero buys. Forward guidance was cut at the last earnings call, and the stock has bled "
    "{drawdown:.1f}% from its 52-week high.",

    "The bull case ignores three structural headwinds for {ticker}: (1) {ticker}'s key end-market is "
    "decelerating, with channel checks showing order books down {orders:.0f}% sequentially. "
    "(2) Margin compression is accelerating as input costs rise faster than pricing power. "
    "(3) The stock trades at {pe}× forward earnings versus a 5-year median of {median_pe}×, leaving "
    "no cushion for a multiple compression scenario. Technicals show a head-and-shoulders top with a "
    "measured-move target {ret:.0f}% lower.",
]


def _synth_bull(rng, ticker: str, strength: float) -> str:
    template = _BULL_TEMPLATES[rng.randrange(len(_BULL_TEMPLATES))]
    sectors = ["semiconductors", "cloud infra", "consumer discretionary", "biotech", "energy"]
    revision_dirs = ["up", "higher", "positively"]
    return template.format(
        ticker=ticker,
        vol=1.5 + strength * 2.5,
        rsi=55 + int(strength * 10),
        streak=2 + int(strength * 4),
        flow=50 + strength * 200,
        sector=sectors[rng.randrange(len(sectors))],
        revision_dir=revision_dirs[rng.randrange(len(revision_dirs))],
        ret=3 + strength * 12,
        growth=8 + strength * 25,
        margin=0.5 + strength * 4,
        cash=1.0 + strength * 20,
        pc=0.55 + strength * 0.20,
        strike=int(100 + strength * 50),
    )


def _synth_bear(rng, ticker: str, strength: float) -> str:
    template = _BEAR_TEMPLATES[rng.randrange(len(_BEAR_TEMPLATES))]
    sectors = ["semis", "software", "consumer staples", "REITs", "industrials"]
    months = ["August", "October", "March", "January", "September"]
    return template.format(
        ticker=ticker,
        ma=rng.choice([20, 50, 100, 200]),
        vol=1.3 + strength * 2.0,
        month=months[rng.randrange(len(months))],
        rsi=45 - int(strength * 12),
        sector=sectors[rng.randrange(len(sectors))],
        insider_count=2 + int(strength * 4),
        insider=8 + strength * 40,
        drawdown=10 + strength * 25,
        orders=5 + int(strength * 30),
        pe=int(35 + strength * 25),
        median_pe=int(20 + strength * 5),
        ret=4 + strength * 12,
    )


def synthesize_eval_set(n: int, seed: int = 42) -> list[dict]:
    """
    Build N synthetic (bull, bear, ground_truth) rows for harness testing.

    Distribution: ~40% BUY, ~40% SELL, ~20% WAIT — matches what we observe in
    the 294-record decision_log so the metric stays representative. Each row's
    ground_truth is determined by which side has the stronger narrative; the
    harness should learn to recover this signal.
    """
    import random

    rng = random.Random(seed)
    tickers = ["NVDA", "AAPL", "MSFT", "GOOG", "META", "TSLA", "AMD", "AVGO", "CRWD", "NET"]
    rows = []
    for i in range(n):
        roll = rng.random()
        if roll < 0.40:
            ground_truth = "BUY"
            bull_strength, bear_strength = 0.7 + rng.random() * 0.3, 0.1 + rng.random() * 0.2
            forward_return = 0.025 + rng.random() * 0.05
        elif roll < 0.80:
            ground_truth = "SELL"
            bull_strength, bear_strength = 0.1 + rng.random() * 0.2, 0.7 + rng.random() * 0.3
            forward_return = -(0.025 + rng.random() * 0.05)
        else:
            ground_truth = "WAIT"
            bull_strength, bear_strength = 0.4 + rng.random() * 0.2, 0.4 + rng.random() * 0.2
            forward_return = (rng.random() - 0.5) * 0.03

        ticker = tickers[rng.randrange(len(tickers))]
        rows.append({
            "ticker": ticker,
            "timestamp": None,
            "bull_argument":   _synth_bull(rng, ticker, bull_strength),
            "bear_argument":   _synth_bear(rng, ticker, bear_strength),
            "hand_decision":   None,
            "hand_confidence": None,
            "forward_return":  round(forward_return, 4),
            "ground_truth":    ground_truth,
            "eligible":        True,
            "synthetic":       True,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=5,
                        help="forward window in trading days")
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true",
                        help="count eligible records without writing")
    parser.add_argument("--threshold", type=float, default=0.02,
                        help="±return threshold for direction labelling")
    parser.add_argument("--synthesize", type=int, default=0,
                        help="emit N synthetic rows instead of reading the log")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed for synthetic mode (deterministic)")
    args = parser.parse_args()

    if args.synthesize > 0:
        rows = synthesize_eval_set(args.synthesize, seed=args.seed)
        out_lines = [json.dumps(r, ensure_ascii=False) for r in rows]
        gt_counts = {gt: sum(1 for r in rows if r["ground_truth"] == gt) for gt in ("BUY", "SELL", "WAIT")}
        print(f"Synthesized {len(rows)} rows (seed={args.seed})")
        print(f"  ground_truth distribution: {gt_counts}")
        if args.dry_run:
            print(f"--dry-run: would have written {len(out_lines)} lines to {args.output}")
            return
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        print(f"Wrote {len(out_lines)} synthetic lines to {args.output}")
        return

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
