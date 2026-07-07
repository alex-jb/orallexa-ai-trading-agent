"""
Risk Sizer voice — v1.2.0, 2026-07-07.

Reference: FinPos (arXiv 2510.27251) — separating directional reasoning
from position sizing outperforms conflated Judge on both dimensions.

This function:
  - Runs AFTER the 5-voice debate resolves to a direction
  - Sees direction as INPUT (never challenges it)
  - Sees volatility regime + portfolio state + Kelly parameters
  - Outputs ONLY a position size in USD (or None if unfundable)
  - Refuses to opine on direction (pinned by test/test_risk_sizer_contract.py)

Design skeleton at docs/roadmap/v1.2.0-finpos-dual-agent.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from .kelly_sizing import kelly_notional

Direction = Literal["long", "short", "no_op"]
VolRegime = Literal["low", "medium", "high"]


@dataclass
class RiskSizerInput:
    """Everything the Risk Sizer voice needs to size a position.

    Note: `direction` is INPUT, not something to opine on. See the contract
    tests.
    """
    direction: Direction
    directional_confidence: float  # 0.0-1.0, from Judge
    bankroll_usd: float
    volatility_regime: VolRegime
    kelly_p_win: float  # from historical backtest, per-strategy
    kelly_avg_win_pct: float
    kelly_avg_loss_pct: float
    current_drawdown_pct: float = 0.0  # 0.0 to 1.0
    max_kelly_cap: float = 0.25  # 25% Kelly, per engine/kelly_sizing.py


@dataclass
class RiskSizerOutput:
    """What the Risk Sizer voice returns to the caller."""
    voice: str = "Risk Sizer"
    verdict: Literal["fund", "skip"] = "skip"
    position_usd: Optional[float] = None
    kelly_notional: Optional[float] = None
    volatility_scalar: float = 1.0
    rationale: str = ""
    metrics: dict = field(default_factory=dict)


# Volatility scalars used for the size shrinkage. Grounded in the empirical
# heuristic that positions in high-vol regimes should be ~40-60% of low-vol
# positions for the same Kelly p_win. Extend with real ATR-adjusted numbers
# once the ATR-sweep from 2026-05-29 has enough data (target n>=100 fills).
_VOL_SCALARS: dict[VolRegime, float] = {
    "low": 1.00,
    "medium": 0.70,
    "high": 0.40,
}


def size_position(inp: RiskSizerInput) -> RiskSizerOutput:
    """Compute position size given a pre-decided direction.

    Contract: this function MUST NOT return a direction. The output's
    verdict is "fund" or "skip" — neither is a direction. The direction
    comes from the Judge voice and is carried through unchanged.
    """
    # 1. If direction is no_op, we are done.
    if inp.direction == "no_op":
        return RiskSizerOutput(
            verdict="skip",
            rationale="Judge emitted no_op; no position to size.",
            metrics={"direction": inp.direction},
        )

    # 2. Compute Kelly notional against bankroll. kelly_notional() returns a
    # KellyTicket dataclass with .notional_usd; we extract the number.
    # kelly_notional expects drawdown as PERCENT (e.g. 5.0 for 5%), we accept
    # fraction (0.05 = 5%) as input and convert.
    dd_pct = (
        inp.current_drawdown_pct * 100.0
        if inp.current_drawdown_pct <= 1.0
        else inp.current_drawdown_pct
    )
    ticket = kelly_notional(
        account_usd=inp.bankroll_usd,
        p_win=inp.kelly_p_win,
        avg_win_pct=inp.kelly_avg_win_pct,
        avg_loss_pct=inp.kelly_avg_loss_pct,
        current_drawdown_pct=dd_pct,
    )
    kelly = float(ticket.notional_usd)

    # 3. Cap at max_kelly_cap * bankroll.
    cap = inp.max_kelly_cap * inp.bankroll_usd
    capped = min(kelly, cap)
    if kelly <= 0:
        return RiskSizerOutput(
            verdict="skip",
            kelly_notional=kelly,
            rationale=(
                f"Kelly notional non-positive ({kelly:.2f}); "
                f"p_win={inp.kelly_p_win:.2f} does not clear break-even given "
                f"avg_win={inp.kelly_avg_win_pct:.2%} and "
                f"avg_loss={inp.kelly_avg_loss_pct:.2%}."
            ),
            metrics={
                "kelly_raw": kelly,
                "cap": cap,
                "direction": inp.direction,
            },
        )

    # 4. Apply volatility-regime scalar.
    vol_scalar = _VOL_SCALARS[inp.volatility_regime]
    scaled = capped * vol_scalar

    # 5. Cap once more at bankroll (defensive; kelly_notional should already respect).
    final = min(scaled, inp.bankroll_usd)

    return RiskSizerOutput(
        verdict="fund",
        position_usd=round(final, 2),
        kelly_notional=round(kelly, 2),
        volatility_scalar=vol_scalar,
        rationale=(
            f"Kelly={kelly:.2f} (p_win={inp.kelly_p_win:.2f}, "
            f"avg_win/avg_loss={inp.kelly_avg_win_pct:.2%}/{inp.kelly_avg_loss_pct:.2%}); "
            f"capped at {inp.max_kelly_cap:.0%}={cap:.2f}; "
            f"volatility={inp.volatility_regime} scalar={vol_scalar:.2f}; "
            f"drawdown-adjusted final={final:.2f}. "
            f"Direction was fixed by Judge upstream."
        ),
        metrics={
            "kelly_raw": kelly,
            "cap": cap,
            "vol_scalar": vol_scalar,
            "drawdown_pct": inp.current_drawdown_pct,
            "direction": inp.direction,
        },
    )


# ---------------------------------------------------------------------------
# Public re-exports so tests and callers do not reach into engine internals.
__all__ = [
    "Direction",
    "VolRegime",
    "RiskSizerInput",
    "RiskSizerOutput",
    "size_position",
]
