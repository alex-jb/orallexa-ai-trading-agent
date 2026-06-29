"""
tests/test_sports_pricer.py
──────────────────────────────────────────────────────────────────
Pins sports_pricer.predict_match contract: deterministic
probabilities, sane sums, plausible mean lambda, no-data fallback.
"""
from __future__ import annotations

import pytest

from engine.sports_pricer import (
    DEFAULT_OU_LINE,
    MatchPrediction,
    predict_match,
)


def test_predict_returns_none_when_elo_missing():
    """No data → graceful None (caller falls back to Haiku)."""
    assert predict_match("A", "B") is None
    assert predict_match("A", "B", elo_home=1600) is None
    assert predict_match("A", "B", elo_away=1600) is None


def test_predict_balanced_match_is_roughly_symmetric():
    """Two equal-Elo teams → home win > away win (home advantage) but
    not by more than ~10 percentage points."""
    pred = predict_match("Spain", "Italy", elo_home=1850, elo_away=1850)
    assert pred is not None
    assert abs(pred.p_home_win - pred.p_away_win) < 0.12, (
        f"home_win={pred.p_home_win} away_win={pred.p_away_win}; "
        "home advantage shouldn't dwarf away chances"
    )
    # Sum to 1.0 within rounding
    total = pred.p_home_win + pred.p_draw + pred.p_away_win
    assert 0.99 < total < 1.01


def test_predict_strong_favorite_dominates():
    """Big Elo gap → strong home win prob, low draw + away."""
    pred = predict_match("Brazil", "USA", elo_home=2100, elo_away=1500)
    assert pred is not None
    assert pred.p_home_win > 0.65
    assert pred.p_away_win < 0.20


def test_predict_strong_underdog_loses():
    """Big Elo gap reversed (low-elo home vs high-elo away) → away wins
    despite home advantage."""
    pred = predict_match("USA", "Brazil", elo_home=1500, elo_away=2100)
    assert pred is not None
    assert pred.p_away_win > pred.p_home_win, (
        "stronger away team should still win > home advantage of weaker home"
    )


def test_lambda_home_higher_for_stronger_home():
    """expected-goals lambda_home > lambda_away when home is much
    stronger AND there's a home advantage boost."""
    pred = predict_match("home", "away", elo_home=1900, elo_away=1500)
    assert pred is not None
    assert pred.lambda_home > pred.lambda_away
    # Both lambdas should be in plausible football range. Top end is
    # ~5 for a heavy favorite at home — Spain hammering Andorra would
    # do that. Upper bound at 5.5 keeps the test sensitive to a real
    # blow-up (lambda > 6 = model broken).
    assert 0.3 < pred.lambda_home < 5.5
    assert 0.05 < pred.lambda_away < 5.5


def test_over_under_sum_to_one():
    """Over + Under must always sum to 1.0 (exhaustive partition)."""
    pred = predict_match("A", "B", elo_home=1700, elo_away=1700)
    assert pred is not None
    total = pred.p_over_n + pred.p_under_n
    assert 0.99 < total < 1.01


def test_btts_in_range_zero_to_one():
    pred = predict_match("A", "B", elo_home=1700, elo_away=1700)
    assert pred is not None
    assert 0.0 <= pred.p_btts <= 1.0


def test_xg_override_increases_lambda():
    """Passing in xg_recent should pull lambda toward the xG signal."""
    pred_baseline = predict_match("A", "B", elo_home=1700, elo_away=1700)
    pred_with_xg = predict_match("A", "B", elo_home=1700, elo_away=1700,
                                  xg_recent_home=3.0, xg_recent_away=0.3)
    assert pred_baseline is not None and pred_with_xg is not None
    assert pred_with_xg.lambda_home > pred_baseline.lambda_home
    assert pred_with_xg.lambda_away < pred_baseline.lambda_away


def test_for_polymarket_leg_maps_correctly():
    pred = predict_match("A", "B", elo_home=1900, elo_away=1500)
    assert pred is not None
    assert pred.for_polymarket_leg("home_win") == pred.p_home_win
    assert pred.for_polymarket_leg("draw") == pred.p_draw
    assert pred.for_polymarket_leg("away_win") == pred.p_away_win
    assert pred.for_polymarket_leg("over") == pred.p_over_n
    assert pred.for_polymarket_leg("under") == pred.p_under_n
    assert pred.for_polymarket_leg("btts") == pred.p_btts
    # Double-chance is a sum
    dc_h = pred.for_polymarket_leg("double_chance_home")
    assert dc_h == pred.p_home_win + pred.p_draw
    # Unknown leg type → None (caller decides what to do)
    assert pred.for_polymarket_leg("not_a_real_leg") is None


def test_custom_ou_line():
    """ou_line=3.5 should give lower over probability than ou_line=1.5."""
    pred_15 = predict_match("A", "B", elo_home=1700, elo_away=1700, ou_line=1.5)
    pred_35 = predict_match("A", "B", elo_home=1700, elo_away=1700, ou_line=3.5)
    assert pred_15 is not None and pred_35 is not None
    assert pred_15.p_over_n > pred_35.p_over_n


def test_model_metadata_present():
    """Every prediction should carry its provenance for auditability."""
    pred = predict_match("A", "B", elo_home=1700, elo_away=1700)
    assert pred is not None
    assert pred.model.startswith("dixon_coles")
    assert "ELO" in pred.trained_on.upper() or "elo" in pred.trained_on.lower()
    assert pred.fetched_at  # ISO timestamp present
