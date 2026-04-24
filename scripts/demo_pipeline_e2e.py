"""
scripts/demo_pipeline_e2e.py
──────────────────────────────────────────────────────────────────
End-to-end demo: signal_fusion → decision → portfolio_manager.

Exercises the full pipeline on real market data (yfinance, Polymarket,
Reddit, etc.) with a mocked portfolio state. Prints conviction, sources,
and the PM verdict — useful as a smoke test and for PR descriptions.

Usage:
    python scripts/demo_pipeline_e2e.py                # default NVDA
    python scripts/demo_pipeline_e2e.py TSLA AMD       # multiple tickers
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# Mock portfolio — 25% NVDA (concentrated), 10% AAPL, 65% cash
from engine.portfolio_manager import Position, approve_decision

MOCK_PORTFOLIO = [
    Position("NVDA", 2_500, sector="Tech"),
    Position("AAPL", 1_000, sector="Tech"),
]
MOCK_PORTFOLIO_VALUE = 10_000.0
RECENT_DECISIONS = [
    {"decision": "BUY"},
    {"decision": "BUY"},
    {"decision": "BUY"},
    {"decision": "WAIT"},
]


def section(title: str) -> None:
    print()
    print("═" * 74)
    print(f"  {title}")
    print("═" * 74)


def fusion_line(name: str, s: dict) -> str:
    status = "✓" if s.get("available") else "✗"
    score = s.get("score", 0)
    weight = s.get("normalized_weight", 0)
    return f"  {status} {name:20s} {score:+4d}  w={weight:.2f}"


def run_one(ticker: str) -> None:
    from engine.signal_fusion import fuse_signals

    section(f"Ticker: {ticker}")

    result = fuse_signals(
        ticker,
        summary={"rsi": 55, "close": 135, "ma20": 130, "ma50": 125,
                 "macd_hist": 0.05, "adx": 24},
    )

    print(
        f"  conviction={result['conviction']:+d}  "
        f"direction={result['direction']}  "
        f"confidence={result['confidence']}  "
        f"n_sources={result['n_sources']}/8"
    )
    print()
    print("  SOURCES:")
    for name, s in result["sources"].items():
        print(fusion_line(name, s))

    print()
    print(f"  {result['fusion_detail']}")

    # Map conviction to a mock decision
    if result["conviction"] > 15:
        decision_label = "BUY"
    elif result["conviction"] < -15:
        decision_label = "SELL"
    else:
        decision_label = "WAIT"

    mock_decision = {
        "decision": decision_label,
        "confidence": min(100, max(0, result["confidence"])),
        "signal_strength": min(100, max(0, abs(result["conviction"]))),
        "sector": "Tech",
    }

    print()
    print(f"  Proposed decision: {decision_label} "
          f"(conf={mock_decision['confidence']}, "
          f"strength={mock_decision['signal_strength']})")

    # Portfolio Manager gate
    verdict = approve_decision(
        ticker=ticker,
        decision=mock_decision,
        portfolio=MOCK_PORTFOLIO,
        portfolio_value=MOCK_PORTFOLIO_VALUE,
        recent_decisions=RECENT_DECISIONS,
    )

    print()
    print("  PORTFOLIO MANAGER:")
    status = "✅ APPROVED" if verdict["approved"] else "❌ REJECTED"
    print(f"    {status}  position={verdict['scaled_position_pct']:.1f}%")
    print(f"    Reason: {verdict['reason']}")
    if verdict["warnings"]:
        for w in verdict["warnings"]:
            print(f"    ⚠  {w}")
    print(f"    Checks: {verdict['checks']}")


def main() -> None:
    tickers = sys.argv[1:] or ["NVDA"]
    print("\nORALLEXA pipeline end-to-end demo")
    print(f"Portfolio: {sum(p.value_usd for p in MOCK_PORTFOLIO):.0f}/{MOCK_PORTFOLIO_VALUE:.0f} USD")
    for p in MOCK_PORTFOLIO:
        pct = p.value_usd / MOCK_PORTFOLIO_VALUE * 100
        print(f"  {p.ticker}: ${p.value_usd:,.0f} ({pct:.0f}%) {p.sector or ''}")
    print(f"Recent decisions: {[d['decision'] for d in RECENT_DECISIONS]}")

    for t in tickers:
        try:
            run_one(t)
        except Exception as e:
            print(f"\n  ❌ {t} failed: {e}")

    print()


if __name__ == "__main__":
    main()
