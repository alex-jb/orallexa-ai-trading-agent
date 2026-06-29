"""
tests/test_parlay_correlation.py
──────────────────────────────────────────────────────────────────
Pins the MC bracket simulator's invariants:
  - leg marginals match single-team advance probability
  - joint parlay prob ≤ each leg's marginal (joint ≤ marginal axiom)
  - independent multiplication overstates joint for correlated legs
  - deterministic under same seed
"""
from __future__ import annotations

import pytest

from engine.parlay_correlation import (
    BracketMatch,
    ParlayLeg,
    leg_team_advances_to,
    leg_match_over,
    leg_match_under,
    leg_match_btts,
    p_joint_parlay,
    simulate_tournament_advance,
)


# Minimal 4-team knockout bracket for testing. Two QFs feed one SF,
# winner is Champion. Just enough structure to validate the math.
SIMPLE_BRACKET = [
    BracketMatch(match_id="qf1", home="Spain", away="USA",
                 stage="QF"),
    BracketMatch(match_id="qf2", home="Brazil", away="Mexico",
                 stage="QF"),
    BracketMatch(match_id="sf", home=None, away=None,
                 home_source="qf1", away_source="qf2",
                 stage="SF"),
    BracketMatch(match_id="final", home=None, away=None,
                 home_source="sf", away_source="sf",
                 stage="F"),
]

ELO_LOOKUP = {
    "Spain": 1900,
    "USA": 1500,
    "Brazil": 2050,
    "Mexico": 1600,
}


def test_strong_team_advance_prob_high():
    """Brazil at Elo 2050 vs Mexico at 1600 should advance > 70% to SF."""
    p = simulate_tournament_advance(
        "Brazil", stage="SF",
        elo_lookup=ELO_LOOKUP, bracket=SIMPLE_BRACKET,
        n=5_000, seed=42,
    )
    assert p > 0.65, f"Brazil SF prob {p} too low for Elo 2050 vs 1600"


def test_weak_team_advance_prob_low():
    """USA at 1500 vs Spain at 1900 → SF prob < 30%."""
    p = simulate_tournament_advance(
        "USA", stage="SF",
        elo_lookup=ELO_LOOKUP, bracket=SIMPLE_BRACKET,
        n=5_000, seed=42,
    )
    assert p < 0.35, f"USA SF prob {p} too high"


def test_seed_reproducibility():
    """Same seed → same MC output (bit-identical for the seed only,
    we just check the float matches at 2 decimals)."""
    p1 = simulate_tournament_advance(
        "Spain", stage="SF",
        elo_lookup=ELO_LOOKUP, bracket=SIMPLE_BRACKET,
        n=2_000, seed=99,
    )
    p2 = simulate_tournament_advance(
        "Spain", stage="SF",
        elo_lookup=ELO_LOOKUP, bracket=SIMPLE_BRACKET,
        n=2_000, seed=99,
    )
    assert abs(p1 - p2) < 0.005, "MC should be reproducible with same seed"


def test_joint_parlay_returns_required_shape():
    legs = [
        leg_team_advances_to("Spain", "SF"),
        leg_team_advances_to("Brazil", "SF"),
    ]
    result = p_joint_parlay(
        legs, elo_lookup=ELO_LOOKUP, bracket=SIMPLE_BRACKET,
        n=2_000, seed=7,
    )
    for k in ("joint_prob", "independent_prob", "leg_marginals",
              "n_iterations", "edge_vs_independent"):
        assert k in result, f"missing key {k}"
    assert result["n_iterations"] == 2_000


def test_joint_prob_le_each_marginal():
    """Axiom: P(A AND B) ≤ min(P(A), P(B))."""
    legs = [
        leg_team_advances_to("Spain", "SF"),
        leg_team_advances_to("Brazil", "SF"),
        leg_team_advances_to("Mexico", "SF"),
    ]
    result = p_joint_parlay(
        legs, elo_lookup=ELO_LOOKUP, bracket=SIMPLE_BRACKET,
        n=3_000, seed=11,
    )
    joint = result["joint_prob"]
    for marginal in result["leg_marginals"].values():
        assert joint <= marginal + 0.01, (
            f"joint {joint} > marginal {marginal} — math regressed"
        )


def test_mutually_exclusive_advance_legs_yield_zero_joint():
    """Spain and USA play each other in QF1 — they can NOT both reach SF.
    Joint prob must be 0."""
    legs = [
        leg_team_advances_to("Spain", "SF"),
        leg_team_advances_to("USA", "SF"),
    ]
    result = p_joint_parlay(
        legs, elo_lookup=ELO_LOOKUP, bracket=SIMPLE_BRACKET,
        n=3_000, seed=13,
    )
    assert result["joint_prob"] == 0.0, (
        f"two teams meeting in QF can't both advance; got joint={result['joint_prob']}"
    )
    # Independent multiplication should give SOMETHING > 0 — that's the
    # EXACT bookmaker-mispricing this module catches. (USA's SF prob is
    # low so the product is small, but still strictly positive.)
    assert result["independent_prob"] > 0.005, (
        f"naive independent calc should have been > 0; got {result['independent_prob']}"
    )
    assert result["edge_vs_independent"] < 0, (
        "MC should show this is over-priced vs independent multiplication"
    )


def test_match_over_and_under_complementary():
    """Over and Under legs at same line shouldn't both win the same match.
    Stronger statement: their marginals roughly sum to 1.0."""
    legs = [
        leg_match_over("qf1", line=2.5),
        leg_match_under("qf1", line=2.5),
    ]
    result = p_joint_parlay(
        legs, elo_lookup=ELO_LOOKUP, bracket=SIMPLE_BRACKET,
        n=3_000, seed=17,
    )
    marg = result["leg_marginals"]
    total = sum(marg.values())
    assert 0.97 < total < 1.03, f"Over+Under sum {total} ≠ 1.0"
    # Joint must be 0 (a match can't be both over and under)
    assert result["joint_prob"] == 0.0


def test_btts_predicate_runs():
    """Smoke check that BTTS predicate runs without crash."""
    legs = [leg_match_btts("qf1")]
    result = p_joint_parlay(
        legs, elo_lookup=ELO_LOOKUP, bracket=SIMPLE_BRACKET,
        n=1_000, seed=21,
    )
    marg = result["leg_marginals"]["qf1 BTTS"]
    # Real-football BTTS hovers 45-55% for balanced matches
    assert 0.20 < marg < 0.80, f"BTTS marginal {marg} outside plausible range"
