"""
tests/test_portfolio_manager.py
──────────────────────────────────────────────────────────────────
Tests for engine/portfolio_manager.py — approve_decision + helpers.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.portfolio_manager import (
    approve_decision,
    Position,
    _normalize_direction,
    _same_direction_streak,
)


# ── Helpers ───────────────────────────────────────────────────────────────


def _decision(direction: str = "BUY", confidence: int = 70,
              signal_strength: int = 60, sector: str | None = None) -> dict:
    d = {"decision": direction, "confidence": confidence, "signal_strength": signal_strength}
    if sector:
        d["sector"] = sector
    return d


# ── _normalize_direction ───────────────────────────────────────────────────


class TestNormalizeDirection:
    @pytest.mark.parametrize("raw,expected", [
        ("BUY", "BUY"), ("long", "BUY"), ("BULLISH", "BUY"),
        ("sell", "SELL"), ("short", "SELL"), ("Bearish", "SELL"),
        ("HOLD", "HOLD"), ("wait", "HOLD"), ("neutral", "HOLD"), ("PASS", "HOLD"),
        ("", "HOLD"),
    ])
    def test_mapping(self, raw, expected):
        assert _normalize_direction({"decision": raw}) == expected


# ── _same_direction_streak ─────────────────────────────────────────────────


class TestSameDirectionStreak:
    def test_empty(self):
        assert _same_direction_streak([]) == 0

    def test_all_hold(self):
        assert _same_direction_streak([{"decision": "HOLD"}] * 3) == 0

    def test_all_same(self):
        assert _same_direction_streak([{"decision": "BUY"}] * 5) == 5

    def test_break_on_change(self):
        assert _same_direction_streak([
            {"decision": "BUY"}, {"decision": "BUY"}, {"decision": "SELL"},
            {"decision": "BUY"},
        ]) == 2


# ── approve_decision: confidence gate ──────────────────────────────────────


class TestConfidenceGate:
    def test_below_min_rejected(self):
        r = approve_decision(ticker="NVDA", decision=_decision(confidence=30))
        assert r["approved"] is False
        assert "below minimum" in r["reason"]
        assert r["scaled_position_pct"] == 0.0

    def test_at_min_approved(self):
        r = approve_decision(ticker="NVDA", decision=_decision(confidence=40))
        assert r["approved"] is True

    def test_hold_bypasses_sizing(self):
        r = approve_decision(ticker="NVDA", decision=_decision("HOLD", confidence=80))
        assert r["approved"] is True
        assert r["scaled_position_pct"] == 0.0
        assert "HOLD" in r["reason"]


# ── approve_decision: concentration ────────────────────────────────────────


class TestConcentration:
    def test_buy_rejected_when_over_max(self):
        portfolio = [Position("NVDA", 3_000)]
        r = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=80),
            portfolio=portfolio,
            portfolio_value=10_000,
        )
        assert r["approved"] is False
        assert "30.0%" in r["reason"]

    def test_buy_allowed_when_under_max(self):
        portfolio = [Position("NVDA", 500)]
        r = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=80),
            portfolio=portfolio,
            portfolio_value=10_000,
        )
        assert r["approved"] is True
        assert r["scaled_position_pct"] > 0

    def test_sell_not_blocked_by_existing_position(self):
        portfolio = [Position("NVDA", 5_000)]
        r = approve_decision(
            ticker="NVDA",
            decision=_decision("SELL", confidence=80),
            portfolio=portfolio,
            portfolio_value=10_000,
        )
        assert r["approved"] is True


# ── approve_decision: sector concentration ─────────────────────────────────


class TestSectorConcentration:
    def test_sector_warning_when_crowded(self):
        portfolio = [
            Position("AAPL", 2_500, sector="Tech"),
            Position("MSFT", 2_500, sector="Tech"),
        ]
        r = approve_decision(
            ticker="GOOGL",
            decision=_decision("BUY", confidence=80, sector="Tech"),
            portfolio=portfolio,
            portfolio_value=10_000,
        )
        assert r["approved"] is True
        assert any("Tech" in w for w in r["warnings"])

    def test_no_warning_when_sector_unknown(self):
        r = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=80),
            portfolio_value=10_000,
        )
        assert r["warnings"] == []


# ── approve_decision: direction streak ─────────────────────────────────────


class TestDirectionStreak:
    def test_long_streak_warns(self):
        r = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=80),
            recent_decisions=[{"decision": "BUY"}] * 6,
        )
        assert r["approved"] is True
        assert any("bias" in w.lower() for w in r["warnings"])

    def test_short_streak_no_warn(self):
        r = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=80),
            recent_decisions=[{"decision": "BUY"}] * 2,
        )
        assert not any("bias" in w.lower() for w in r["warnings"])


# ── approve_decision: sizing ──────────────────────────────────────────────


class TestSizing:
    def test_high_confidence_bigger_position(self):
        low = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=50, signal_strength=50),
        )
        high = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=90, signal_strength=80),
        )
        assert high["scaled_position_pct"] > low["scaled_position_pct"]

    def test_warnings_trim_position(self):
        clean = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=80, signal_strength=70),
        )
        with_warn = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=80, signal_strength=70),
            recent_decisions=[{"decision": "BUY"}] * 6,
        )
        assert with_warn["scaled_position_pct"] < clean["scaled_position_pct"]

    def test_headroom_respected(self):
        # Existing 15% position + high-conf BUY → scaled to remaining 5%
        portfolio = [Position("NVDA", 1_500)]
        r = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=95, signal_strength=90),
            portfolio=portfolio,
            portfolio_value=10_000,
        )
        assert r["approved"] is True
        assert r["scaled_position_pct"] <= 5.0  # 20% cap - 15% existing

    def test_never_exceeds_max_position_pct(self):
        r = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=100, signal_strength=100),
            rules={"max_position_pct": 10.0},
        )
        assert r["scaled_position_pct"] <= 10.0


# ── approve_decision: rules override ──────────────────────────────────────


class TestRulesOverride:
    def test_custom_min_confidence(self):
        r = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=60),
            rules={"min_confidence": 70},
        )
        assert r["approved"] is False

    def test_custom_max_position(self):
        portfolio = [Position("NVDA", 1_000)]
        r = approve_decision(
            ticker="NVDA",
            decision=_decision("BUY", confidence=80),
            portfolio=portfolio,
            portfolio_value=10_000,
            rules={"max_single_position_pct": 5.0},
        )
        assert r["approved"] is False  # already 10%, max 5%


# ── approve_decision: output shape ────────────────────────────────────────


class TestOutputShape:
    def test_has_all_required_fields(self):
        r = approve_decision(ticker="NVDA", decision=_decision())
        assert set(r.keys()) >= {
            "approved", "scaled_position_pct", "reason", "warnings",
            "original_confidence", "adjusted_confidence", "checks",
        }
        assert isinstance(r["warnings"], list)
        assert isinstance(r["checks"], dict)
