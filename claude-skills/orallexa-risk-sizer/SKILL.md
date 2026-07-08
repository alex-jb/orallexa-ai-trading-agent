---
name: orallexa-risk-sizer
description: >
  FinPos-style position sizer for trading decisions. Takes an upstream Judge
  direction (long/short/no_op), a bankroll, a volatility regime, and Kelly
  parameters — returns a fund/skip verdict with a Kelly-cap-respecting,
  drawdown-adjusted position size. Never emits a direction. Ports from
  Orallexa's Python engine to a callable skill inside Claude Desktop / Cursor
  / OpenCode. Pairs with any upstream direction source: a fundamental
  analyst, an ML model, a discretionary trader, or Orallexa's own 5-voice
  debate.
version: 1.0.0
author: Alex Xiaoyu Ji
scope: trading:size
depends_on:
  - orallexa engine/risk_sizer.py (upstream Python reference)
  - Byte-identical to Shadow trader-pack risk-sizer.js
---

# Orallexa Risk Sizer

Standalone position sizing for a trade thesis. Direction is an input, not an output.

## When to invoke

The user's request combines all three of:

1. A specific trade thesis with a stated direction — long, short, or no-op.
2. A bankroll amount and volatility read on the underlying (low, medium, high).
3. A calibrated win-rate estimate and average win/loss magnitudes (Kelly parameters).

If any of the three is missing, ask for it. Do not fabricate a Kelly p_win.

## What it does

Applies a fractional Kelly formula (default 0.5 = half-Kelly) with:

1. **Max Kelly cap** — default 25% of bankroll. Never lets a single position exceed this fraction regardless of what Kelly says.
2. **Volatility scalar** — low = 1.0, medium = 0.7, high = 0.4. Scales the Kelly notional down as volatility rises.
3. **Drawdown adjustment** — if the account is currently down, shrinks position size linearly toward the max tolerable drawdown.

If Kelly returns non-positive (bad thesis: p_win too low relative to R:R), verdict is `skip` and position_usd is null. This is the "no_op" case explicit in the sizer contract.

## The named invariant

**The sizer never emits a direction.** Direction is the caller's decision. The sizer only decides fund/skip and position_usd. This is what makes it composable — you can pair it with any direction source (fundamental analyst, ML model, human trader, Orallexa's 5-voice debate).

Contract test coverage in `tests/test_risk_sizer_contract.py` (7 pinned invariants).

## Input schema

```json
{
  "direction": "long" | "short" | "no_op",
  "directional_confidence": 0.72,
  "bankroll_usd": 10000,
  "volatility_regime": "low" | "medium" | "high",
  "kelly_p_win": 0.55,
  "kelly_avg_win_pct": 0.04,
  "kelly_avg_loss_pct": 0.02,
  "current_drawdown_pct": 0.0,
  "max_kelly_cap": 0.25
}
```

## Output schema

```json
{
  "voice": "Risk Sizer",
  "verdict": "fund" | "skip",
  "position_usd": 350.00,
  "kelly_notional": 500.00,
  "volatility_scalar": 0.7,
  "rationale": "Kelly=500 (p_win=0.55, R=2:1)...",
  "metrics": { "direction": "long", ... }
}
```

## Approval boundary

The Judge that supplies direction is upstream and out of scope for this skill. If the direction is no_op, the sizer returns skip immediately without running Kelly. If Kelly returns negative for a stated long/short direction, the sizer returns skip and cites the specific p_win / R:R that failed break-even in the rationale.

## Non-goals

- Not a directional signal. Never tells you whether to buy or sell.
- Not a portfolio-level VaR or concentration limit. Position-level only.
- Not tied to a specific broker or execution venue. Returns a dollar amount; you decide how to fill.
- Not a full trading system. Pairs with an upstream Judge (5-voice debate, LLM analyst, or a human).

## Reference

- Orallexa `engine/risk_sizer.py` — the Python source of truth.
- FinPos: A Dual-Agent Framework for Financial Decision-Making. arXiv:2510.27251.
- Byte-identical port at `shadow-mentor/lib/personas/trader-pack/risk-sizer.js` in the Shadow banking-compliance repo.
