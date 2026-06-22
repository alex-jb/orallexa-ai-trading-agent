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
    wrap_signal_with_insider,
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


# ────────────────────────────────────────────────────────────────────
# Integration wrapper — wrap_signal_with_insider
# ────────────────────────────────────────────────────────────────────

class TestWrapSignalWithInsider:
    """Decorator-style integration into any signal-emitter's dict output."""

    def test_no_events_passthrough(self):
        base = {"up_probability": 0.55, "down_probability": 0.30}
        out = wrap_signal_with_insider(base, [], "ASTS", today=TODAY)
        assert out["up_probability"] == 0.55
        assert out["down_probability"] == 0.30
        assert out["insider_adjustment"]["p_up_delta"] == 0
        assert out["insider_adjustment"]["events_considered"] == 0

    def test_negative_signal_shifts_mass_up_to_down(self):
        base = {"up_probability": 0.55, "down_probability": 0.30}
        events = [_ev("ASTS", 11, "CFO", "sale", 430_000, "Andrew Johnson")]
        out = wrap_signal_with_insider(base, events, "ASTS", today=TODAY)
        # CFO sale → p_up should drop, p_down should rise by same magnitude
        assert out["up_probability"] < 0.55
        assert out["down_probability"] > 0.30
        delta = out["up_probability"] - 0.55
        # Sum preserved (mass conservation)
        assert abs((out["up_probability"] + out["down_probability"])
                   - (0.55 + 0.30)) < 1e-6
        # Delta matches signal
        assert abs(delta - out["insider_adjustment"]["p_up_delta"]) < 1e-6

    def test_positive_signal_shifts_mass_down_to_up(self):
        base = {"up_probability": 0.40, "down_probability": 0.45}
        events = [_ev("X", 3, "CEO", "purchase", 1_000_000)]
        out = wrap_signal_with_insider(base, events, "X", today=TODAY)
        assert out["up_probability"] > 0.40
        assert out["down_probability"] < 0.45

    def test_does_not_mutate_input(self):
        base = {"up_probability": 0.55, "down_probability": 0.30}
        original_keys = set(base.keys())
        events = [_ev("ASTS", 11, "CFO", "sale", 430_000)]
        wrap_signal_with_insider(base, events, "ASTS", today=TODAY)
        # Original dict unchanged
        assert base["up_probability"] == 0.55
        assert base["down_probability"] == 0.30
        assert set(base.keys()) == original_keys

    def test_preserves_other_fields(self):
        base = {
            "up_probability": 0.55,
            "down_probability": 0.30,
            "signal": 1,
            "confidence": 67.5,
            "expected_return": 0.012,
        }
        events = [_ev("ASTS", 11, "CFO", "sale", 430_000)]
        out = wrap_signal_with_insider(base, events, "ASTS", today=TODAY)
        # All non-probability fields pass through unchanged
        assert out["signal"] == 1
        assert out["confidence"] == 67.5
        assert out["expected_return"] == 0.012

    def test_rationale_attached(self):
        base = {"up_probability": 0.55, "down_probability": 0.30}
        events = [_ev("ASTS", 11, "CFO", "sale", 430_000, "Andrew Johnson")]
        out = wrap_signal_with_insider(base, events, "ASTS", today=TODAY)
        assert out["insider_adjustment"]["events_considered"] == 1
        assert len(out["insider_adjustment"]["rationale"]) >= 1
        assert "CFO" in out["insider_adjustment"]["rationale"][0] \
            or "Financial" in out["insider_adjustment"]["rationale"][0]

    def test_clamp_at_zero(self):
        # Baseline near zero + large negative delta should clamp
        base = {"up_probability": 0.01, "down_probability": 0.95}
        events = [_ev("X", i, "CEO", "sale", 1_000_000) for i in range(10)]
        out = wrap_signal_with_insider(base, events, "X", today=TODAY)
        assert out["up_probability"] >= 0
        assert out["down_probability"] <= 1

    def test_rejects_non_dict(self):
        with pytest.raises(TypeError):
            wrap_signal_with_insider("not a dict", [], "X", today=TODAY)  # type: ignore[arg-type]

    def test_custom_field_names(self):
        """Some signal generators use different key names."""
        base = {"p_up": 0.55, "p_down": 0.30}
        events = [_ev("ASTS", 11, "CFO", "sale", 430_000)]
        out = wrap_signal_with_insider(
            base, events, "ASTS", today=TODAY,
            up_key="p_up", down_key="p_down",
        )
        assert out["p_up"] < 0.55
        assert out["p_down"] > 0.30
