"""
tests/test_shared_memory.py
──────────────────────────────────────────────────────────────────
Tests for engine/shared_memory.py — read-aggregator over role +
layered memory.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.layered_memory import LayeredMemory
from engine.shared_memory import SharedMemory


def _iso(now: datetime, days_ago: float) -> str:
    return (now - timedelta(days=days_ago)).isoformat()


@pytest.fixture
def lm(tmp_path):
    return LayeredMemory(path=tmp_path / "lm.json")


# ── summary_for ────────────────────────────────────────────────────────────


class TestSummaryFor:
    def test_empty_memories_returns_empty(self, lm):
        sm = SharedMemory(role_mem=False, layered_mem=lm)
        assert sm.summary_for("X", "NVDA") == ""

    def test_layered_narrative_included_when_sufficient(self, lm):
        now = datetime.now()
        for _ in range(4):
            lm.record("Conservative", "NVDA", "BULLISH",
                      timestamp=_iso(now, 1))
        lm.update_outcome("Conservative", "NVDA", forward_return=0.05)
        sm = SharedMemory(role_mem=False, layered_mem=lm)
        out = sm.summary_for("Conservative", "NVDA")
        assert "Conservative accuracy" in out
        assert "100%" in out

    def test_cross_role_appended(self, lm):
        # Aggressive made calls on NVDA; we ask from Conservative's POV
        now = datetime.now()
        for _ in range(4):
            lm.record("Aggressive", "NVDA", "BULLISH",
                      timestamp=_iso(now, 2))
        lm.update_outcome("Aggressive", "NVDA", forward_return=0.05)
        sm = SharedMemory(role_mem=False, layered_mem=lm)
        out = sm.summary_for("Conservative", "NVDA")
        assert "Other roles on NVDA" in out
        assert "BULLISH" in out


# ── cross_role_consensus ───────────────────────────────────────────────────


class TestCrossRole:
    def test_excludes_self(self, lm):
        now = datetime.now()
        lm.record("X", "NVDA", "BULLISH", timestamp=_iso(now, 1))
        lm.record("Y", "NVDA", "BEARISH", timestamp=_iso(now, 1))
        sm = SharedMemory(role_mem=False, layered_mem=lm)
        out = sm.cross_role_consensus("NVDA", exclude_role="X")
        assert "BEARISH" in out
        # X's bullish call should be excluded — count is 0 BULLISH
        assert "0 BULLISH" in out

    def test_per_role_accuracy_when_enough_data(self, lm):
        now = datetime.now()
        for _ in range(4):
            lm.record("Q", "NVDA", "BULLISH", timestamp=_iso(now, 2))
        lm.update_outcome("Q", "NVDA", forward_return=0.05)
        sm = SharedMemory(role_mem=False, layered_mem=lm)
        out = sm.cross_role_consensus("NVDA")
        assert "Q: 100% acc" in out

    def test_below_threshold_no_per_role(self, lm):
        now = datetime.now()
        lm.record("Q", "NVDA", "BULLISH", timestamp=_iso(now, 2))
        lm.update_outcome("Q", "NVDA", forward_return=0.05)
        sm = SharedMemory(role_mem=False, layered_mem=lm)
        out = sm.cross_role_consensus("NVDA")
        assert "no per-role accuracy yet" in out

    def test_other_ticker_excluded(self, lm):
        now = datetime.now()
        lm.record("X", "NVDA", "BULLISH", timestamp=_iso(now, 1))
        lm.record("X", "AAPL", "BEARISH", timestamp=_iso(now, 1))
        sm = SharedMemory(role_mem=False, layered_mem=lm)
        out = sm.cross_role_consensus("NVDA")
        assert "1 BULLISH" in out

    def test_empty_when_no_data(self, lm):
        sm = SharedMemory(role_mem=False, layered_mem=lm)
        assert sm.cross_role_consensus("NVDA") == ""


# ── full_context ───────────────────────────────────────────────────────────


class TestFullContext:
    def test_includes_all_when_data_present(self, lm):
        now = datetime.now()
        for _ in range(4):
            lm.record("Q", "NVDA", "BULLISH", timestamp=_iso(now, 2))
        lm.update_outcome("Q", "NVDA", forward_return=0.05)
        sm = SharedMemory(role_mem=False, layered_mem=lm)
        ctx = sm.full_context("Q", "NVDA")
        assert ctx["role"] == "Q"
        assert ctx["ticker"] == "NVDA"
        assert "layered_tiers" in ctx
        assert "layered_narrative" in ctx

    def test_minimal_when_empty(self, lm):
        sm = SharedMemory(role_mem=False, layered_mem=lm)
        ctx = sm.full_context("X", "NVDA")
        # role/ticker always present; layered_tiers will be empty dict per tier
        assert ctx["role"] == "X"
