"""
scripts/eval_context_compression.py
──────────────────────────────────────────────────────────────────
A/B framework: does compressing the Bull/Bear arguments before the
Judge call meaningfully change the Judge's decision?

decision_log.json doesn't capture intermediate Bull/Bear text, so we
can't replay historical Judge calls from real data. Instead this
script generates synthetic Bull/Bear pairs at varying lengths,
runs the Judge with each input variant (full / extractive / llm),
and reports decision agreement, confidence drift, and per-source
token savings.

Two outputs:
  1. Per-pair table (decision_full vs decision_compressed, conf delta)
  2. Aggregate verdict — agreement %, mean confidence delta, mean
     compression ratio

If agreement >= 95% AND mean confidence delta <= 5 points, compression
is safe to enable in the production deep-analysis pipeline. Below
either threshold, keep it off.

Usage:
    python scripts/eval_context_compression.py --n 10
    python scripts/eval_context_compression.py --mode extractive --n 20
    python scripts/eval_context_compression.py --offline   # no API calls
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


# ── Synthetic Bull/Bear pairs ──────────────────────────────────────────────
# Hand-picked to cover bullish-leaning, bearish-leaning, and ambiguous cases.
# Lengths chosen to push the auto-mode threshold (1500 chars) so we exercise
# both extractive and LLM compression paths.

_BULL_TEMPLATES = [
    # short, decisive bull
    "NVDA momentum is strong: ADX 32, RSI 62, price trading above all major MAs. "
    "Recent earnings beat by 5%, datacenter revenue +40% YoY. "
    "Options flow shows P/C 0.45 — bullish institutional positioning. "
    "Target: 165, stop: 140. Risk/reward 1:2.5.",
    # long, padded bull
    "The setup on TSLA is exceptional. " + (
        "Momentum indicators align across timeframes — daily ADX at 28, "
        "weekly RSI 58, and the 50/200 MA cross occurred 12 sessions ago. "
        "Volume confirms: average daily volume up 1.8x over the trailing 20 days. "
    ) * 4 + "Target: 295, stop: 265. Conviction: high.",
]

_BEAR_TEMPLATES = [
    # short, decisive bear
    "META faces antitrust headwinds and ad-spend slowdown. "
    "RSI overbought at 76, MACD divergence on daily, options P/C ratio 1.6 (bearish). "
    "Insider selling: 2 transactions in last 10 days totaling 250k shares. "
    "Target: 480, stop: 540. Risk: regulatory action.",
    # long, padded bear
    "AMZN is showing classic exhaustion patterns. " + (
        "Volume is declining on each test of resistance — dry-up suggests "
        "institutional distribution. Momentum oscillators (RSI, Stochastic) "
        "are diverging negatively from price. Earnings preview consensus is "
        "already pricing in optimism, leaving little room for upside surprise. "
    ) * 4 + "Risk: short squeeze on broader market rally.",
]


# ── Mock Judge (offline) ──────────────────────────────────────────────────
# When --offline, we don't call Claude. Instead we use a deterministic "judge"
# that picks BUY/SELL/WAIT based on which side has more directional keywords —
# this is enough to test that compression preserves the signal vs scrambles it.

_BULL_KW = ("bullish", "buy", "long", "target", "above", "beat", "exceeds", "strong", "momentum")
_BEAR_KW = ("bearish", "sell", "short", "stop", "below", "miss", "decline", "overbought", "headwinds")


def _mock_judge(bull: str, bear: str) -> dict:
    """Deterministic stand-in for the Claude Judge call."""
    b_low = bull.lower()
    bear_low = bear.lower()
    bull_score = sum(b_low.count(k) for k in _BULL_KW)
    bear_score = sum(bear_low.count(k) for k in _BEAR_KW)
    diff = bull_score - bear_score
    if diff > 2:
        decision = "BUY"
    elif diff < -2:
        decision = "SELL"
    else:
        decision = "WAIT"
    confidence = min(85, 40 + abs(diff) * 5)
    return {"decision": decision, "confidence": confidence,
            "bull_kw": bull_score, "bear_kw": bear_score}


# ── Eval ───────────────────────────────────────────────────────────────────


def run_pair(idx: int, bull: str, bear: str, mode: str, offline: bool) -> dict:
    from engine.context_compressor import compress, compression_ratio

    bull_c = compress(bull, mode=mode, max_chars=400)
    bear_c = compress(bear, mode=mode, max_chars=400)

    full = _mock_judge(bull, bear) if offline else _real_judge(bull, bear)
    compr = _mock_judge(bull_c, bear_c) if offline else _real_judge(bull_c, bear_c)

    return {
        "idx": idx,
        "bull_chars": len(bull),
        "bear_chars": len(bear),
        "bull_ratio": compression_ratio(bull, bull_c),
        "bear_ratio": compression_ratio(bear, bear_c),
        "decision_full": full["decision"],
        "decision_compr": compr["decision"],
        "agree": full["decision"] == compr["decision"],
        "conf_full": full["confidence"],
        "conf_compr": compr["confidence"],
        "conf_delta": compr["confidence"] - full["confidence"],
    }


def _real_judge(bull: str, bear: str) -> dict:
    """Hit the real Claude Judge. Costs ~$0.005 per call."""
    from llm.debate import _call_judge
    from llm.claude_client import get_client
    initial = MagicMock()
    initial.decision = "WAIT"
    initial.confidence = 50.0
    initial.risk_level = "MEDIUM"
    initial.reasoning = []
    initial.probabilities = {"up": 0.33, "neutral": 0.34, "down": 0.33}
    initial.source = "eval"
    initial.signal_strength = 50.0
    try:
        out = _call_judge(get_client(), initial, bull, bear, "EVAL", {})
        return {"decision": out.decision, "confidence": float(out.confidence)}
    except Exception as e:
        return {"decision": "WAIT", "confidence": 0.0, "error": str(e)[:100]}


def _load_real_pairs_from_log(limit: int = 50) -> list[tuple[str, str]]:
    """
    Pull (bull, bear) pairs from memory_data/decision_log.json — populated
    by `llm/debate.py` since the 'stash debate text on decision.extra'
    commit. Returns pairs from the most recent `limit` records that have
    debate text. Empty list if none available.
    """
    import json as _json
    from pathlib import Path as _Path

    log_path = _Path(__file__).resolve().parent.parent / "memory_data" / "decision_log.json"
    if not log_path.exists():
        return []
    try:
        records = _json.loads(log_path.read_text(encoding="utf-8"))
    except (_json.JSONDecodeError, OSError):
        return []
    if not isinstance(records, list):
        return []

    out: list[tuple[str, str]] = []
    for r in records:
        extra = r.get("extra") or {}
        debate = extra.get("debate") if isinstance(extra, dict) else None
        if not isinstance(debate, dict):
            continue
        bull = (debate.get("bull_argument") or "").strip()
        bear = (debate.get("bear_argument") or "").strip()
        if len(bull) > 50 and len(bear) > 50:
            out.append((bull, bear))
        if len(out) >= limit:
            break
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="extractive",
                        choices=["extractive", "llm", "auto", "off"])
    parser.add_argument("--n", type=int, default=8,
                        help="number of pair runs (rotates through templates)")
    parser.add_argument("--offline", action="store_true",
                        help="skip real Claude calls, use deterministic mock")
    parser.add_argument("--from-log", action="store_true",
                        help="use decision_log.json for real Bull/Bear pairs "
                             "instead of synthetic templates")
    args = parser.parse_args()

    pairs = []
    if args.from_log:
        real = _load_real_pairs_from_log(limit=args.n)
        if not real:
            print("--from-log: no records with debate text yet. Either:")
            print("  (a) run /api/deep-analysis a few times to populate the log, or")
            print("  (b) drop --from-log to fall back to synthetic templates.")
            sys.exit(1)
        print(f"Loaded {len(real)} real (Bull, Bear) pairs from decision_log.json\n")
        for i, (bull, bear) in enumerate(real):
            pairs.append(run_pair(i, bull, bear, args.mode, args.offline))
    else:
        for i in range(args.n):
            bull = _BULL_TEMPLATES[i % len(_BULL_TEMPLATES)]
            bear = _BEAR_TEMPLATES[i % len(_BEAR_TEMPLATES)]
            pairs.append(run_pair(i, bull, bear, args.mode, args.offline))

    print()
    print(f"Context Compression Eval — mode={args.mode}, n={args.n}, offline={args.offline}")
    print()
    header = (
        f"{'#':>3} {'bull→':>6} {'bear→':>6}  "
        f"{'full':<6} {'compr':<6}  "
        f"{'agree':<6}  {'conf_d':>7}"
    )
    print(header)
    print("─" * len(header))
    for p in pairs:
        agree = "✓" if p["agree"] else "✗"
        print(
            f"{p['idx']:>3} "
            f"{p['bull_ratio']:>6.2f} {p['bear_ratio']:>6.2f}  "
            f"{p['decision_full']:<6} {p['decision_compr']:<6}  "
            f"{agree:<6}  {p['conf_delta']:+7.1f}"
        )

    n = len(pairs)
    n_agree = sum(1 for p in pairs if p["agree"])
    agreement = n_agree / n if n else 0
    avg_conf_delta = sum(abs(p["conf_delta"]) for p in pairs) / n if n else 0
    avg_ratio = sum((p["bull_ratio"] + p["bear_ratio"]) / 2 for p in pairs) / n if n else 0

    print()
    print(f"Decision agreement:    {n_agree}/{n} = {agreement * 100:.1f}%")
    print(f"Mean |conf delta|:     {avg_conf_delta:.1f} pts")
    print(f"Mean compression:      {avg_ratio:.2f} ({(1 - avg_ratio) * 100:.0f}% chars saved)")
    print()
    safe = agreement >= 0.95 and avg_conf_delta <= 5.0
    verdict = "✓ SAFE TO ENABLE" if safe else "✗ KEEP DISABLED"
    print(f"Verdict: {verdict}")
    print(
        "Threshold: agreement ≥ 95% AND mean |conf delta| ≤ 5 pts. "
        "Both must hold."
    )


if __name__ == "__main__":
    main()
