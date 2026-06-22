"""Tests for engine/insider_signal.py — covers the 3 documented patterns:
  - ASTS CFO single sale (-)
  - BKSY CEO+CFO same-day paired sales (- with cluster multiplier)
  - Below threshold / wrong-window noise filtering
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import pytest  # noqa: E402

from engine.insider_signal import (  # noqa: E402
    ABS_DELTA_CAP,
    CSUITE_CLUSTER_MULTIPLIER,
    PER_EVENT_BASE_DELTA,
    InsiderEvent,
    apply_insider_adjustment,
    compute_insider_signal,
)


# Anchor today so the tests don't drift as the calendar rolls.
TODAY = date(2026, 6, 22)


def _ev(ticker, ago_days, position, direction, value, insider=""):
    return {
        "ticker": ticker,
        "date": (TODAY - timedelta(days=ago_days)).isoformat(),
        "position": position,
        "direction": direction,
        "shares": int(value / 100),
        "value_usd": value,
        "insider": insider,
    }


# ────────────────────────────────────────────────────────────────────
# ASTS — single CFO sale, brief 2026-06-20 named case
# ────────────────────────────────────────────────────────────────────

class TestAstsCfoSale:
    """CFO single $430k sale should produce a moderate negative tilt."""

    def test_negative_delta(self):
        events = [_ev("ASTS", 11, "Chief Financial Officer",
                      "sale", 430_000, "Andrew Johnson")]
        sig = compute_insider_signal("ASTS", events, today=TODAY)
        assert sig.p_up_delta < 0
        assert sig.events_considered == 1
        assert not sig.cluster_bonus_applied

    def test_magnitude_matches_position_weight(self):
        events = [_ev("ASTS", 11, "Chief Financial Officer",
                      "sale", 430_000, "Andrew Johnson")]
        sig = compute_insider_signal("ASTS", events, today=TODAY)
        # CFO weight = 0.95, direction = -1, base = 0.04 → -0.038
        assert abs(sig.p_up_delta - (-0.95 * PER_EVENT_BASE_DELTA)) < 1e-6


# ────────────────────────────────────────────────────────────────────
# BKSY — CEO + CFO same-day paired sales, brief 2026-06-20 named case
# ────────────────────────────────────────────────────────────────────

class TestBksyCsuitePairedSales:
    """Same-day CEO+CFO sales hit the cluster multiplier."""

    def test_cluster_bonus_applied(self):
        events = [
            _ev("BKSY", 12, "Chief Executive Officer",
                "sale", 500_000, "Brian O'Toole"),
            _ev("BKSY", 12, "Chief Financial Officer",
                "sale", 500_000, "Henry DuBois"),
        ]
        sig = compute_insider_signal("BKSY", events, today=TODAY)
        assert sig.cluster_bonus_applied is True
        assert sig.events_considered == 2
        assert sig.p_up_delta < 0

    def test_cluster_magnitude_larger_than_individual_sum(self):
        paired_events = [
            _ev("BKSY", 12, "Chief Executive Officer", "sale", 500_000, "A"),
            _ev("BKSY", 12, "Chief Financial Officer", "sale", 500_000, "B"),
        ]
        non_paired_events = [
            _ev("BKSY", 12, "Chief Executive Officer", "sale", 500_000, "A"),
            _ev("BKSY", 5,  "Chief Financial Officer", "sale", 500_000, "B"),
        ]
        paired = compute_insider_signal("BKSY", paired_events, today=TODAY).p_up_delta
        spread = compute_insider_signal("BKSY", non_paired_events, today=TODAY).p_up_delta
        # Same total event mass, paired-on-same-day should be MORE negative
        assert abs(paired) > abs(spread)

    def test_single_csuite_no_cluster(self):
        events = [_ev("BKSY", 12, "Chief Executive Officer",
                      "sale", 500_000, "Solo CEO")]
        sig = compute_insider_signal("BKSY", events, today=TODAY)
        assert sig.cluster_bonus_applied is False


# ────────────────────────────────────────────────────────────────────
# Filtering — window, min value, position seniority
# ────────────────────────────────────────────────────────────────────

class TestFiltering:
    """Noise filters should drop out-of-window, below-threshold, and
    non-material-role events."""

    def test_out_of_window_dropped(self):
        events = [_ev("X", 30, "Chief Executive Officer", "sale", 1_000_000)]
        sig = compute_insider_signal("X", events, window_days=14, today=TODAY)
        assert sig.events_considered == 0
        assert sig.p_up_delta == 0

    def test_below_min_value_dropped(self):
        events = [_ev("X", 3, "Chief Executive Officer", "sale", 10_000)]
        sig = compute_insider_signal("X", events, today=TODAY)
        assert sig.events_considered == 0

    def test_unknown_position_dropped(self):
        events = [_ev("X", 3, "Janitor", "sale", 500_000)]
        sig = compute_insider_signal("X", events, today=TODAY)
        assert sig.events_considered == 0

    def test_unknown_direction_dropped(self):
        events = [_ev("X", 3, "Chief Executive Officer", "other", 500_000)]
        sig = compute_insider_signal("X", events, today=TODAY)
        assert sig.events_considered == 0

    def test_wrong_ticker_dropped(self):
        events = [_ev("OTHER", 3, "CEO", "sale", 500_000)]
        sig = compute_insider_signal("ASTS", events, today=TODAY)
        assert sig.events_considered == 0


# ────────────────────────────────────────────────────────────────────
# Caps + direction sanity
# ────────────────────────────────────────────────────────────────────

class TestCapsAndDirection:

    def test_purchase_positive(self):
        events = [_ev("X", 3, "CEO", "purchase", 1_000_000)]
        sig = compute_insider_signal("X", events, today=TODAY)
        assert sig.p_up_delta > 0

    def test_cap_at_abs_delta_cap(self):
        events = [_ev("X", i, "CEO", "sale", 1_000_000) for i in range(10)]
        sig = compute_insider_signal("X", events, today=TODAY)
        assert abs(sig.p_up_delta) <= ABS_DELTA_CAP + 1e-9


# ────────────────────────────────────────────────────────────────────
# Integration helper
# ────────────────────────────────────────────────────────────────────

class TestApplyAdjustment:

    def test_clamp_low(self):
        events = [_ev("X", i, "CEO", "sale", 1_000_000) for i in range(10)]
        sig = compute_insider_signal("X", events, today=TODAY)
        # baseline 0.10, large negative signal → would go below 0
        adj = apply_insider_adjustment(0.10, sig)
        assert 0 <= adj <= 1

    def test_clamp_high(self):
        events = [_ev("X", i, "CEO", "purchase", 1_000_000) for i in range(10)]
        sig = compute_insider_signal("X", events, today=TODAY)
        adj = apply_insider_adjustment(0.95, sig)
        assert adj <= 1

    def test_unclamped_returns_raw(self):
        events = [_ev("X", i, "CEO", "sale", 1_000_000) for i in range(10)]
        sig = compute_insider_signal("X", events, today=TODAY)
        adj = apply_insider_adjustment(0.10, sig, clamp_to_unit=False)
        assert adj == 0.10 + sig.p_up_delta
