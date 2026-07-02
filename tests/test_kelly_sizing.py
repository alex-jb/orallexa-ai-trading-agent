"""
tests/test_kelly_sizing.py
──────────────────────────────────────────────────────────────────
Pins the Kelly sizing contract shipped 2026-07-02 (Tier-2 #11).

These tests enforce the Kelly-math invariants that keep the sizing
layer from silently taking oversized positions:
  - never > max_cap
  - never < 0
  - never NaN or Inf
  - degenerate inputs (p_win = 0/1, zero loss magnitude) → zero
  - half-Kelly is exactly 0.5 × full
  - drawdown scaling monotone
"""
from __future__ import annotations

import math

import pytest

from engine.kelly_sizing import (
    DEFAULT_KELLY_FRACTION,
    MAX_KELLY_FRACTION_CAP,
    drawdown_adjusted_kelly,
    fractional_kelly,
    full_kelly_fraction,
    kelly_notional,
)


# ═══════════════════════════════════════════════════════════════
# full_kelly_fraction
# ═══════════════════════════════════════════════════════════════

def test_full_kelly_symmetric_no_edge():
    """p_win=0.5, symmetric payoff → zero edge → zero size."""
    assert full_kelly_fraction(0.5, 0.05, 0.05) == 0.0


def test_full_kelly_positive_edge_returns_positive():
    """60% win with 1:1 payoff → f* = 2*0.6 - 1 = 0.2."""
    f = full_kelly_fraction(0.6, 0.05, 0.05)
    assert abs(f - 0.2) < 0.001


def test_full_kelly_asymmetric_upside():
    """60% win with 2:1 upside (win $2 vs lose $1) → f* = (0.6*2 - 0.4)/2 = 0.4."""
    f = full_kelly_fraction(0.6, 0.10, 0.05)
    assert abs(f - 0.4) < 0.001


def test_full_kelly_negative_edge_returns_zero():
    """40% win with 1:1 payoff → negative expected → zero size (not short bet)."""
    assert full_kelly_fraction(0.4, 0.05, 0.05) == 0.0


def test_full_kelly_certain_win_capped_by_math():
    """As p_win → 1, f* → 1.0. The safety cap MAX_KELLY_FRACTION_CAP
    is enforced by fractional_kelly, not by full_kelly_fraction itself."""
    f = full_kelly_fraction(0.99, 0.05, 0.05)
    assert 0.9 < f < 1.0


@pytest.mark.parametrize("p", [0.0, 1.0, -0.1, 1.1, float("nan"), float("inf")])
def test_full_kelly_degenerate_p_returns_zero(p):
    """Any p outside (0, 1) exclusive gets you zero — no accidental
    infinities, no negative sizes."""
    assert full_kelly_fraction(p, 0.05, 0.05) == 0.0


def test_full_kelly_zero_loss_returns_zero():
    """avg_loss_pct = 0 → b = ∞ → skip. Kelly on garbage inputs must
    not produce infinite positions."""
    assert full_kelly_fraction(0.6, 0.05, 0.0) == 0.0


def test_full_kelly_never_nan():
    """No combination of finite positive inputs should produce NaN."""
    for p in [0.51, 0.6, 0.7, 0.9, 0.99]:
        for w in [0.01, 0.05, 0.1, 0.5]:
            for lo in [0.01, 0.05, 0.1, 0.5]:
                f = full_kelly_fraction(p, w, lo)
                assert not math.isnan(f)
                assert not math.isinf(f)
                assert f >= 0.0


# ═══════════════════════════════════════════════════════════════
# fractional_kelly + safety cap
# ═══════════════════════════════════════════════════════════════

def test_half_kelly_is_exactly_half_of_full():
    """0.5 fraction on a bet whose full Kelly is 0.20 → 0.10."""
    full = full_kelly_fraction(0.6, 0.05, 0.05)  # ~0.20
    half = fractional_kelly(0.6, 0.05, 0.05, fraction=0.5, max_cap=1.0)
    assert abs(half - 0.5 * full) < 1e-9


def test_default_fraction_is_half_kelly():
    """DEFAULT_KELLY_FRACTION == 0.5 — professional consensus."""
    assert DEFAULT_KELLY_FRACTION == 0.5


def test_max_cap_enforced():
    """Very edgy bet whose Half-Kelly would exceed cap gets clipped."""
    # 95% win with 5:1 upside → full Kelly ~0.94, Half-Kelly ~0.47.
    f = fractional_kelly(0.95, 0.25, 0.05, fraction=0.5)
    assert f <= MAX_KELLY_FRACTION_CAP
    assert f == MAX_KELLY_FRACTION_CAP  # actually clipped


def test_max_cap_custom_value_respected():
    """Custom lower cap is honored."""
    f = fractional_kelly(0.95, 0.25, 0.05, fraction=0.5, max_cap=0.10)
    assert f == 0.10


def test_negative_fraction_raises():
    """Nonsensical negative fraction → ValueError, not silent zero."""
    with pytest.raises(ValueError):
        fractional_kelly(0.6, 0.05, 0.05, fraction=-0.1)


# ═══════════════════════════════════════════════════════════════
# drawdown_adjusted_kelly
# ═══════════════════════════════════════════════════════════════

def test_dd_kelly_zero_drawdown_equals_fractional_kelly():
    """At 0% DD, drawdown adjustment is a no-op."""
    plain = fractional_kelly(0.6, 0.05, 0.05, fraction=0.5)
    dd = drawdown_adjusted_kelly(
        0.6, 0.05, 0.05,
        current_drawdown_pct=0.0,
        fraction=0.5,
    )
    assert abs(dd - plain) < 1e-9


def test_dd_kelly_at_max_dd_is_zero():
    """At (or past) max tolerable DD, size drops to zero."""
    dd = drawdown_adjusted_kelly(
        0.6, 0.05, 0.05,
        current_drawdown_pct=15.0,
        max_tolerable_drawdown_pct=15.0,
        fraction=0.5,
    )
    assert dd == 0.0


def test_dd_kelly_scales_linearly_between():
    """At half of max DD, size should be roughly half the baseline."""
    baseline = drawdown_adjusted_kelly(
        0.6, 0.05, 0.05,
        current_drawdown_pct=0.0,
        max_tolerable_drawdown_pct=15.0,
        fraction=0.5,
    )
    halfway = drawdown_adjusted_kelly(
        0.6, 0.05, 0.05,
        current_drawdown_pct=7.5,
        max_tolerable_drawdown_pct=15.0,
        fraction=0.5,
    )
    assert abs(halfway - 0.5 * baseline) < 1e-9


def test_dd_kelly_negative_dd_treated_as_zero():
    """Negative DD (i.e. currently above high-water mark) is not a
    'special bonus' — same as zero DD."""
    dd = drawdown_adjusted_kelly(
        0.6, 0.05, 0.05,
        current_drawdown_pct=-3.0,
        fraction=0.5,
    )
    baseline = drawdown_adjusted_kelly(
        0.6, 0.05, 0.05,
        current_drawdown_pct=0.0,
        fraction=0.5,
    )
    assert dd == baseline


# ═══════════════════════════════════════════════════════════════
# kelly_notional (the applied API)
# ═══════════════════════════════════════════════════════════════

def test_kelly_notional_returns_correct_dollar_amount():
    """On $10k account, Half-Kelly at f=0.10 → $1,000 notional."""
    ticket = kelly_notional(10_000, 0.6, 0.05, 0.05)
    # Half of 0.20 f* = 0.10 → $1,000
    assert abs(ticket.notional_usd - 1_000) < 0.01
    assert ticket.method == "half_kelly"


def test_kelly_notional_zero_edge_zero_position():
    """No edge → no position."""
    ticket = kelly_notional(10_000, 0.5, 0.05, 0.05)
    assert ticket.notional_usd == 0
    assert ticket.fraction == 0


def test_kelly_notional_zero_account_zero_position():
    """No money → no bets. Also no crash."""
    ticket = kelly_notional(0, 0.6, 0.05, 0.05)
    assert ticket.notional_usd == 0
    assert ticket.method == "disabled_zero_account"


def test_kelly_notional_dd_adjusts_method_label():
    """When DD adjustment kicks in, method label reflects it — so
    downstream reports can bucket by sizing method."""
    ticket = kelly_notional(
        10_000, 0.6, 0.05, 0.05,
        current_drawdown_pct=5.0,
    )
    assert ticket.method == "dd_adj_kelly"


def test_kelly_notional_never_exceeds_max_cap_of_account():
    """No matter how edgy the bet, notional ≤ MAX_KELLY_FRACTION_CAP × account."""
    ticket = kelly_notional(10_000, 0.99, 0.50, 0.05)  # huge edge
    assert ticket.notional_usd <= 10_000 * MAX_KELLY_FRACTION_CAP + 0.001


def test_full_kelly_method_label():
    """Using fraction=1.0 labels as full_kelly."""
    ticket = kelly_notional(10_000, 0.6, 0.05, 0.05, fraction=1.0)
    assert ticket.method == "full_kelly"


def test_custom_fraction_gets_labeled_variant():
    """Nonstandard fraction gets a descriptive label."""
    ticket = kelly_notional(10_000, 0.6, 0.05, 0.05, fraction=0.25)
    assert "0.25" in ticket.method
