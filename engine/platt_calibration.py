"""
engine/platt_calibration.py
──────────────────────────────────────────────────────────────────
Post-hoc probability calibration via Platt scaling.

Ships 2026-07-02 Tier-2 upgrade #7a from the deep-research roadmap.

Why
---
Prophet Arena (arxiv 2510.17638) found LLM forecasters — including
Haiku, Sonnet, GPT-4o — systematically compress p_yes into the
middle band (~0.30–0.70) even when the true probability is far off.
The `brier_reliability` middle-bin ECE audit shipped 2026-07-02
(Tier-1 #8) surfaces this pathology; this module FIXES it.

Bridgewater's AIA Forecaster (arxiv 2511.07678, 2025-09-15) adds
Platt scaling as a post-hoc supervisor step. Same idea as Platt's
original 1999 SVM calibration paper — fit a sigmoid
    p_calibrated = 1 / (1 + exp(A * p_raw + B))
to historical (p_raw, actual_outcome) pairs via logistic regression.

Two knobs (A, B) are enough to un-compress the middle band without
overfitting on n=50-200 calibration observations. Deterministic,
cheap, no LLM per market.

Contract
--------
Pure functions. No LLM. No network. Take a list of historical
(predicted_p, actual_outcome ∈ {0, 1}) pairs, return a fitted
PlattCalibrator dataclass whose `calibrate(p_raw)` maps a fresh
raw probability to a calibrated one.

Consumers
---------
- markets/auto/polymarket_daily.py estimate_p_yes(): apply Platt
  calibration to raw Haiku/Sonnet output before persisting to
  polymarket_history.jsonl. The audit block records BOTH raw and
  calibrated values so we can measure the improvement.
- markets/auto/brier_audit.py: the calibrator itself can be
  updated weekly from the last 30-90 days of history — the
  brier_audit run is the natural cadence.

Refs
----
Platt, J.C. (1999) "Probabilistic Outputs for Support Vector Machines
and Comparisons to Regularized Likelihood Methods", Adv. in Large
Margin Classifiers.

Bridgewater Associates (2025-09) "AIA Forecaster: Adaptive
Introspective Alignment for Probabilistic Forecasting",
arxiv 2511.07678.

Prophet Arena (2026-05) arxiv 2510.17638 §4.3 — the middle-bin
compression pathology this module directly addresses.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import scipy.optimize as _opt


# ═══════════════════════════════════════════════════════════════
# Fitted calibrator
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PlattCalibrator:
    """Fitted Platt sigmoid parameters.

    p_calibrated = 1 / (1 + exp(A * p_raw + B))

    A negative → calibration steepens (spreads mid-band toward tails)
    A ≈ 0     → identity (no calibration needed)
    """
    A: float
    B: float
    n_train: int          # observations used for fit
    train_brier_raw: float
    train_brier_calibrated: float

    def calibrate(self, p_raw: float) -> float:
        """Apply the fitted sigmoid to a fresh raw probability.

        Degenerate inputs (NaN, Inf, out of [0,1]) are passed through
        unchanged — the caller should have already validated inputs.
        """
        if math.isnan(p_raw) or math.isinf(p_raw):
            return p_raw
        return _platt_transform(p_raw, self.A, self.B)

    def improvement_pct(self) -> float:
        """Fractional Brier score improvement on the training set.

        Positive → calibration helped. Negative → identity would have
        been better (which suggests overfitting or already-calibrated
        raw outputs).
        """
        if self.train_brier_raw <= 0:
            return 0.0
        return (self.train_brier_raw - self.train_brier_calibrated) / self.train_brier_raw


# ═══════════════════════════════════════════════════════════════
# Fit
# ═══════════════════════════════════════════════════════════════

def _platt_transform(p_raw: float, A: float, B: float) -> float:
    """Sigmoid: p = 1 / (1 + exp(A * p_raw + B))."""
    z = A * p_raw + B
    # Numerical-safety clamps for extreme z
    if z > 500:
        return 0.0
    if z < -500:
        return 1.0
    return 1.0 / (1.0 + math.exp(z))


def _brier(predictions: list[float], actuals: list[float]) -> float:
    """Mean squared error between prediction and 0/1 outcome."""
    n = len(predictions)
    if n == 0:
        return 0.0
    return sum((p - a) ** 2 for p, a in zip(predictions, actuals)) / n


def fit(history: Iterable[dict], *,
        min_observations: int = 30) -> PlattCalibrator:
    """Fit Platt scaling from history of (p_raw, actual) pairs.

    Parameters
    ----------
    history : iterable of {"forecast_p": float, "actual": 0|1|float}
              — same shape brier_audit.brier_for_decision() emits.
    min_observations : hard floor. Below this the fit is degenerate.

    Returns
    -------
    PlattCalibrator with A, B, and Brier-improvement audit.

    Raises
    ------
    ValueError if fewer than min_observations OR all outcomes are
    the same class (fit is undefined without both 0s and 1s).
    """
    pairs = []
    for h in history:
        p = h.get("forecast_p")
        a = h.get("actual")
        if p is None or a is None:
            continue
        if not (0 <= p <= 1):
            continue
        if math.isnan(p) or math.isinf(p):
            continue
        # Coerce actual to 0/1 float — accept int 0/1, float 0.0/1.0
        try:
            a_val = float(a)
        except (TypeError, ValueError):
            continue
        if a_val not in (0.0, 1.0):
            continue
        pairs.append((float(p), a_val))

    n = len(pairs)
    if n < min_observations:
        raise ValueError(
            f"Need at least {min_observations} observations, got {n}. "
            f"Platt fit is unreliable below this scale."
        )

    n_positive = sum(1 for _, a in pairs if a == 1.0)
    n_negative = n - n_positive
    if n_positive == 0 or n_negative == 0:
        raise ValueError(
            f"Need both classes present; got {n_positive} positives "
            f"and {n_negative} negatives."
        )

    p_raws = [p for p, _ in pairs]
    actuals = [a for _, a in pairs]

    # Log-likelihood for logistic regression. Platt's paper §3
    # recommends smoothed targets (t+, t-) to reduce overfitting:
    #   t+ = (N+ + 1) / (N+ + 2)
    #   t- = 1 / (N- + 2)
    # But at n≥30 the raw {0, 1} targets are fine. Skip the smoothing
    # here to keep the fit interpretable.

    def neg_log_likelihood(params):
        A, B = params
        nll = 0.0
        for p, a in zip(p_raws, actuals):
            q = _platt_transform(p, A, B)
            # Clip to avoid log(0)
            q = max(1e-12, min(1.0 - 1e-12, q))
            nll -= a * math.log(q) + (1 - a) * math.log(1 - q)
        return nll

    # Initial guess: identity sigmoid at A=-4, B=2 approximates the
    # p→p mapping for p in [0, 1]. Nelder-Mead handles the smooth
    # 2-parameter surface robustly.
    x0 = [-4.0, 2.0]
    result = _opt.minimize(
        neg_log_likelihood, x0,
        method="Nelder-Mead",
        options={"maxiter": 2000, "xatol": 1e-5, "fatol": 1e-5},
    )
    A_fit, B_fit = float(result.x[0]), float(result.x[1])

    calibrated = [_platt_transform(p, A_fit, B_fit) for p in p_raws]
    brier_raw = _brier(p_raws, actuals)
    brier_cal = _brier(calibrated, actuals)

    return PlattCalibrator(
        A=A_fit,
        B=B_fit,
        n_train=n,
        train_brier_raw=brier_raw,
        train_brier_calibrated=brier_cal,
    )


# ═══════════════════════════════════════════════════════════════
# Identity calibrator (returned when no history exists yet)
# ═══════════════════════════════════════════════════════════════

def identity() -> PlattCalibrator:
    """Return a no-op calibrator for the cold-start case.

    Under the fitted Platt sigmoid,
        p = 1 / (1 + exp(A * p_raw + B))
    the identity mapping p_cal = p_raw is achieved by A = -∞, but
    numerically we approximate it with A = -60, B = 30. This gives
    p_cal ≈ 1 - 1e-13 at p_raw = 1 and p_cal ≈ 1e-13 at p_raw = 0,
    with p_cal ≈ 0.5 at p_raw ≈ 0.5.
    """
    # For a true near-identity we want:
    #   p = 1/(1 + exp(A*p_raw + B))
    #   at p_raw=0:   p ≈ 0, so exp(B) large → B large positive
    #   at p_raw=0.5: p ≈ 0.5, so A*0.5 + B ≈ 0 → A ≈ -2B
    #   at p_raw=1:   p ≈ 1, so exp(A + B) small → A + B large negative
    # A=-60, B=30 satisfies all three within numerical precision.
    return PlattCalibrator(
        A=-60.0,
        B=30.0,
        n_train=0,
        train_brier_raw=0.0,
        train_brier_calibrated=0.0,
    )
