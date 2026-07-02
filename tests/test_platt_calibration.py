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


# ═══════════════════════════════════════════════════════════════
# save / load / load_or_refit
# ═══════════════════════════════════════════════════════════════

def test_save_and_load_roundtrip(tmp_path):
    """Persist a fitted calibrator, read it back, params match."""
    from engine.platt_calibration import save, load

    history = _compressed_history(n_per_bucket=60, seed=11)
    original = fit(history)
    cache_path = tmp_path / "platt.json"
    save(original, cache_path)
    reloaded = load(cache_path)

    assert reloaded is not None
    assert reloaded.A == pytest.approx(original.A)
    assert reloaded.B == pytest.approx(original.B)
    assert reloaded.n_train == original.n_train


def test_load_missing_returns_none(tmp_path):
    """Missing cache file → None (caller treats as cold-start)."""
    from engine.platt_calibration import load
    assert load(tmp_path / "missing.json") is None


def test_load_corrupt_returns_none(tmp_path):
    """Malformed cache file → None (don't crash on garbage)."""
    from engine.platt_calibration import load
    cache_path = tmp_path / "corrupt.json"
    cache_path.write_text("{not valid json")
    assert load(cache_path) is None


def test_load_or_refit_cold_start_returns_fitted(tmp_path):
    """No cache → refit from history → return fitted calibrator."""
    from engine.platt_calibration import load_or_refit

    history = _compressed_history(n_per_bucket=60, seed=12)
    cache_path = tmp_path / "platt.json"

    result = load_or_refit(cache_path, lambda: history)
    assert result.n_train > 0  # NOT identity
    assert cache_path.exists()  # was persisted


def test_load_or_refit_uses_cache_when_fresh(tmp_path):
    """Fresh cache → don't refit → history_provider never called."""
    from engine.platt_calibration import load_or_refit, save

    history = _compressed_history(n_per_bucket=60, seed=13)
    fitted = fit(history)
    cache_path = tmp_path / "platt.json"
    save(fitted, cache_path)

    call_count = {"n": 0}

    def _provider():
        call_count["n"] += 1
        return []

    result = load_or_refit(cache_path, _provider)
    assert call_count["n"] == 0  # provider not called
    assert result.A == pytest.approx(fitted.A)


def test_load_or_refit_cold_start_falls_back_to_identity(tmp_path):
    """Cold start + insufficient history → identity() rather than crash."""
    from engine.platt_calibration import load_or_refit

    cache_path = tmp_path / "platt.json"
    # 10 observations << min_observations=30
    tiny = [{"forecast_p": 0.5, "actual": i % 2} for i in range(10)]
    result = load_or_refit(cache_path, lambda: tiny)
    assert result.n_train == 0  # identity()


def test_load_or_refit_stale_cache_refits(tmp_path):
    """Cache older than refit_interval_days → refit + overwrite."""
    from engine.platt_calibration import load_or_refit, save
    import json

    history_v1 = _compressed_history(n_per_bucket=60, seed=14)
    fitted_v1 = fit(history_v1)
    cache_path = tmp_path / "platt.json"
    save(fitted_v1, cache_path)
    # Force stale by rewriting refitted_at to 30 days ago
    payload = json.loads(cache_path.read_text())
    payload["refitted_at"] = "2026-01-01T00:00:00+00:00"
    cache_path.write_text(json.dumps(payload))

    call_count = {"n": 0}
    history_v2 = _compressed_history(n_per_bucket=80, seed=15)  # different size

    def _provider():
        call_count["n"] += 1
        return history_v2

    result = load_or_refit(cache_path, _provider, refit_interval_days=7)
    assert call_count["n"] == 1  # refit fired
    assert result.n_train == len(history_v2)
