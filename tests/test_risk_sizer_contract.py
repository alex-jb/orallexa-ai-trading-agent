"""
Risk Sizer voice contract tests — v1.2.0, 2026-07-07.

Reference: FinPos (arXiv 2510.27251) design + design doc at
docs/roadmap/v1.2.0-finpos-dual-agent.md.

Named contract:
  1. size_position() MUST NOT return a direction
  2. size_position() respects Kelly max-cap
  3. size_position() returns skip on no_op direction
  4. size_position() scales inversely with volatility regime
  5. size_position() shrinks under drawdown-adjusted Kelly
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from engine.risk_sizer import (  # noqa: E402
    RiskSizerInput,
    RiskSizerOutput,
    size_position,
)


def _base_input(**overrides) -> RiskSizerInput:
    """Reasonable-defaults RiskSizerInput for use in each test."""
    defaults = dict(
        direction="long",
        directional_confidence=0.72,
        bankroll_usd=10_000.0,
        volatility_regime="medium",
        kelly_p_win=0.55,
        kelly_avg_win_pct=0.04,
        kelly_avg_loss_pct=0.02,
        current_drawdown_pct=0.0,
        max_kelly_cap=0.25,
    )
    defaults.update(overrides)
    return RiskSizerInput(**defaults)


# --------------------------------------------------------------------------
# Contract test 1: Risk Sizer NEVER emits a direction
# --------------------------------------------------------------------------
def test_risk_sizer_never_emits_direction():
    for direction in ("long", "short", "no_op"):
        out = size_position(_base_input(direction=direction))
        # Verdict is fund/skip — NEVER a direction like long/short/no_op.
        assert out.verdict in ("fund", "skip"), (
            f"verdict must be fund/skip, got {out.verdict}"
        )
        # The output object has no direction field — Judge owns direction.
        assert not hasattr(out, "direction") or getattr(out, "direction", None) is None, (
            "Risk Sizer must not expose a direction field"
        )
        # The direction from input passes through the metrics dict but is
        # NOT part of the sizer's opinion — it's audit metadata.
        assert out.metrics.get("direction") == direction, (
            "Input direction should be preserved in metrics for audit"
        )


# --------------------------------------------------------------------------
# Contract test 2: Kelly cap is respected
# --------------------------------------------------------------------------
def test_risk_sizer_respects_kelly_cap():
    for cap in (0.10, 0.25, 0.40):
        out = size_position(_base_input(max_kelly_cap=cap, volatility_regime="low"))
        if out.verdict == "fund":
            assert out.position_usd is not None
            assert out.position_usd <= cap * 10_000.0 + 0.01, (
                f"position {out.position_usd} exceeds cap {cap * 10000}"
            )


# --------------------------------------------------------------------------
# Contract test 3: no_op skips
# --------------------------------------------------------------------------
def test_risk_sizer_skips_on_no_op():
    out = size_position(_base_input(direction="no_op"))
    assert out.verdict == "skip"
    assert out.position_usd is None
    assert "no_op" in out.rationale.lower()


# --------------------------------------------------------------------------
# Contract test 4: Position scales inversely with volatility
# --------------------------------------------------------------------------
def test_risk_sizer_scales_inversely_with_volatility():
    low = size_position(_base_input(volatility_regime="low"))
    med = size_position(_base_input(volatility_regime="medium"))
    high = size_position(_base_input(volatility_regime="high"))

    # All should fund (positive Kelly given p_win=0.55, R=2:1).
    assert low.verdict == "fund"
    assert med.verdict == "fund"
    assert high.verdict == "fund"

    # Strictly monotone decreasing.
    assert low.position_usd > med.position_usd > high.position_usd, (
        f"low={low.position_usd}, med={med.position_usd}, high={high.position_usd}"
    )


# --------------------------------------------------------------------------
# Contract test 5: Drawdown shrinks position
# --------------------------------------------------------------------------
def test_risk_sizer_shrinks_under_drawdown():
    no_dd = size_position(_base_input(current_drawdown_pct=0.0))
    dd_10 = size_position(_base_input(current_drawdown_pct=0.10))
    dd_50 = size_position(_base_input(current_drawdown_pct=0.50))

    # All fund (positive Kelly).
    assert no_dd.verdict == "fund"
    # Under 10% DD, position should be smaller than at 0% (Kelly scales down).
    assert dd_10.position_usd is None or (
        dd_10.position_usd < no_dd.position_usd
    ), f"dd_10={dd_10.position_usd}, no_dd={no_dd.position_usd}"
    # Under 50% DD, position should be even smaller or skipped entirely.
    if dd_50.verdict == "fund":
        assert dd_50.position_usd < dd_10.position_usd or dd_50.position_usd < 100.0
    else:
        assert dd_50.verdict == "skip"


# --------------------------------------------------------------------------
# Bonus: negative-Kelly parameters skip cleanly (bad-strategy input)
# --------------------------------------------------------------------------
def test_risk_sizer_skips_on_negative_kelly():
    # p_win 0.30 with 1:1 payoff → negative Kelly, MUST skip
    out = size_position(_base_input(
        kelly_p_win=0.30,
        kelly_avg_win_pct=0.02,
        kelly_avg_loss_pct=0.02,
    ))
    assert out.verdict == "skip"
    assert out.position_usd is None
    assert "non-positive" in out.rationale.lower() or "break-even" in out.rationale.lower()


# --------------------------------------------------------------------------
# Bonus: rationale is human-readable + cites Kelly parameters
# --------------------------------------------------------------------------
def test_risk_sizer_rationale_is_readable():
    out = size_position(_base_input())
    if out.verdict == "fund":
        # A bank counsel should be able to read this rationale in 5 seconds.
        assert "kelly" in out.rationale.lower()
        assert "volatility" in out.rationale.lower()
        # And should see that direction was NOT part of the sizer's opinion.
        assert (
            "direction was fixed" in out.rationale.lower()
            or "judge" in out.rationale.lower()
        )
