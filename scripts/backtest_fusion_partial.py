"""
scripts/backtest_fusion_partial.py
──────────────────────────────────────────────────────────────────
Synthetic time-series simulation of signal_fusion variants.

We can't do a true walk-forward backtest of social_sentiment +
prediction_markets — those sources have no historical cache and the
APIs only return current data. What we CAN test is whether the
WEIGHTING POLICY (5-source legacy vs 8-source Phase 8) produces a
better strategy when source scores follow a plausible joint distribution.

Approach:
  1. Simulate N days. Each day generates an underlying "true" market
     direction (random walk) and per-source scores correlated with it
     plus noise (different SNR per source — tech is moderate, ml +
     options high, social/news low, etc.).
  2. Run fuse_signals with mocked _fetch_* injected at each step under
     two weight policies:
       LEGACY_5  : original tech/ml/news/options/institutional weights
       PHASE_8   : full 8-source weights (current default)
  3. Translate conviction → position (-1 / 0 / +1, scaled by abs(conv)/100)
     and compute the strategy return = position × next-day true direction.
  4. Report Sharpe, total return, hit rate, max conviction stability.

Not a substitute for real out-of-sample testing — but a defensible way
to compare weight policies on the same input distribution.

Usage:
    python scripts/backtest_fusion_partial.py
    python scripts/backtest_fusion_partial.py --days 500 --seed 7
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


LEGACY_5 = {
    "technical":          0.25,
    "ml_ensemble":         0.25,
    "news_sentiment":      0.15,
    "options_flow":        0.20,
    "institutional":       0.15,
    "social_sentiment":    0.0,
    "earnings":            0.0,
    "prediction_markets":  0.0,
}


# Per-source signal-to-noise. Higher SNR = source more aligned with
# the underlying true direction. These are guesses calibrated to what
# domain literature suggests — adjust to taste.
SNR = {
    "technical":          0.45,
    "ml_ensemble":        0.55,
    "news_sentiment":     0.20,
    "options_flow":       0.40,
    "institutional":      0.25,
    "social_sentiment":   0.15,
    "earnings":           0.30,
    "prediction_markets": 0.50,  # smart-money signal
}


def _gen_day(rng, true_dir: float) -> dict:
    """Generate per-source scores correlated with `true_dir` ∈ [-1, +1]."""
    out = {}
    for src, snr in SNR.items():
        # Score in [-100, +100]: signal component + noise component
        signal_part = true_dir * snr * 100
        noise_part = rng.normal(0, (1 - snr) * 60)
        score = max(-100, min(100, int(signal_part + noise_part)))
        out[src] = score
    return out


def _run_strategy(weights: dict, days: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    from engine.signal_fusion import fuse_signals

    # Pre-generate true direction series (random walk on direction probability)
    true_dirs = np.tanh(np.cumsum(rng.normal(0, 0.4, days)) * 0.1)
    next_returns = np.diff(np.append(true_dirs, true_dirs[-1])) * 0.02  # ~2% range

    convictions: list[int] = []
    positions: list[float] = []
    strategy_returns: list[float] = []

    for d in range(days):
        scores = _gen_day(rng, float(true_dirs[d]))

        def _opt(t, s=scores): return {"available": True, "score": s["options_flow"]}
        def _inst(t, s=scores): return {"available": True, "score": s["institutional"]}
        def _social(t, s=scores): return {"available": True, "score": s["social_sentiment"]}
        def _earn(t, s=scores): return {"available": True, "score": s["earnings"]}
        def _pm(t, s=scores): return {"available": True, "score": s["prediction_markets"]}

        with patch("engine.signal_fusion._fetch_options_flow", side_effect=_opt), \
             patch("engine.signal_fusion._fetch_institutional_signals", side_effect=_inst), \
             patch("engine.signal_fusion._fetch_social_signal", side_effect=_social), \
             patch("engine.signal_fusion._fetch_earnings_signal", side_effect=_earn), \
             patch("engine.signal_fusion._fetch_prediction_markets_signal", side_effect=_pm):
            # Build a realistic technical summary that produces the desired score
            # The technical scoring uses RSI/MACD/MA — we tune RSI to map to target.
            tech_target = scores["technical"]
            rsi = 50 + tech_target * 0.3
            close = 100 + tech_target * 0.5
            summary = {"rsi": rsi, "close": close,
                       "ma20": 100, "ma50": 99, "macd_hist": tech_target / 1000}

            # ml scoring needs a results dict. Map to target.
            ml_sharpe = scores["ml_ensemble"] / 50.0
            ml_result = {"results": {
                "random_forest": {"status": "ok",
                                  "metrics": {"sharpe": ml_sharpe, "total_return": ml_sharpe * 0.05}},
            }}

            # news items
            news_compound = scores["news_sentiment"] / 200
            news = [{"score": news_compound}]

            r = fuse_signals(
                "SIM", summary=summary, ml_result=ml_result,
                news_items=news, weights=weights,
            )

        conv = r["conviction"]
        # Position: scale by conviction strength (|conv| / 100)
        position = math.copysign(min(abs(conv) / 100, 1.0), conv) if abs(conv) > 10 else 0.0
        convictions.append(conv)
        positions.append(position)
        strategy_returns.append(position * float(next_returns[d]))

    sr = np.array(strategy_returns)
    if sr.std() > 0:
        sharpe = float(sr.mean() / sr.std() * math.sqrt(252))
    else:
        sharpe = 0.0
    cum_return = float((1 + sr).prod() - 1)
    hit_rate = float(np.mean(sr > 0)) if (sr != 0).any() else 0.0
    avg_position = float(np.mean(np.abs(positions)))
    return {
        "sharpe":      round(sharpe, 3),
        "total_return": round(cum_return * 100, 2),
        "hit_rate":     round(hit_rate, 3),
        "avg_position": round(avg_position, 3),
        "conv_std":     round(float(np.std(convictions)), 1),
        "n_traded":     int(np.sum(np.abs(positions) > 0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=252)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-trials", type=int, default=5,
                        help="run with N seeds and average")
    args = parser.parse_args()

    print()
    print(f"Synthetic fusion-policy backtest — {args.days} days × {args.n_trials} seeds")
    print(f"Underlying truth: random-walk tanh(cumsum(N(0, 0.4)) * 0.1)")
    print()

    from engine.signal_fusion import DEFAULT_WEIGHTS
    policies = {"5-src legacy": LEGACY_5, "8-src Phase 8": DEFAULT_WEIGHTS}

    aggregated: dict = {p: [] for p in policies}
    for trial in range(args.n_trials):
        seed = args.seed + trial * 17
        for name, weights in policies.items():
            r = _run_strategy(weights, days=args.days, seed=seed)
            aggregated[name].append(r)

    header = f"{'Policy':<18} {'Sharpe':>9} {'Return%':>9} {'HitRate':>9} {'AvgPos':>8} {'ConvStd':>9}"
    print(header)
    print("─" * len(header))
    for name, runs in aggregated.items():
        avg = lambda k: round(sum(r[k] for r in runs) / len(runs), 3)
        print(
            f"{name:<18} {avg('sharpe'):>9.3f} {avg('total_return'):>9.2f} "
            f"{avg('hit_rate'):>9.3f} {avg('avg_position'):>8.3f} {avg('conv_std'):>9.1f}"
        )

    print()
    print("Notes:")
    print("  Sharpe / Return / HitRate measure the strategy quality.")
    print("  AvgPos is the average |position| size; higher = more aggressive book.")
    print("  ConvStd is conviction time-series volatility; lower = more stable signal.")


if __name__ == "__main__":
    main()
