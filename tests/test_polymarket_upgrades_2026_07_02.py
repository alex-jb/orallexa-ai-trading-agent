"""
tests/test_polymarket_upgrades_2026_07_02.py
──────────────────────────────────────────────────────────────────
Pins the 2026-07-02 Tier-1 upgrades from the deep-research roadmap:

  #2 political-market extremization (arxiv 2602.19520)
  #3 72h news-lag skip (Prophet Arena, arxiv 2510.17638)
  #4 edge_thesis required field (Kris Longmore 2026 edge theory)

Each upgrade has its own reason for existing, cited in the module
docstrings. These tests exist to prevent someone later from thinking
"why is this if/else here, let me simplify" and re-opening the loss
window we just closed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from markets.auto.polymarket_daily import (
    NEWS_LAG_SKIP_HOURS,
    POLITICAL_COMPRESSION_ZONE,
    POLITICAL_EXTREMIZATION_FACTOR,
    _extremize_political_p,
    _hours_until_resolution,
    _is_political_market,
    _is_within_news_lag_window,
    estimate_p_yes,
)


# ═════════════════════════════════════════════════════════════════
# #3 — 72h news-lag skip
# ═════════════════════════════════════════════════════════════════

def _iso_hours_from_now(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def test_hours_until_resolution_positive_future_date():
    end = _iso_hours_from_now(48)
    hrs = _hours_until_resolution(end)
    assert hrs is not None
    assert 47.5 < hrs < 48.5, hrs


def test_hours_until_resolution_negative_for_past():
    end = _iso_hours_from_now(-24)
    hrs = _hours_until_resolution(end)
    assert hrs is not None
    assert hrs < 0


def test_hours_until_resolution_none_on_bad_input():
    assert _hours_until_resolution(None) is None
    assert _hours_until_resolution("") is None
    assert _hours_until_resolution("not a date") is None


def test_news_lag_skip_true_within_window():
    assert _is_within_news_lag_window(_iso_hours_from_now(24)) is True
    assert _is_within_news_lag_window(_iso_hours_from_now(NEWS_LAG_SKIP_HOURS - 1)) is True


def test_news_lag_skip_false_outside_window():
    # Well beyond the 72h window
    assert _is_within_news_lag_window(_iso_hours_from_now(NEWS_LAG_SKIP_HOURS + 24)) is False
    # Already resolved (negative) — not in a future window
    assert _is_within_news_lag_window(_iso_hours_from_now(-1)) is False


def test_news_lag_skip_false_on_missing_end_date():
    """A missing endDate should NOT cause us to skip — better to
    Haiku-estimate a long-horizon market than skip a valid one over
    a parse quirk."""
    assert _is_within_news_lag_window(None) is False


def test_estimate_p_yes_returns_news_lag_skip_within_72h(monkeypatch):
    """estimate_p_yes must short-circuit BEFORE calling Anthropic when
    the market is within 72h of resolution."""
    monkeypatch.setattr(
        "markets.auto.polymarket_daily._load_anthropic_key",
        lambda: "should-not-be-called",
    )

    result = estimate_p_yes(
        event_title="Will Powell resign by July 8?",
        question="Will Powell resign by July 8?",
        current_market_p=0.05,
        event_slug="will-powell-resign-by-july-8",
        end_date=_iso_hours_from_now(24),  # 24h out — inside 72h window
    )
    assert result["p_yes"] is None
    assert result["conviction"] == "skip"
    assert "news_lag_skip" in result["rationale"]


# ═════════════════════════════════════════════════════════════════
# #2 — political-market extremization
# ═════════════════════════════════════════════════════════════════

def test_is_political_market_detects_common_political_keywords():
    for kw in ["Fed rate cut in 2026", "Will Trump nominate a SCOTUS justice",
               "China-Taiwan invasion 2027", "Fed FOMC meeting outcome"]:
        assert _is_political_market(kw, "", "") is True, kw


def test_is_political_market_false_on_non_political():
    for kw in ["Will Uzbekistan win the 2026 FIFA World Cup",
               "Best AI model at end of June",
               "OpenAI valuation hit $500B by December 31",
               "SpaceX Starship reaches orbit 2026"]:
        assert _is_political_market(kw, "", "") is False, kw


def test_extremize_political_p_amplifies_agreement_in_compression_zone():
    """When market_p = 0.45 and our_p = 0.55 (both above 0.5? no wait —
    market_p 0.45 is BELOW, our_p 0.55 is ABOVE), that's directional
    disagreement — should NOT extremize. Rebuild test."""
    # Both above 0.5, market in compression zone — should extremize
    market_p = 0.6
    our_p = 0.7  # +0.1 above market
    extremized = _extremize_political_p(our_p, market_p)
    # Should be 0.6 + 1.3 * 0.1 = 0.73
    assert 0.72 < extremized <= 0.75, extremized


def test_extremize_political_p_no_change_outside_compression_zone():
    """market_p outside [0.30, 0.70] → no extremization."""
    # market_p = 0.15 (below zone)
    assert _extremize_political_p(our_p=0.22, market_p=0.15) == 0.22
    # market_p = 0.85 (above zone)
    assert _extremize_political_p(our_p=0.82, market_p=0.85) == 0.82


def test_extremize_political_p_no_change_on_directional_disagreement():
    """When our_p and market_p disagree directionally (one above 0.5,
    other below), extremization would flip the bet — that's not the
    correction we're making."""
    # market at 0.4, we say 0.6 — flip direction, no extremize
    assert _extremize_political_p(our_p=0.6, market_p=0.4) == 0.6


def test_extremize_political_p_clamps_to_never_cross_50():
    """Even with aggressive extremization, we never cross 0.5."""
    # market 0.5, our 0.55 (bull), factor 0.3 → 0.5 + 1.3 * 0.05 = 0.565
    # Well above 0.5, OK.
    extremized = _extremize_political_p(our_p=0.55, market_p=0.5)
    assert extremized >= 0.5


def test_extremize_political_p_none_market_returns_raw():
    """market_p unknown → no reference point → no change."""
    assert _extremize_political_p(our_p=0.42, market_p=None) == 0.42


# ═════════════════════════════════════════════════════════════════
# #4 — edge_thesis required field
# ═════════════════════════════════════════════════════════════════

def test_estimate_p_yes_preserves_edge_thesis_when_present(monkeypatch):
    """When the model returns a specific edge_thesis, it flows through
    to the result dict verbatim (up to 300 chars)."""
    monkeypatch.setattr(
        "markets.auto.polymarket_daily._load_anthropic_key",
        lambda: "test-key",
    )
    _install_fake_anthropic(monkeypatch, response_json={
        "p_yes": 0.42,
        "conviction": "medium",
        "rationale": "test rationale",
        "edge_thesis": "Retail traders overweight recency and price in Fed dovishness too quickly.",
    })
    result = estimate_p_yes(
        event_title="Will there be 2 Fed rate cuts in 2026",
        question="Will 2 Fed rate cuts happen in 2026?",
        current_market_p=0.35,
        event_slug="how-many-fed-rate-cuts-in-2026-2-cuts",
    )
    assert result["edge_thesis"] is not None
    assert "retail traders" in result["edge_thesis"].lower()
    assert result["conviction"] == "medium"


def test_estimate_p_yes_null_edge_thesis_downgrades_conviction(monkeypatch):
    """When the model returns null edge_thesis (or omits it), conviction
    MUST be downgraded to 'low' — this is the whole point of the field.
    A view without an economic driver is a random walk."""
    monkeypatch.setattr(
        "markets.auto.polymarket_daily._load_anthropic_key",
        lambda: "test-key",
    )
    _install_fake_anthropic(monkeypatch, response_json={
        "p_yes": 0.42,
        "conviction": "high",  # model claims high — we override to low
        "rationale": "test",
        "edge_thesis": None,
    })
    result = estimate_p_yes(
        event_title="Will 2 Fed rate cuts happen in 2026",
        question="Will 2 Fed rate cuts happen in 2026?",
        current_market_p=0.35,
        event_slug="how-many-fed-rate-cuts-in-2026-2-cuts",
    )
    assert result["edge_thesis"] is None
    assert result["conviction"] == "low", (
        "null edge_thesis MUST downgrade to low — the point of the field"
    )


def test_estimate_p_yes_empty_string_edge_thesis_treated_as_null(monkeypatch):
    """Whitespace/empty edge_thesis is not a thesis. Downgrade conviction."""
    monkeypatch.setattr(
        "markets.auto.polymarket_daily._load_anthropic_key",
        lambda: "test-key",
    )
    _install_fake_anthropic(monkeypatch, response_json={
        "p_yes": 0.42,
        "conviction": "high",
        "rationale": "test",
        "edge_thesis": "   ",
    })
    result = estimate_p_yes(
        event_title="Will 2 Fed rate cuts happen in 2026",
        question="Will 2 Fed rate cuts happen in 2026?",
        current_market_p=0.35,
    )
    assert result["edge_thesis"] is None
    assert result["conviction"] == "low"


# ═════════════════════════════════════════════════════════════════
# Test helper
# ═════════════════════════════════════════════════════════════════

def _install_fake_anthropic(monkeypatch, *, response_json: dict) -> None:
    """Inject a fake Anthropic SDK that returns the given JSON body
    verbatim wrapped in a text block. Used by any test that needs the
    Haiku call path to land in the parsing / normalization code."""
    import json as _json
    import sys

    class FakeContent:
        def __init__(self, text: str):
            self.text = text

    class FakeResponse:
        def __init__(self, text: str):
            self.content = [FakeContent(text)]

    class _Messages:
        def create(self, *a, **kw):
            return FakeResponse(_json.dumps(response_json))

    class FakeClient:
        def __init__(self, *a, **kw):
            self.messages = _Messages()

    fake_anthropic = type(sys)("anthropic")
    fake_anthropic.Anthropic = FakeClient  # type: ignore
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)
