"""
tests/test_layered_memory.py
──────────────────────────────────────────────────────────────────
Tests for engine/layered_memory.py — tiered bucketing + outcomes.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.layered_memory import LayeredMemory, TIERS, _age_days


@pytest.fixture
def mem(tmp_path):
    return LayeredMemory(path=tmp_path / "lm.json")


def _iso(now: datetime, days_ago: float) -> str:
    return (now - timedelta(days=days_ago)).isoformat()


# ── _age_days ──────────────────────────────────────────────────────────────


class TestAgeDays:
    def test_recent(self):
        now = datetime(2026, 4, 24, 12, 0)
        ts = (now - timedelta(days=3)).isoformat()
        assert 2.9 < _age_days(ts, now=now) < 3.1

    def test_garbage_returns_default(self):
        assert _age_days("not a date", now=datetime.now(), default=42.0) == 42.0


# ── record + persistence ───────────────────────────────────────────────────


class TestRecord:
    def test_record_persists(self, mem, tmp_path):
        mem.record("Analyst", "NVDA", "BULLISH", score=30, conviction=70)
        saved = json.loads((tmp_path / "lm.json").read_text(encoding="utf-8"))
        assert len(saved["records"]) == 1
        assert saved["records"][0]["role"] == "Analyst"
        assert saved["records"][0]["ticker"] == "NVDA"

    def test_record_truncates_reasoning(self, mem):
        mem.record("A", "NVDA", "BULLISH", reasoning="x" * 500)
        assert len(mem._data["records"][0]["reasoning"]) == 200


# ── bucketing ──────────────────────────────────────────────────────────────


class TestBucketing:
    def test_records_placed_in_correct_tiers(self, mem):
        now = datetime.now()
        mem.record("A", "NVDA", "BULLISH", timestamp=_iso(now, 2))   # short
        mem.record("A", "NVDA", "BEARISH", timestamp=_iso(now, 15))  # mid
        mem.record("A", "NVDA", "BULLISH", timestamp=_iso(now, 90))  # long

        ctx = mem.get_tiered_context("A", "NVDA", now=now)
        assert ctx["short_term"]["n"] == 1
        assert ctx["mid_term"]["n"] == 1
        assert ctx["long_term"]["n"] == 1

    def test_other_role_not_counted(self, mem):
        now = datetime.now()
        mem.record("A", "NVDA", "BULLISH", timestamp=_iso(now, 2))
        mem.record("B", "NVDA", "BULLISH", timestamp=_iso(now, 2))
        ctx = mem.get_tiered_context("A", "NVDA", now=now)
        assert ctx["short_term"]["n"] == 1

    def test_ticker_scope(self, mem):
        now = datetime.now()
        mem.record("A", "NVDA", "BULLISH", timestamp=_iso(now, 2))
        mem.record("A", "AAPL", "BULLISH", timestamp=_iso(now, 2))
        ctx = mem.get_tiered_context("A", "NVDA", now=now)
        assert ctx["short_term"]["n"] == 1

    def test_ticker_none_aggregates_all(self, mem):
        now = datetime.now()
        mem.record("A", "NVDA", "BULLISH", timestamp=_iso(now, 2))
        mem.record("A", "AAPL", "BULLISH", timestamp=_iso(now, 2))
        ctx = mem.get_tiered_context("A", ticker=None, now=now)
        assert ctx["short_term"]["n"] == 2


# ── update_outcome + accuracy ──────────────────────────────────────────────


class TestOutcomes:
    def test_bullish_prediction_correct_when_positive_return(self, mem):
        mem.record("A", "NVDA", "BULLISH")
        updated = mem.update_outcome("A", "NVDA", forward_return=0.05)
        assert updated == 1
        rec = mem._data["records"][0]
        assert rec["correct"] is True
        assert rec["outcome"] == "BULLISH"

    def test_bearish_prediction_correct_when_negative_return(self, mem):
        mem.record("A", "NVDA", "BEARISH")
        mem.update_outcome("A", "NVDA", forward_return=-0.04)
        assert mem._data["records"][0]["correct"] is True

    def test_neutral_threshold_applied(self, mem):
        mem.record("A", "NVDA", "NEUTRAL")
        mem.update_outcome("A", "NVDA", forward_return=0.01)  # below 0.02 threshold
        assert mem._data["records"][0]["outcome"] == "NEUTRAL"
        assert mem._data["records"][0]["correct"] is True

    def test_already_evaluated_skipped(self, mem):
        mem.record("A", "NVDA", "BULLISH")
        mem.update_outcome("A", "NVDA", forward_return=0.05)
        # Second update shouldn't change anything (0 records updated)
        assert mem.update_outcome("A", "NVDA", forward_return=-0.05) == 0

    def test_accuracy_computed_per_tier(self, mem):
        now = datetime.now()
        # Short-term: 1/2 correct
        mem.record("A", "NVDA", "BULLISH", timestamp=_iso(now, 2))
        mem.record("A", "NVDA", "BEARISH", timestamp=_iso(now, 3))
        mem.update_outcome("A", "NVDA", forward_return=0.05)  # both get 0.05
        # First BULLISH is correct, second BEARISH is wrong

        ctx = mem.get_tiered_context("A", "NVDA", now=now)
        assert ctx["short_term"]["n"] == 2
        assert ctx["short_term"]["correct"] == 1
        assert ctx["short_term"]["accuracy"] == 0.5


# ── narrative ──────────────────────────────────────────────────────────────


class TestNarrative:
    def test_empty_when_insufficient(self, mem):
        mem.record("A", "NVDA", "BULLISH")
        narr = mem.narrative("A", "NVDA")
        assert "Insufficient" in narr

    def test_summarizes_tiers_with_enough_data(self, mem):
        now = datetime.now()
        # 3+ records in short term, all evaluated
        for _ in range(3):
            mem.record("A", "NVDA", "BULLISH", timestamp=_iso(now, 1))
        mem.update_outcome("A", "NVDA", forward_return=0.05)
        narr = mem.narrative("A", "NVDA")
        assert "short_term" in narr
        assert "100%" in narr


# ── pruning ────────────────────────────────────────────────────────────────


class TestPruning:
    def test_short_term_capped(self, mem):
        now = datetime.now()
        # Exceed the short_term cap (100)
        for i in range(120):
            mem.record(
                "A", "NVDA", "BULLISH",
                timestamp=_iso(now, 0.01 * i),  # all within 7 days, oldest first
            )
        # After pruning, short_term should be ≤ 100
        short_cap = next(t.max_records for t in TIERS if t.name == "short_term")
        remaining_short = sum(
            1 for r in mem._data["records"]
            if _age_days(r["timestamp"], now=datetime.now()) < 7
        )
        assert remaining_short <= short_cap
