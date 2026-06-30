"""
tests/test_polymarket_sports_skip.py
──────────────────────────────────────────────────────────────────
Pins the 2026-06-30 sports-market skip-routing logic.

Background: queue_consumer.py first fire (2026-06-30) surfaced that 126
of 173 historical Polymarket decisions were sports markets ("Will X win
the 2026 FIFA World Cup"), and Haiku had been returning a default-ish
~0.5 p_yes for ALL of them — producing a fake mean edge of +0.472
across the entire sports tape. If we'd been real-money trading: 126
sized positions on noise.

These tests pin _is_sports_market() so the next time someone "improves"
the detector they can't accidentally re-introduce the false-edge bug.
"""
from __future__ import annotations

import pytest

from markets.auto.polymarket_daily import _is_sports_market, estimate_p_yes


# ---------------------------------------------------------------------
# Detector contract
# ---------------------------------------------------------------------

@pytest.mark.parametrize("slug,question", [
    ("will-uzbekistan-win-the-2026-fifa-world-cup-773",
     "Will Uzbekistan win the 2026 FIFA World Cup?"),
    ("will-usa-win-the-2026-fifa-world-cup-467",
     "Will USA win the 2026 FIFA World Cup?"),
    ("will-new-zealand-win-the-2026-fifa-world-cup-635",
     "Will New Zealand win the 2026 FIFA World Cup?"),
    ("nba-finals-2027-game-3",
     "Will the Lakers win NBA Finals Game 3?"),
    ("super-bowl-lxi-winner",
     "Who wins Super Bowl LXI?"),
    ("wimbledon-2026-mens-final",
     "Will Alcaraz win Wimbledon 2026?"),
    ("champions-league-2027-final",
     "Will Real Madrid win the Champions League?"),
    ("uefa-euro-2028-winner",
     "Who wins UEFA Euro 2028?"),
    ("f1-2026-drivers-championship",
     "Will Verstappen win F1 2026 drivers championship?"),
    ("olympics-2028-mens-100m",
     "Who wins Olympics 2028 men's 100m?"),
    ("",
     "Will Mexico advance to the World Cup Round of 16?"),
])
def test_sports_markets_detected(slug, question):
    """Every sports market in the 173-file historical tape — and
    representative future sport types — must trigger sports-skip."""
    assert _is_sports_market(slug, question), (
        f"FALSE NEGATIVE: {slug!r} / {question!r} should be detected as sports"
    )


@pytest.mark.parametrize("slug,question", [
    ("will-china-invade-taiwan-before-2027",
     "Will China invade Taiwan before 2027?"),
    ("how-many-fed-rate-cuts-in-2026",
     "Will 2 Fed rate cuts happen in 2026?"),
    ("will-openais-valuation-hit-500b-by-december-31",
     "Will OpenAI's valuation hit $500B by December 31?"),
    ("which-company-has-best-ai-model-end-of-june",
     "Will Google have the best AI model end of June?"),
    ("will-bernie-sanders-win-the-2028-democratic-presidential-nom",
     "Will Bernie Sanders win the 2028 Democratic Presidential nomination?"),
    ("us-x-iran-permanent-peace-deal-by-may-31-2026",
     "US-Iran permanent peace deal by May 31, 2026?"),
    ("will-jesus-christ-return-before-2027",
     "Will Jesus Christ return before 2027?"),
    ("will-the-iranian-regime-fall-by-june-30",
     "Will the Iranian regime fall by June 30?"),
])
def test_non_sports_markets_not_flagged(slug, question):
    """Geopolitics / politics / AI / macro / religion markets must NOT
    trigger sports-skip — Haiku is fine on those."""
    assert not _is_sports_market(slug, question), (
        f"FALSE POSITIVE: {slug!r} should NOT be detected as sports"
    )


def test_empty_inputs_not_sports():
    """Empty slug + empty question is not sports (it's a malformed row)."""
    assert not _is_sports_market("", "")
    assert not _is_sports_market("", None or "")


# ---------------------------------------------------------------------
# Wire-through contract: estimate_p_yes() with a sports slug skips Haiku
# ---------------------------------------------------------------------

def test_estimate_returns_skip_payload_for_sports_market(monkeypatch):
    """When event_slug matches a sports pattern, estimate_p_yes must
    return the no-estimate stub WITHOUT calling Anthropic — the whole
    point of the 6/30 fix is to stop the 0.5 default from leaking into
    mispricing flags."""

    def boom_anthropic(*a, **kw):
        raise AssertionError(
            "Anthropic was called for a sports market — sports-skip routing broke"
        )

    monkeypatch.setattr(
        "markets.auto.polymarket_daily._load_anthropic_key",
        lambda: "test-key-should-not-be-used",
    )
    # If anyone refactors to call anthropic directly, this catches it.
    import sys
    fake_anthropic = type(sys)("anthropic")
    fake_anthropic.Anthropic = boom_anthropic  # type: ignore
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    result = estimate_p_yes(
        event_title="Will Uzbekistan win the 2026 FIFA World Cup",
        question="Will Uzbekistan win the 2026 FIFA World Cup?",
        current_market_p=0.012,
        event_slug="will-uzbekistan-win-the-2026-fifa-world-cup-773",
    )
    assert result["p_yes"] is None, "sports markets must return p_yes=None"
    assert result["conviction"] == "skip"
    assert "sports_market" in result["rationale"]


def test_estimate_falls_through_to_anthropic_for_non_sports(monkeypatch):
    """Non-sports markets must STILL flow to Haiku — the skip is sports-only.
    Mock the SDK to assert it's reached + return a deterministic value."""

    call_count = {"n": 0}

    class FakeContent:
        def __init__(self, text):
            self.text = text

    class FakeResponse:
        def __init__(self):
            self.content = [
                FakeContent('{"p_yes": 0.42, "conviction": "medium", '
                            '"rationale": "test"}')
            ]

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        @property
        def messages(self):
            outer = self

            class _MessagesNS:
                def create(self_inner, *a, **kw):
                    call_count["n"] += 1
                    return FakeResponse()

            return _MessagesNS()

    monkeypatch.setattr(
        "markets.auto.polymarket_daily._load_anthropic_key",
        lambda: "test-key",
    )
    import sys
    fake_anthropic = type(sys)("anthropic")
    fake_anthropic.Anthropic = FakeClient  # type: ignore
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    result = estimate_p_yes(
        event_title="Will China invade Taiwan before 2027",
        question="Will China invade Taiwan before 2027?",
        current_market_p=0.05,
        event_slug="will-china-invade-taiwan-before-2027",
    )
    assert call_count["n"] == 1, "Anthropic must be called for non-sports markets"
    assert result["p_yes"] == 0.42
    assert result["conviction"] == "medium"
