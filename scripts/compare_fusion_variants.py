"""
scripts/compare_fusion_variants.py
──────────────────────────────────────────────────────────────────
Compare the conviction + direction produced by the legacy 5-source
fusion vs the full 8-source fusion across a basket of tickers.

Not a walk-forward backtest — that would require cached historical
Polymarket / Reddit / earnings data which we don't maintain yet. This
script pins current-moment inputs and runs two weight sets over them
to measure how much the new sources (social / earnings / prediction
markets) actually move the needle in practice.

Usage:
    python scripts/compare_fusion_variants.py NVDA TSLA AAPL
    python scripts/compare_fusion_variants.py          # default basket
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.signal_fusion import fuse_signals, DEFAULT_WEIGHTS


LEGACY_5_SOURCE_WEIGHTS = {
    "technical":        0.25,
    "ml_ensemble":      0.25,
    "news_sentiment":   0.15,
    "options_flow":     0.20,
    "institutional":    0.15,
    # new sources forced to zero — same behaviour as the pre-Phase 7 engine
    "social_sentiment":   0,
    "earnings":           0,
    "prediction_markets": 0,
}

DEFAULT_BASKET = ["NVDA", "AAPL", "TSLA", "AMD", "META"]


def _fmt(n: int) -> str:
    return f"{n:+d}" if isinstance(n, (int, float)) else str(n)


def _diverge(a: int, b: int) -> str:
    delta = b - a
    if abs(delta) < 5:
        return "≈"
    if a == 0 or b == 0:
        return "—"
    return f"Δ {_fmt(delta)}"


def run(tickers: list[str]) -> None:
    print("\nFusion variant comparison: 5-source legacy vs 8-source Phase-8")
    print("Same live inputs. Different weight policies.\n")

    header = f"{'Ticker':<8} {'5-src conv':>12} {'5-src dir':>12} | {'8-src conv':>12} {'8-src dir':>12}   {'Shift':>10}"
    print(header)
    print("─" * len(header))

    for t in tickers:
        try:
            summary = {"rsi": 55, "close": 100, "ma20": 98, "ma50": 95, "macd_hist": 0.02}
            five = fuse_signals(t, summary=summary, weights=LEGACY_5_SOURCE_WEIGHTS)
            eight = fuse_signals(t, summary=summary, weights=DEFAULT_WEIGHTS)
            shift = _diverge(five["conviction"], eight["conviction"])
            print(
                f"{t:<8} "
                f"{_fmt(five['conviction']):>12} {five['direction']:>12} | "
                f"{_fmt(eight['conviction']):>12} {eight['direction']:>12}   {shift:>10}"
            )
        except Exception as e:
            print(f"{t:<8}  {str(e)[:60]}")

    print("\nInterpretation:")
    print("  ≈            — new sources confirm legacy signal (little shift)")
    print("  Δ ±5 to ±20  — new sources add meaningful information")
    print("  Δ >±20       — new sources sharply disagree with legacy fusion")
    print("                 (inspect per-source breakdown before acting)")


def main() -> None:
    tickers = sys.argv[1:] or DEFAULT_BASKET
    run(tickers)


if __name__ == "__main__":
    main()
