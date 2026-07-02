"""
tests/test_platt_calibration.py
──────────────────────────────────────────────────────────────────
Pins the Platt calibration contract shipped 2026-07-02 (Tier-2 #7a).

Contract:
  - Fit on n ≥ 30 (p_raw, actual) pairs — smaller raises ValueError
  - Both classes required — all-0 or all-1 raises
  - Fitted calibrator improves training Brier score on
    middle-band-compressed data (the Prophet Arena pathology)
  - identity() returns an approximate no-op mapping
  - calibrate(NaN/Inf) passes through unchanged
"""
from __future__ import annotations

import math
import random

import pytest

from engine.platt_calibration import (
    PlattCalibrator,
    _brier,
    _platt_transform,
    fit,
    identity,
)


# ═══════════════════════════════════════════════════════════════
# Guards
# ═══════════════════════════════════════════════════════════════

def test_fit_below_min_observations_raises():
    """29 pairs → ValueError (below default min_observations=30)."""
    history = [{"forecast_p": 0.5, "actual": 1} for _ in range(15)] + \
              [{"forecast_p": 0.5, "actual": 0} for _ in range(14)]
    with pytest.raises(ValueError, match="30 observations"):
        fit(history)


def test_fit_all_positive_class_raises():
    """All actuals = 1 → ValueError (undefined logistic fit)."""
    history = [{"forecast_p": 0.7, "actual": 1} for _ in range(50)]
    with pytest.raises(ValueError, match="both classes"):
        fit(history)


def test_fit_all_negative_class_raises():
    """All actuals = 0 → ValueError."""
    history = [{"forecast_p": 0.3, "actual": 0} for _ in range(50)]
    with pytest.raises(ValueError, match="both classes"):
        fit(history)


def test_fit_ignores_out_of_range_forecast_p():
    """p_raw ∉ [0, 1] silently dropped; if that leaves <30 → raise."""
    history = (
        [{"forecast_p": 0.4, "actual": 1} for _ in range(15)]
        + [{"forecast_p": 0.6, "actual": 0} for _ in range(15)]
        + [{"forecast_p": 1.5, "actual": 1}]   # dropped
        + [{"forecast_p": -0.2, "actual": 0}]  # dropped
    )
    result = fit(history)  # 30 valid observations = exactly at min
    assert result.n_train == 30


def test_fit_ignores_nan_forecast_p():
    """NaN inputs silently dropped."""
    history = (
        [{"forecast_p": 0.4, "actual": 1} for _ in range(15)]
        + [{"forecast_p": 0.6, "actual": 0} for _ in range(15)]
        + [{"forecast_p": float("nan"), "actual": 1}]  # dropped
    )
    result = fit(history)
    assert result.n_train == 30


def test_fit_ignores_missing_fields():
    """Rows without forecast_p or actual silently dropped."""
    history = (
        [{"forecast_p": 0.4, "actual": 1} for _ in range(15)]
        + [{"forecast_p": 0.6, "actual": 0} for _ in range(15)]
        + [{"forecast_p": 0.5}]                  # missing actual
        + [{"actual": 1}]                        # missing forecast_p
    )
    result = fit(history)
    assert result.n_train == 30


# ═══════════════════════════════════════════════════════════════
# Middle-band compression pathology (Prophet Arena)
# ═══════════════════════════════════════════════════════════════

def _compressed_history(n_per_bucket: int = 40, seed: int = 1):
    """Simulate the Prophet Arena Haiku pathology:
       - true low-prob events (~0.1) predicted at ~0.30 (compressed up)
       - true high-prob events (~0.9) predicted at ~0.70 (compressed down)
       - true mid-prob events (~0.5) predicted at ~0.55 (roughly right)
    Result: raw Brier > 0.20 while calibrated Brier should improve."""
    rng = random.Random(seed)
    history = []
    # Low: true 0.1, predicted 0.30 (over-called)
    for _ in range(n_per_bucket):
        history.append({"forecast_p": 0.30,
                        "actual": 1.0 if rng.random() < 0.10 else 0.0})
    # High: true 0.9, predicted 0.70 (under-called)
    for _ in range(n_per_bucket):
        history.append({"forecast_p": 0.70,
                        "actual": 1.0 if rng.random() < 0.90 else 0.0})
    # Mid: true 0.5, predicted 0.55 (roughly right)
    for _ in range(n_per_bucket):
        history.append({"forecast_p": 0.55,
                        "actual": 1.0 if rng.random() < 0.50 else 0.0})
    return history


def test_fit_improves_brier_on_compressed_data():
    """Calibrated Brier should beat raw Brier on middle-band-compressed
    input (the pathology this module ships to fix)."""
    history = _compressed_history(n_per_bucket=100, seed=42)
    result = fit(history)
    assert result.train_brier_calibrated < result.train_brier_raw
    assert result.improvement_pct() > 0.05  # non-trivial


def test_fit_calibrator_stretches_middle_band_toward_tails():
    """On a compressed forecaster (p=0.30 for true 0.1 events),
    the calibrator should map 0.30 → below 0.30 (toward the true 0.1)."""
    history = _compressed_history(n_per_bucket=100, seed=7)
    result = fit(history)
    calibrated_from_30 = result.calibrate(0.30)
    assert calibrated_from_30 < 0.30


def test_fit_calibrator_stretches_upper_middle_up():
    """Symmetric: p=0.70 for true 0.9 events should map to above 0.70."""
    history = _compressed_history(n_per_bucket=100, seed=8)
    result = fit(history)
    calibrated_from_70 = result.calibrate(0.70)
    assert calibrated_from_70 > 0.70


# ═══════════════════════════════════════════════════════════════
# Calibrate — sanity
# ═══════════════════════════════════════════════════════════════

def test_calibrate_nan_passes_through():
    """NaN input → NaN output (no crash)."""
    cal = identity()
    assert math.isnan(cal.calibrate(float("nan")))


def test_calibrate_inf_passes_through():
    """Inf input → Inf output."""
    cal = identity()
    assert math.isinf(cal.calibrate(float("inf")))


def test_calibrate_output_in_zero_one():
    """For any well-behaved input the calibrated p is in [0, 1]."""
    history = _compressed_history(n_per_bucket=60, seed=9)
    result = fit(history)
    for p in [0.0, 0.1, 0.5, 0.9, 1.0]:
        p_cal = result.calibrate(p)
        assert 0.0 <= p_cal <= 1.0


# ═══════════════════════════════════════════════════════════════
# identity()
# ═══════════════════════════════════════════════════════════════

def test_identity_is_no_op_at_endpoints_and_midpoint():
    """identity() should map ~0 → ~0, ~0.5 → ~0.5, ~1 → ~1."""
    ident = identity()
    assert ident.calibrate(0.0) < 0.01
    assert abs(ident.calibrate(0.5) - 0.5) < 0.01
    assert ident.calibrate(1.0) > 0.99


def test_identity_reports_n_train_zero():
    """identity() should report 0 training observations."""
    ident = identity()
    assert ident.n_train == 0
    assert ident.train_brier_raw == 0.0
    assert ident.train_brier_calibrated == 0.0


def test_identity_improvement_pct_zero():
    """No training → no improvement claim."""
    ident = identity()
    assert ident.improvement_pct() == 0.0


# ═══════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════

def test_platt_transform_symmetric():
    """At A=-2*B, p_raw=0.5 → p_cal=0.5 (the midpoint identity)."""
    B = 10.0
    A = -2 * B
    assert abs(_platt_transform(0.5, A, B) - 0.5) < 1e-9


def test_platt_transform_extreme_z_clamped():
    """Extreme A*p+B should not overflow — 0 or 1 returned safely."""
    assert _platt_transform(0.5, 1e6, 0) == 0.0
    assert _platt_transform(0.5, -1e6, 0) == 1.0


def test_brier_helper():
    """Brier: 0.7 predicted vs 1 actual → 0.09; 0.3 vs 0 → 0.09; mean 0.09."""
    result = _brier([0.7, 0.3], [1.0, 0.0])
    assert abs(result - 0.09) < 1e-9


def test_brier_empty_returns_zero():
    """Empty input → 0.0 (no crash)."""
    assert _brier([], []) == 0.0
