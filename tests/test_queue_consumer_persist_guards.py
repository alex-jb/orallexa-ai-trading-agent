"""
Regression tests for the v1.2.1 persist-boundary guards in queue_consumer.py.

Reason to exist: on 2026-07-08 an audit found 3 World Cup rows written to
polymarket-decisions.jsonl on 2026-07-07 with `our_p_yes=0.5 /
edge=+0.47` — a garbage signal that the v1.1.0 uniform-0.5 guard and
sports_skip were supposed to have caught upstream in polymarket_daily.py.
The guards fired on the SIGNAL side, but whatever queue-emit path fed
queue/pending/ bypassed them, and queue_consumer.py had no defense at
the persist boundary.

These tests pin the last-hop guards so the calibration record can never
be corrupted again by a broken upstream.

If any of these fail, do NOT relax them. Chase the regression upstream.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make markets/auto importable
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "markets" / "auto")
)


def test_should_persist_rejects_uniform_0_5_exactly():
    """our_p_yes = 0.5 exactly must be rejected."""
    import queue_consumer as qc

    decision = {
        "market_id": "will-openai-hit-500b-valuation-2026",
        "our_p_yes": 0.5,
        "edge": 0.47,
        "suggested_side": "BUY YES",
    }
    ok, reason = qc._should_persist(decision)
    assert ok is False
    assert reason == "uniform_0_5_collapse_at_persist_boundary"


def test_should_persist_rejects_uniform_0_5_within_tolerance():
    """our_p_yes within 0.5 ± 0.002 must be rejected."""
    import queue_consumer as qc

    for p in (0.4985, 0.5015, 0.499, 0.501):
        decision = {"market_id": "will-something-happen-2026", "our_p_yes": p}
        ok, reason = qc._should_persist(decision)
        assert ok is False, f"our_p_yes={p} should be rejected"
        assert reason == "uniform_0_5_collapse_at_persist_boundary"


def test_should_persist_accepts_signal_outside_uniform_band():
    """our_p_yes safely outside 0.5 ± 0.002 must pass."""
    import queue_consumer as qc

    for p in (0.30, 0.48, 0.503, 0.55, 0.90):
        decision = {"market_id": "will-fed-cut-rates-jul-2026", "our_p_yes": p}
        ok, reason = qc._should_persist(decision)
        assert ok is True, f"our_p_yes={p} should pass"
        assert reason == ""


def test_should_persist_rejects_world_cup_sports_slug():
    """The exact 2026-07-07 failure mode: World Cup slug with edge signal."""
    import queue_consumer as qc

    # These are the actual slugs that leaked through on 2026-07-07
    for slug in (
        "will-egypt-win-the-2026-fifa-world-cup",
        "will-morocco-win-the-2026-fifa-world-cup",
        "will-norway-win-the-2026-fifa-world-cup",
    ):
        # Even with a "believable" our_p_yes that dodges the uniform-0.5
        # guard, the sports_skip must reject.
        decision = {"market_id": slug, "our_p_yes": 0.03}
        ok, reason = qc._should_persist(decision)
        assert ok is False, f"{slug} must be rejected as sports"
        assert reason == "sports_skip_at_persist_boundary"


def test_should_persist_rejects_other_sport_slugs():
    """Broad sports-token coverage (nba, nfl, tennis, olympics)."""
    import queue_consumer as qc

    for slug in (
        "will-lakers-win-nba-championship-2026",
        "will-chiefs-win-super-bowl-2027",
        "who-wins-wimbledon-mens-singles-2026",
        "will-usa-medal-count-exceed-40-olympics",
    ):
        decision = {"market_id": slug, "our_p_yes": 0.25}
        ok, _reason = qc._should_persist(decision)
        assert ok is False, f"{slug} must be rejected as sports"


def test_should_persist_accepts_non_sport_political_market():
    """Politics/economics markets must NOT be false-positived as sports."""
    import queue_consumer as qc

    for slug in (
        "will-bernie-sanders-win-2028-nomination",
        "will-fed-cut-25bp-in-jul-2026",
        "will-openai-valuation-hit-500b-2026",
        "china-taiwan-military-action-2026",
    ):
        decision = {"market_id": slug, "our_p_yes": 0.15}
        ok, _reason = qc._should_persist(decision)
        assert ok is True, f"{slug} must NOT be rejected"


def test_should_persist_accepts_missing_our_p():
    """our_p_yes = None (sports_skip already recorded upstream) must pass
    IF the slug isn't a sports slug. Otherwise sports guard catches it."""
    import queue_consumer as qc

    decision = {"market_id": "will-cpi-print-above-3-jul-2026", "our_p_yes": None}
    ok, _reason = qc._should_persist(decision)
    assert ok is True


def test_should_persist_rejects_sports_slug_with_none_our_p():
    """Sports rejection must win even when our_p is None (upstream skip)."""
    import queue_consumer as qc

    decision = {
        "market_id": "will-brazil-win-2026-fifa-world-cup",
        "our_p_yes": None,
    }
    ok, reason = qc._should_persist(decision)
    assert ok is False
    assert reason == "sports_skip_at_persist_boundary"
