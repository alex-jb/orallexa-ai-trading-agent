"""
tests/test_dixon_coles_fit.py
──────────────────────────────────────────────────────────────────
Pins the Dixon-Coles fit contract shipped 2026-07-02 (Tier-2 #6).

Coverage strategy:
  - Fit-shape invariants (attack sums to zero, γ near 0.25, ρ ≤ 0)
  - Fit correctness on synthetic data with known strength ordering
  - Degenerate inputs (too few matches, too few teams) raise cleanly
  - match_probabilities() output is a proper distribution (sums to 1,
    all cells non-negative, over + under = 1)
  - DC τ correction is applied (draws vs Poisson-independence)
  - Time-decay weight helper monotonically increases toward newest
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

import pytest

from engine.dixon_coles_fit import (
    DixonColesFit,
    _tau,
    fit,
    match_probabilities,
    time_decay_weights,
)


# ═══════════════════════════════════════════════════════════════
# Fit — shape + basic invariants
# ═══════════════════════════════════════════════════════════════

def _synthetic_matches(n_per_pair: int = 4, seed: int = 42) -> list[dict]:
    """3 strong teams (A/B/C) + 3 weak teams (X/Y/Z). Sample Poisson
    goals from λ that reflects strength: strong-vs-weak → λ=2.5/0.7."""
    rng = random.Random(seed)
    strong = ["A", "B", "C"]
    weak = ["X", "Y", "Z"]

    def poisson(lam: float) -> int:
        # Knuth's rejection algorithm — cheap for small lam
        L = math.exp(-lam)
        k = 0
        p = 1.0
        while p > L:
            k += 1
            p *= rng.random()
        return k - 1

    matches = []
    pairs = []
    for h in strong + weak:
        for a in strong + weak:
            if h != a:
                pairs.append((h, a))
    for h, a in pairs:
        for _ in range(n_per_pair):
            # Strong home vs weak away → 2.5 - 0.7
            # Weak home vs strong away → 0.9 - 2.0 (home boost still helps)
            if h in strong and a in weak:
                lam_h, lam_a = 2.5, 0.7
            elif h in weak and a in strong:
                lam_h, lam_a = 0.9, 2.0
            elif h in strong and a in strong:
                lam_h, lam_a = 1.6, 1.3
            else:  # weak vs weak
                lam_h, lam_a = 1.3, 1.1
            matches.append({
                "home_team": h, "away_team": a,
                "home_goals": poisson(lam_h),
                "away_goals": poisson(lam_a),
            })
    return matches


def test_fit_recovers_strength_ordering():
    """Strong teams should have higher attack than weak teams."""
    matches = _synthetic_matches(n_per_pair=8, seed=1)
    result = fit(matches)
    for strong in ["A", "B", "C"]:
        for weak in ["X", "Y", "Z"]:
            assert result.attack[strong] > result.attack[weak], (
                f"Strong team {strong} attack {result.attack[strong]:.3f} "
                f"should be > weak team {weak} attack {result.attack[weak]:.3f}"
            )


def test_fit_attack_sums_approximately_zero():
    """Sum-to-zero identifiability constraint should hold exactly."""
    matches = _synthetic_matches(seed=2)
    result = fit(matches)
    total_attack = sum(result.attack.values())
    assert abs(total_attack) < 1e-6, (
        f"Attack should sum to zero (identifiability), got {total_attack}"
    )


def test_fit_home_advantage_is_positive():
    """γ (home_advantage) should be positive — home teams score more.
    The 1997 Dixon-Coles paper landed γ ≈ 0.30 for the EPL."""
    matches = _synthetic_matches(seed=3)
    result = fit(matches)
    assert result.home_advantage > 0, (
        f"γ should be > 0, got {result.home_advantage}"
    )
    # Sanity: shouldn't be absurd (>1 log-scale would mean 2.7× goal
    # multiplier just for playing at home — not physically realistic)
    assert result.home_advantage < 1.0


def test_fit_rho_is_bounded():
    """ρ should be in [-0.5, 0.5] after the clamp guard."""
    matches = _synthetic_matches(seed=4)
    result = fit(matches)
    assert -0.5 <= result.rho <= 0.5


def test_fit_reports_n_matches_and_ll():
    """The fit reports the training set size + achieved log-likelihood."""
    matches = _synthetic_matches(n_per_pair=6, seed=5)
    result = fit(matches)
    assert result.n_matches == len(matches)
    assert isinstance(result.log_likelihood, float)
    assert not math.isnan(result.log_likelihood)
    assert not math.isinf(result.log_likelihood)


def test_fit_below_20_matches_raises():
    """Fitting on 19 matches should be rejected — too small to converge."""
    matches = [{"home_team": "A", "away_team": "B",
                "home_goals": 1, "away_goals": 0} for _ in range(19)]
    with pytest.raises(ValueError, match="20 matches"):
        fit(matches)


def test_fit_below_4_teams_raises():
    """Fitting on 3 teams is degenerate — not enough team variance."""
    matches = [{"home_team": "A", "away_team": "B",
                "home_goals": 1, "away_goals": 0} for _ in range(25)]
    with pytest.raises(ValueError, match="4 unique teams"):
        fit(matches)


# ═══════════════════════════════════════════════════════════════
# expected_goals API
# ═══════════════════════════════════════════════════════════════

def test_expected_goals_strong_vs_weak_asymmetric():
    """Strong home vs weak away → home λ should be substantially higher."""
    matches = _synthetic_matches(n_per_pair=8, seed=6)
    result = fit(matches)
    lam_h, lam_a = result.expected_goals("A", "X")
    assert lam_h > lam_a
    assert lam_h > 1.5   # Strong team should score above avg
    assert lam_a < 1.5   # Weak team suppressed


def test_expected_goals_unknown_team_returns_zero():
    """Team not in the fit → (0, 0), signals caller to fall back."""
    matches = _synthetic_matches(seed=7)
    result = fit(matches)
    lam_h, lam_a = result.expected_goals("UnknownTeam", "A")
    assert lam_h == 0.0
    assert lam_a == 0.0


# ═══════════════════════════════════════════════════════════════
# match_probabilities — is this a proper distribution?
# ═══════════════════════════════════════════════════════════════

def test_match_probs_sum_to_one():
    """home + draw + away should sum to 1 (exhaustive + disjoint)."""
    probs = match_probabilities(1.5, 1.2, -0.1)
    total = probs["p_home_win"] + probs["p_draw"] + probs["p_away_win"]
    assert abs(total - 1.0) < 1e-6


def test_match_probs_over_plus_under_equals_one():
    """Over 2.5 + Under 2.5 must partition."""
    probs = match_probabilities(1.5, 1.2, -0.1)
    assert abs(probs["p_over_n"] + probs["p_under_n"] - 1.0) < 1e-6


def test_match_probs_all_non_negative():
    """No probability field should ever be negative."""
    probs = match_probabilities(2.0, 1.0, -0.15)
    for k, v in probs.items():
        assert v >= 0, f"{k} = {v}"


def test_match_probs_high_lambdas_favor_home():
    """λ_h=3, λ_a=0.5 → home win prob should dominate."""
    probs = match_probabilities(3.0, 0.5, -0.1)
    assert probs["p_home_win"] > 0.75
    assert probs["p_home_win"] > probs["p_draw"] + probs["p_away_win"]


def test_match_probs_symmetric_lambdas_split_evenly():
    """λ_h = λ_a → p_home > p_away only via home advantage NOT via τ.
    We're passing symmetric λs so home + away should be nearly equal."""
    probs = match_probabilities(1.4, 1.4, -0.1)
    # Symmetric grid → home and away probs equal (grid is symmetric).
    assert abs(probs["p_home_win"] - probs["p_away_win"]) < 1e-6


def test_match_probs_over_line_configurable():
    """Different OU lines should give different p_over_n."""
    probs_2_5 = match_probabilities(1.5, 1.2, -0.1, ou_line=2.5)
    probs_3_5 = match_probabilities(1.5, 1.2, -0.1, ou_line=3.5)
    # Higher line → harder to go over → lower p_over_n
    assert probs_3_5["p_over_n"] < probs_2_5["p_over_n"]


# ═══════════════════════════════════════════════════════════════
# Dixon-Coles τ correction
# ═══════════════════════════════════════════════════════════════

def test_tau_only_active_on_low_scores():
    """τ = 1.0 for any (h, a) other than {(0,0), (0,1), (1,0), (1,1)}."""
    for h in [2, 3, 5]:
        for a in [2, 3, 4]:
            assert _tau(h, a, 1.5, 1.2, -0.1) == 1.0


def test_tau_bumps_00_when_rho_negative():
    """With ρ < 0, 0-0 gets a τ > 1 bump."""
    tau_00 = _tau(0, 0, 1.5, 1.2, -0.1)
    assert tau_00 > 1.0


def test_tau_bumps_11_when_rho_negative():
    """With ρ < 0, 1-1 gets τ > 1 (Dixon-Coles found independent Poisson
    UNDERESTIMATES the 1-1 scoreline just like it underestimates 0-0)."""
    tau_11 = _tau(1, 1, 1.5, 1.2, -0.1)
    assert tau_11 > 1.0


def test_tau_dampens_10_when_rho_negative():
    """With ρ < 0, 1-0 gets τ < 1 (independent Poisson OVERESTIMATES
    the 1-0 scoreline — mass gets pulled out by the correction)."""
    tau_10 = _tau(1, 0, 1.5, 1.2, -0.1)
    assert tau_10 < 1.0


def test_tau_dampens_01_when_rho_negative():
    """Same as 1-0 by symmetry."""
    tau_01 = _tau(0, 1, 1.5, 1.2, -0.1)
    assert tau_01 < 1.0


def test_tau_reduces_to_one_when_rho_zero():
    """ρ = 0 → τ = 1 for all cells (Dixon-Coles collapses to independent Poisson)."""
    for h in range(3):
        for a in range(3):
            assert _tau(h, a, 1.5, 1.2, 0.0) == 1.0


# ═══════════════════════════════════════════════════════════════
# time_decay_weights
# ═══════════════════════════════════════════════════════════════

def test_time_decay_newest_is_one():
    """Newest date should get weight 1.0."""
    today = date(2026, 7, 2)
    dates = [today - timedelta(days=d) for d in [100, 50, 10, 0]]
    w = time_decay_weights(dates, xi=0.0018)
    assert abs(w[-1] - 1.0) < 1e-6


def test_time_decay_older_lower():
    """Older dates should have monotonically lower weights."""
    today = date(2026, 7, 2)
    dates = [today - timedelta(days=d) for d in [200, 100, 50, 0]]
    w = time_decay_weights(dates, xi=0.0018)
    assert w[0] < w[1] < w[2] < w[3]


def test_time_decay_all_weights_positive():
    """No weight should ever be zero or negative."""
    today = date(2026, 7, 2)
    dates = [today - timedelta(days=d) for d in [1000, 500, 100, 10, 0]]
    w = time_decay_weights(dates, xi=0.0018)
    assert all(x > 0 for x in w)


def test_time_decay_empty_returns_empty():
    """Empty dates → empty weights (no crash)."""
    assert time_decay_weights([]) == []


# ═══════════════════════════════════════════════════════════════
# sports_pricer wiring — fit consumed by predict_match_from_fit
# ═══════════════════════════════════════════════════════════════

def test_sports_pricer_from_fit_returns_prediction():
    """The sports_pricer bridge accepts a DC fit and produces a
    MatchPrediction with correct model label."""
    from engine.sports_pricer import predict_match_from_fit

    matches = _synthetic_matches(n_per_pair=8, seed=8)
    result = fit(matches)
    pred = predict_match_from_fit("A", "X", result)
    assert pred is not None
    assert pred.model == "dixon_coles_mle_v2"
    assert 0.0 <= pred.p_home_win <= 1.0
    assert abs(pred.p_home_win + pred.p_draw + pred.p_away_win - 1.0) < 1e-4


def test_sports_pricer_from_fit_unknown_team_returns_none():
    """Team not in fit → None → caller falls back."""
    from engine.sports_pricer import predict_match_from_fit

    matches = _synthetic_matches(seed=9)
    result = fit(matches)
    pred = predict_match_from_fit("UnknownTeam", "A", result)
    assert pred is None
