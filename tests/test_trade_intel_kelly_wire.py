"""
tests/test_trade_intel_kelly_wire.py
──────────────────────────────────────────────────────────────────
Pins the Kelly-sizing wire-up into markets/auto/trade_intel.py
(Tier-2 #11 wire-up, shipped 2026-07-02).

Contract:
  - setup_to_sizing_notional is 100% back-compat when no Kelly kwargs
    are passed (existing callers see identical numbers)
  - Passing kelly_p_win + kelly_avg_win_pct + kelly_avg_loss_pct
    together opts into Kelly sizing
  - Kelly sizing preserves side logic (long/short/pass) from setup
  - Zero edge → zero notional
  - Negative edge → zero notional (never a short bet)
  - Notional capped at MAX_KELLY_FRACTION_CAP × account
  - Drawdown adjustment shrinks the notional
  - Partial Kelly kwargs (only 1 or 2 present) fall back to fixed bucket
"""
from __future__ import annotations

import pytest

from markets.auto.trade_intel import setup_to_sizing_notional
from engine.kelly_sizing import MAX_KELLY_FRACTION_CAP


# ═══════════════════════════════════════════════════════════════
# Back-compat: no Kelly kwargs → identical to legacy behavior
# ═══════════════════════════════════════════════════════════════

def test_no_kelly_kwargs_uses_fixed_bucket():
    """Full sizing without Kelly → same $2000 notional as pre-wire-up
    ($10k account × min(15 × 0.015 × 10k / 10k, 0.20) = $2000 cap)."""
    notional, side = setup_to_sizing_notional("Trend", "Full", 10_000)
    assert notional == 2_000  # 20% cap on $10k
    assert side == "long"


def test_no_kelly_kwargs_short_side_preserved():
    """Short-half + Breakdown → still 'short' after wire-up."""
    notional, side = setup_to_sizing_notional("Breakdown", "Short-half", 10_000)
    assert side == "short"
    assert notional > 0


def test_no_kelly_kwargs_pass():
    """Sizing label not in the buckets → notional 0, side 'pass'."""
    notional, side = setup_to_sizing_notional("Unknown", "tiny", 10_000)
    assert notional == 0
    assert side == "pass"


# ═══════════════════════════════════════════════════════════════
# Kelly opt-in path
# ═══════════════════════════════════════════════════════════════

def test_kelly_kwargs_use_kelly_path():
    """60% win with 1:1 payoff → Half-Kelly f* = 0.10 → $1000 on $10k account."""
    notional, side = setup_to_sizing_notional(
        "Trend", "Full", 10_000,
        kelly_p_win=0.6,
        kelly_avg_win_pct=0.05,
        kelly_avg_loss_pct=0.05,
    )
    assert abs(notional - 1_000) < 0.01
    assert side == "long"


def test_kelly_zero_edge_zero_notional():
    """50/50 → zero edge → Kelly overrides fixed bucket down to $0."""
    notional, side = setup_to_sizing_notional(
        "Trend", "Full", 10_000,
        kelly_p_win=0.5,
        kelly_avg_win_pct=0.05,
        kelly_avg_loss_pct=0.05,
    )
    assert notional == 0
    assert side == "pass"


def test_kelly_negative_edge_zero_notional():
    """40% win with symmetric payoff → negative edge → $0 not a short bet."""
    notional, side = setup_to_sizing_notional(
        "Trend", "Full", 10_000,
        kelly_p_win=0.4,
        kelly_avg_win_pct=0.05,
        kelly_avg_loss_pct=0.05,
    )
    assert notional == 0
    assert side == "pass"


def test_kelly_notional_capped_at_max_kelly_fraction():
    """Very edgy bet → notional never exceeds MAX_KELLY_FRACTION_CAP × account."""
    notional, side = setup_to_sizing_notional(
        "Trend", "Full", 10_000,
        kelly_p_win=0.99,
        kelly_avg_win_pct=0.50,
        kelly_avg_loss_pct=0.05,
    )
    assert notional <= 10_000 * MAX_KELLY_FRACTION_CAP + 0.001


def test_kelly_short_side_preserved():
    """Kelly path + Short sizing_label → side is 'short'."""
    notional, side = setup_to_sizing_notional(
        "Breakdown", "Short-half", 10_000,
        kelly_p_win=0.6,
        kelly_avg_win_pct=0.05,
        kelly_avg_loss_pct=0.05,
    )
    assert notional > 0
    assert side == "short"


def test_kelly_drawdown_shrinks_notional():
    """At 7.5% drawdown (half of default 15% max), Kelly should be ~half
    the no-drawdown notional (linear scaling)."""
    n_base, _ = setup_to_sizing_notional(
        "Trend", "Full", 10_000,
        kelly_p_win=0.6,
        kelly_avg_win_pct=0.05,
        kelly_avg_loss_pct=0.05,
        kelly_current_drawdown_pct=0.0,
    )
    n_dd, _ = setup_to_sizing_notional(
        "Trend", "Full", 10_000,
        kelly_p_win=0.6,
        kelly_avg_win_pct=0.05,
        kelly_avg_loss_pct=0.05,
        kelly_current_drawdown_pct=7.5,
    )
    assert abs(n_dd - 0.5 * n_base) < 0.01


def test_kelly_at_max_dd_notional_zero():
    """At the 15% max drawdown gate, Kelly should return $0."""
    n, side = setup_to_sizing_notional(
        "Trend", "Full", 10_000,
        kelly_p_win=0.6,
        kelly_avg_win_pct=0.05,
        kelly_avg_loss_pct=0.05,
        kelly_current_drawdown_pct=15.0,
    )
    assert n == 0
    assert side == "pass"


# ═══════════════════════════════════════════════════════════════
# Partial Kelly kwargs → fall through to fixed bucket
# ═══════════════════════════════════════════════════════════════

def test_partial_kelly_kwargs_falls_back_to_fixed_bucket():
    """Only kelly_p_win passed → other required kwargs missing →
    fixed-bucket path fires unchanged."""
    n_kelly, _ = setup_to_sizing_notional(
        "Trend", "Full", 10_000,
        kelly_p_win=0.6,   # only one — kelly path won't activate
    )
    n_default, _ = setup_to_sizing_notional("Trend", "Full", 10_000)
    assert n_kelly == n_default


# ═══════════════════════════════════════════════════════════════
# Full Kelly (fraction=1.0) works
# ═══════════════════════════════════════════════════════════════

def test_full_kelly_fraction_1_0_uses_full_math():
    """kelly_fraction=1.0 → full Kelly. On 60/40 symmetric bet f*=0.20 →
    $2000 on $10k account (Half-Kelly gives $1000)."""
    n, _ = setup_to_sizing_notional(
        "Trend", "Full", 10_000,
        kelly_p_win=0.6,
        kelly_avg_win_pct=0.05,
        kelly_avg_loss_pct=0.05,
        kelly_fraction=1.0,
    )
    # 0.20 × 10_000 = 2_000
    assert abs(n - 2_000) < 0.01
