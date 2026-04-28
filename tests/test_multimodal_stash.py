"""
tests/test_multimodal_stash.py
──────────────────────────────────────────────────────────────────
Day 6 integration test — verify the multimodal_diff produced by
run_perspective_panel(multimodal=True) round-trips through:

  1. multi_agent_analysis stashing it onto decision.extra
  2. DecisionOutput.to_dict() carrying extra through
  3. save_decision writing it to disk

Same pattern as test_debate_stash.py — guards Phase B's eval-set
extractor against silent regressions when someone refactors
multi_agent_analysis or DecisionOutput.

The full multi-agent pipeline isn't run end-to-end (slow + needs
yfinance + LLM); we test the stash-and-roundtrip plumbing directly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.decision import DecisionOutput


@pytest.fixture
def fake_diff():
    return {
        "pairs": [
            {
                "role": "Quant Researcher",
                "text":   {"bias": "BULLISH", "score": 30, "conviction": 60,
                           "reasoning": "RSI rising"},
                "vision": {"bias": "BEARISH", "score": -20, "conviction": 55,
                           "reasoning": "Head and shoulders forming"},
                "agree": False,
                "score_delta": -50,
                "conviction_delta": -5,
            }
        ],
        "agreement_rate": 0.0,
        "avg_score_delta": -50.0,
        "avg_conviction_delta": -5.0,
        "n_pairs": 1,
    }


# ── 1. Stash logic carries the diff onto extra ───────────────────────────


class TestStashLogic:
    """Exercise the conditional that copies panel_result['multimodal_diff']
    onto final_decision.extra. Replicates the multi_agent_analysis snippet
    inline so we can test it without spinning the whole pipeline."""

    def _stash(self, decision: DecisionOutput, panel_result: dict) -> None:
        # Mirror engine/multi_agent_analysis.py's stash block exactly.
        mm_diff = panel_result.get("multimodal_diff")
        if mm_diff and mm_diff.get("n_pairs", 0) > 0:
            decision.extra["multimodal_diff"] = mm_diff

    def _bare_decision(self):
        return DecisionOutput(
            decision="BUY", confidence=72.0, risk_level="MEDIUM",
            reasoning=[], probabilities={"up": 0.6, "neutral": 0.25, "down": 0.15},
            source="multi_agent",
        )

    def test_stashes_when_diff_has_pairs(self, fake_diff):
        d = self._bare_decision()
        self._stash(d, {"multimodal_diff": fake_diff})
        assert "multimodal_diff" in d.extra
        assert d.extra["multimodal_diff"]["n_pairs"] == 1
        assert d.extra["multimodal_diff"]["pairs"][0]["role"] == "Quant Researcher"

    def test_no_stash_when_diff_missing(self):
        d = self._bare_decision()
        self._stash(d, {})
        assert "multimodal_diff" not in d.extra

    def test_no_stash_when_n_pairs_zero(self):
        # multimodal=True but render failed → diff exists with n_pairs=0.
        d = self._bare_decision()
        empty_diff = {
            "pairs": [], "agreement_rate": 0.0,
            "avg_score_delta": 0.0, "avg_conviction_delta": 0.0, "n_pairs": 0,
        }
        self._stash(d, {"multimodal_diff": empty_diff})
        # Empty diff doesn't pollute decision_log — only real pairings stash.
        assert "multimodal_diff" not in d.extra


# ── 2. to_dict() carries multimodal_diff through ─────────────────────────


class TestToDictCarriesDiff:
    def test_extra_serializes_diff(self, fake_diff):
        d = DecisionOutput(
            decision="BUY", confidence=70.0, risk_level="LOW",
            reasoning=[], probabilities={"up": 0.65, "neutral": 0.20, "down": 0.15},
            source="multi_agent",
        )
        d.extra["multimodal_diff"] = fake_diff
        out = d.to_dict()
        assert "extra" in out
        assert out["extra"]["multimodal_diff"]["n_pairs"] == 1
        # Nested types serialize cleanly (dataclasses-as-dict already works).
        assert out["extra"]["multimodal_diff"]["pairs"][0]["agree"] is False


# ── 3. save_decision round-trips the diff through disk ───────────────────


class TestSaveDecisionRoundtrip:
    def test_diff_survives_save_load(self, fake_diff, tmp_path, monkeypatch):
        from engine import decision_log

        log_path = tmp_path / "decision_log.json"
        monkeypatch.setattr(decision_log, "LOG_PATH", str(log_path))

        d = DecisionOutput(
            decision="BUY", confidence=72.0, risk_level="MEDIUM",
            reasoning=[], probabilities={"up": 0.6, "neutral": 0.25, "down": 0.15},
            source="multi_agent",
        )
        d.extra["multimodal_diff"] = fake_diff

        decision_log.save_decision(
            d, "NVDA", mode="swing", timeframe="1D", entry_price=480.50,
        )

        records = json.loads(log_path.read_text(encoding="utf-8"))
        assert len(records) == 1
        rec = records[0]
        assert rec["ticker"] == "NVDA"
        assert "extra" in rec
        diff = rec["extra"]["multimodal_diff"]
        assert diff["n_pairs"] == 1
        assert diff["agreement_rate"] == 0.0
        assert diff["pairs"][0]["role"] == "Quant Researcher"
        assert diff["pairs"][0]["score_delta"] == -50


# ── 4. Phase-B-style extractor finds stashed records ─────────────────────


class TestEligibilityForFutureExtractor:
    """When we eventually build a multimodal eval-set extractor (mirrors
    scripts/build_dspy_eval_set.py), it'll filter on extra.multimodal_diff
    being a dict with at least 1 pair. Verify that gate fires on a
    real-shaped record and skips records without the stash."""

    def test_extractor_gate_finds_only_stashed_records(self, fake_diff, tmp_path, monkeypatch):
        from engine import decision_log

        log_path = tmp_path / "decision_log.json"
        monkeypatch.setattr(decision_log, "LOG_PATH", str(log_path))

        # One record WITH multimodal stash …
        d_mm = DecisionOutput(
            decision="BUY", confidence=70.0, risk_level="LOW",
            reasoning=[], probabilities={"up": 0.65, "neutral": 0.20, "down": 0.15},
            source="multi_agent",
        )
        d_mm.extra["multimodal_diff"] = fake_diff
        decision_log.save_decision(d_mm, "NVDA", mode="swing", timeframe="1D")

        # … and one without (vanilla deep-analysis).
        d_plain = DecisionOutput(
            decision="WAIT", confidence=50.0, risk_level="MEDIUM",
            reasoning=[], probabilities={"up": 0.34, "neutral": 0.33, "down": 0.33},
            source="multi_agent",
        )
        decision_log.save_decision(d_plain, "AAPL", mode="swing", timeframe="1D")

        records = json.loads(log_path.read_text(encoding="utf-8"))
        eligible = [
            r for r in records
            if isinstance(r.get("extra"), dict)
            and isinstance(r["extra"].get("multimodal_diff"), dict)
            and r["extra"]["multimodal_diff"].get("n_pairs", 0) > 0
        ]
        assert len(eligible) == 1
        assert eligible[0]["ticker"] == "NVDA"
