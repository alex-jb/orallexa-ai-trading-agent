"""Binary-event prediction module — Kalshi + Polymarket dual.

Adapts Orallexa's stock-trading architecture (Bull/Bear LangGraph debate +
multi-source context) to CFTC-regulated binary event markets. v0.1 wires
both Kalshi (real-money path, NY-legal today via demo + ACH) and
Polymarket (Gamma API for historical read-only backtest; trading deferred
until Polymarket US/QCEX waitlist opens non-sports markets in Q4 2026).

The `BinaryMarket` dataclass is platform-agnostic, so the same debate /
queue / sizing / retro pipeline serves both venues unchanged.

Form: **decision-support only (Form A)**. The system writes a morning
markdown queue of edge-scored markets; a human reads, decides, and places
every trade by hand on kalshi.com. Phase 1 has no executor that signs or
sends — `executor.py` emits CSV only. This is enforced at the code layer
so the loop physically cannot auto-trade until a deliberate v0.2 upgrade.

Why this shape:
- Solo dev validating an LLM signal needs the loop to fail safe by default.
- 92.6% of human traders on these venues lose money; LLM hallucinations on
  resolution criteria are a real failure mode (see retro.py).
- "AI/ML SDE with a binary-event prediction system + Brier-score backtest"
  is a portfolio asset. "AI/ML SDE who auto-traded a prediction market" is
  not — same architecture, very different reputational shape.

Kill conditions (hardcoded in retro.py):
1. Brier score not significantly better than market price baseline on 100+
   settled markets → archive.
2. Single-month drawdown > 15% bankroll → 30-day pause + manual review.
3. Any path that violates Kalshi/Polymarket ToS or US prediction-market law
   → immediate stop (do not write VPN-evading code).
"""
from markets.market import BinaryMarket, PriceTick

__all__ = ["BinaryMarket", "PriceTick"]
