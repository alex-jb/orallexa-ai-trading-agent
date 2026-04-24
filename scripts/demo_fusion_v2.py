"""
scripts/demo_fusion_v2.py
──────────────────────────────────────────────────────────────────
End-to-end integration demo for the 7-source signal_fusion pipeline.

Uses mocked (but realistic) inputs for each source to verify:
  1. fuse_signals produces sane conviction scores across scenarios
  2. earnings + social sources actually move the needle when active
  3. weight normalization + source agreement work correctly

Not a historical alpha backtest — that would require cached social
post history and per-earnings historical data which we don't have.
For alpha verification, run this against live market data + actual
earnings dates over a walk-forward period.

Usage:
    python scripts/demo_fusion_v2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


SCENARIOS = {
    "strong_bullish_with_earnings": {
        "summary": {"rsi": 30, "close": 105, "ma20": 100, "ma50": 95, "macd_hist": 0.08, "adx": 28},
        "ml_result": {"results": {
            "random_forest": {"status": "ok", "metrics": {"sharpe": 2.2, "total_return": 0.18}},
            "xgboost":       {"status": "ok", "metrics": {"sharpe": 1.9, "total_return": 0.15}},
        }},
        "news_items": [{"score": 0.5}, {"score": 0.4}, {"score": 0.3}],
        "options":    {"available": True, "score": 55, "pc_ratio": 0.55},
        "inst":       {"available": True, "score": 35, "insider_transactions": []},
        "social":     {"available": True, "score": 45, "n_posts": 30, "bullish": 22, "bearish": 3, "engagement": 2_400},
        "earnings":   {"available": True, "score": 58, "days_until": 4,
                       "avg_drift_5d": 2.8, "positive_rate": 0.78},
    },
    "mixed_signals_no_earnings": {
        "summary": {"rsi": 52, "close": 100, "ma20": 100, "ma50": 102, "macd_hist": 0.0},
        "ml_result": {"results": {
            "random_forest": {"status": "ok", "metrics": {"sharpe": 0.8, "total_return": 0.04}},
        }},
        "news_items": [{"score": 0.1}, {"score": -0.2}],
        "options":    {"available": True, "score": 10, "pc_ratio": 0.95},
        "inst":       {"available": True, "score": -5, "insider_transactions": []},
        "social":     {"available": True, "score": 5, "n_posts": 14, "bullish": 7, "bearish": 5, "engagement": 500},
        "earnings":   {"available": False, "score": 0},
    },
    "bearish_earnings_imminent": {
        "summary": {"rsi": 72, "close": 100, "ma20": 103, "ma50": 105, "macd_hist": -0.05},
        "ml_result": {"results": {
            "random_forest": {"status": "ok", "metrics": {"sharpe": -0.8, "total_return": -0.06}},
        }},
        "news_items": [{"score": -0.4}, {"score": -0.3}],
        "options":    {"available": True, "score": -40, "pc_ratio": 1.6},
        "inst":       {"available": True, "score": -25, "short_pct": 8.0},
        "social":     {"available": True, "score": -35, "n_posts": 28, "bullish": 5, "bearish": 18, "engagement": 1_800},
        "earnings":   {"available": True, "score": -50, "days_until": 2,
                       "avg_drift_5d": -2.2, "positive_rate": 0.30},
    },
}


def run_scenario(name: str, cfg: dict) -> dict:
    from engine.signal_fusion import fuse_signals
    with patch("engine.signal_fusion._fetch_options_flow", return_value=cfg["options"]), \
         patch("engine.signal_fusion._fetch_institutional_signals", return_value=cfg["inst"]), \
         patch("engine.signal_fusion._fetch_social_signal", return_value=cfg["social"]), \
         patch("engine.signal_fusion._fetch_earnings_signal", return_value=cfg["earnings"]):
        return fuse_signals(
            "DEMO",
            summary=cfg["summary"],
            ml_result=cfg["ml_result"],
            news_items=cfg["news_items"],
        )


def pretty(result: dict) -> str:
    sources = result["sources"]
    active = [n for n, s in sources.items() if s["available"]]
    breakdown = " | ".join(
        f"{n[:6]}: {sources[n]['score']:+d}×{sources[n]['normalized_weight']:.2f}"
        for n in active
    )
    return (
        f"  conviction={result['conviction']:+d}  direction={result['direction']:<8} "
        f"confidence={result['confidence']}  n={result['n_sources']}\n"
        f"    {breakdown}\n"
        f"    top: {result['fusion_detail']}"
    )


def main() -> None:
    print("═" * 70)
    print("  signal_fusion v2 — 7-source end-to-end demo")
    print("═" * 70)
    for name, cfg in SCENARIOS.items():
        print(f"\n▸ {name}")
        result = run_scenario(name, cfg)
        print(pretty(result))

    # Ablation: does the earnings source move conviction when other signals are weak?
    print("\n" + "═" * 70)
    print("  Ablation: earnings-only-divergent scenario")
    print("═" * 70)
    divergent_cfg = {
        "summary": {"rsi": 50, "close": 100, "ma20": 100, "ma50": 100, "macd_hist": 0.0},
        "ml_result": {"results": {}},
        "news_items": [],
        "options": {"available": False, "score": 0},
        "inst":    {"available": False, "score": 0},
        "social":  {"available": True, "score": 5, "n_posts": 10, "bullish": 3, "bearish": 3, "engagement": 100},
        "earnings": {"available": True, "score": 65, "days_until": 3,
                      "avg_drift_5d": 3.5, "positive_rate": 0.82},
    }
    with_earn = run_scenario("earn_on", divergent_cfg)
    no_earn = run_scenario("earn_off", {**divergent_cfg, "earnings": {"available": False, "score": 0}})
    print(f"\n  with earnings (+65): conviction={with_earn['conviction']:+d}  direction={with_earn['direction']}")
    print(f"  without earnings:    conviction={no_earn['conviction']:+d}  direction={no_earn['direction']}")
    print(f"  Δ from earnings source: {with_earn['conviction'] - no_earn['conviction']:+d}")
    print(f"\n  → earnings source is {'active' if with_earn['conviction'] != no_earn['conviction'] else 'inert'}")


if __name__ == "__main__":
    main()
