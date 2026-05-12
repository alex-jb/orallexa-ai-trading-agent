"""tests/test_markets_critic.py
─────────────────────────────────────────────────────────────
Critic agent (5th voice) parser + rendering tests.
Inspired by yorkeccak/Polyseer's Critic pattern (2026-05).

No network — these test the pure parsing + rendering logic.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from markets.event_debate import (
    CriticOutput, EventDebateOutput, _parse_critic,
)
from markets.queue import QueueEntry, render_entry
from markets.market import BinaryMarket


# ════════════════════════════════════════════════════════════════════
# CriticOutput dataclass + parser
# ════════════════════════════════════════════════════════════════════


def test_critic_parser_full_ok():
    raw = {
        "verdict": "OK",
        "failure_modes": [],
        "same_source_overlap": False,
        "missing_base_rate": False,
        "unverifiable_claims": [],
        "confirmation_drift": False,
        "summary": "Both sides cited independent sources + Judge anchored to base rate.",
    }
    c = _parse_critic(raw)
    assert c.verdict == "OK"
    assert c.failure_modes == []
    assert c.same_source_overlap is False
    assert "base rate" in c.summary


def test_critic_parser_caveat_with_flags():
    raw = {
        "verdict": "CAVEAT",
        "failure_modes": ["Bull and Bear both cited Reuters article"],
        "same_source_overlap": True,
        "missing_base_rate": True,
        "unverifiable_claims": ["'industry sources say' in Bull"],
        "confirmation_drift": False,
        "summary": "Same-source bias + missing base rate. Probability is informative but soft.",
    }
    c = _parse_critic(raw)
    assert c.verdict == "CAVEAT"
    assert c.same_source_overlap is True
    assert c.missing_base_rate is True
    assert len(c.failure_modes) == 1
    assert len(c.unverifiable_claims) == 1


def test_critic_parser_reject():
    raw = {
        "verdict": "REJECT",
        "failure_modes": [
            "Only one source cited across both sides",
            "No base rate",
            "All claims unverifiable",
        ],
        "same_source_overlap": True,
        "missing_base_rate": True,
        "unverifiable_claims": ["A", "B", "C"],
        "confirmation_drift": True,
        "summary": "Debate is structurally broken.",
    }
    c = _parse_critic(raw)
    assert c.verdict == "REJECT"
    assert c.confirmation_drift is True


def test_critic_parser_defaults_to_ok_on_garbage():
    """Defensive: if LLM returns junk, default to OK so pipeline doesn't break."""
    c = _parse_critic({})
    assert c.verdict == "OK"
    assert c.failure_modes == []

    c2 = _parse_critic({"verdict": "MAYBE_BAD", "failure_modes": "not a list"})
    assert c2.verdict == "OK"      # bad verdict → OK fallback
    assert c2.failure_modes == []   # bad list type → empty list


def test_critic_parser_coerces_types():
    """Defensive: non-string items in lists get coerced to str."""
    raw = {
        "verdict": "caveat",   # lowercase ok
        "failure_modes": [1, 2, "real"],
        "unverifiable_claims": [{"a": "b"}, "claim"],  # dict gets stringified
    }
    c = _parse_critic(raw)
    assert c.verdict == "CAVEAT"  # uppercase normalization
    assert len(c.failure_modes) == 3
    assert "1" in c.failure_modes
    assert "real" in c.failure_modes


# ════════════════════════════════════════════════════════════════════
# EventDebateOutput.has_critic_concerns
# ════════════════════════════════════════════════════════════════════


def _make_debate_output(critic: CriticOutput = None) -> EventDebateOutput:
    return EventDebateOutput(
        market_id="m1",
        platform="polymarket",
        question="Will X happen by July?",
        p_yes=0.61,
        bull_argument="strong case",
        bear_argument="weak case",
        judge_reasoning="Bull wins",
        market_price_at_debate=0.42,
        critic=critic,
    )


def test_no_critic_no_concerns():
    d = _make_debate_output(critic=None)
    assert d.has_critic_concerns is False


def test_critic_ok_no_concerns():
    d = _make_debate_output(critic=CriticOutput(verdict="OK"))
    assert d.has_critic_concerns is False


def test_critic_caveat_has_concerns():
    d = _make_debate_output(critic=CriticOutput(verdict="CAVEAT", summary="check this"))
    assert d.has_critic_concerns is True


def test_critic_reject_has_concerns():
    d = _make_debate_output(critic=CriticOutput(verdict="REJECT"))
    assert d.has_critic_concerns is True


# ════════════════════════════════════════════════════════════════════
# Queue card renders critic section when present
# ════════════════════════════════════════════════════════════════════


def _make_market() -> BinaryMarket:
    return BinaryMarket(
        platform="polymarket",
        market_id="iran-deal",
        ticker="iran-deal",
        question="Will US-Iran reach a deal by July 1?",
        category="geopolitics",
        status="open",
        close_time="2026-07-01T23:59:59Z",
        yes_price=0.42,
    )


def test_render_no_critic_omits_section():
    """Backward compat: cards without Critic shouldn't break or show empty sections."""
    debate = _make_debate_output(critic=None)
    entry = QueueEntry(market=_make_market(), debate=debate, suggested_position_usd=15.0)
    md = render_entry(entry)
    assert "Critic audit" not in md      # no section rendered
    assert "| Critic |" not in md         # no summary row
    assert "## Judge reasoning" in md     # other sections still there


def test_render_critic_ok_shows_summary_row_no_full_section():
    """OK verdict: show summary row in table, skip the full audit block."""
    critic = CriticOutput(
        verdict="OK",
        summary="Both sides independent + base rate cited.",
    )
    debate = _make_debate_output(critic=critic)
    entry = QueueEntry(market=_make_market(), debate=debate, suggested_position_usd=15.0)
    md = render_entry(entry)
    assert "✓ OK" in md
    assert "## Critic audit" not in md   # OK verdict → no separate block


def test_render_critic_caveat_shows_full_block():
    """CAVEAT: surface failure modes + structural flags + claims to HITL reviewer."""
    critic = CriticOutput(
        verdict="CAVEAT",
        failure_modes=["Both sides cited Reuters article from 5/9"],
        same_source_overlap=True,
        missing_base_rate=True,
        unverifiable_claims=["'industry sources say'"],
        summary="Same-source bias + missing base rate.",
    )
    debate = _make_debate_output(critic=critic)
    entry = QueueEntry(market=_make_market(), debate=debate, suggested_position_usd=15.0)
    md = render_entry(entry)
    assert "⚠ CAVEAT" in md
    assert "## Critic audit" in md
    assert "Reuters article" in md
    assert "same-source bias" in md
    assert "missing historical base-rate" in md
    assert "industry sources say" in md


def test_render_critic_reject_shows_full_block():
    critic = CriticOutput(
        verdict="REJECT",
        failure_modes=["Both sides cite same source", "No base rate", "All claims unverifiable"],
        same_source_overlap=True,
        missing_base_rate=True,
        confirmation_drift=True,
        summary="Debate structurally broken.",
    )
    debate = _make_debate_output(critic=critic)
    entry = QueueEntry(market=_make_market(), debate=debate, suggested_position_usd=15.0)
    md = render_entry(entry)
    assert "✗ REJECT" in md
    assert "## Critic audit" in md
    assert "structurally broken" in md
    assert "confirmation drift" in md
