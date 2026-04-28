"""
tests/test_debate_stash.py
──────────────────────────────────────────────────────────────────
Integration test for the Phase B prerequisite: every deep-analysis
debate must persist Bull/Bear/Judge text on `decision.extra['debate']`
so `scripts/build_dspy_eval_set.py` can rebuild a real eval set
without re-running the LLM pipeline.

The 294-record decision_log currently has 0 rows with debate text
because the stash was added in commit f11c79b (Phase 10) and no
deep-analysis runs have landed since. This test guards against
*future* regressions of the stash itself — three things must hold:

  1. `run_lightweight_debate` populates `out.extra['debate']` with
     bull/bear/judge fields when all 3 LLM calls succeed.
  2. `DecisionOutput.to_dict()` carries the `extra` dict through.
  3. `save_decision` round-trips the field through disk.

LLM calls are mocked at the module level (`_call_bull`, `_call_bear`,
`_call_judge`) so this test runs in <1s with no API key.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from models.decision import DecisionOutput


@pytest.fixture
def initial_decision():
    return DecisionOutput(
        decision="BUY",
        confidence=60.0,
        risk_level="MEDIUM",
        reasoning=["initial signal: trend up + RSI healthy"],
        probabilities={"up": 0.55, "neutral": 0.30, "down": 0.15},
        source="multi_agent",
        signal_strength=70.0,
    )


@pytest.fixture
def summary():
    # Minimal context shape; _build_context reads .get(...) freely.
    return {
        "ticker":       "NVDA",
        "current_price": 480.50,
        "indicators":   {"rsi": 58, "macd_hist": 0.42},
        "regime":       "trending",
    }


# ── 1. extra['debate'] is populated ────────────────────────────────────────


class TestDebateStashPopulated:
    def test_extra_debate_contains_full_text(self, initial_decision, summary):
        from llm import debate

        bull_text = "Bull: Strong setup with earnings beat and sector rotation."
        bear_text = "Bear: Valuation extended, watch for rejection at resistance."
        judge_data = {
            "decision":           "BUY",
            "confidence":         72,
            "risk_level":         "MEDIUM",
            "up_probability":     0.6,
            "neutral_probability": 0.25,
            "down_probability":   0.15,
            "reasoning_summary":  "Bull case wins on momentum + earnings.",
            "reasoning_detail":   "Three factors tip the balance toward BUY.",
        }

        with patch.object(debate, "get_client"), \
             patch.object(debate, "_call_bull", return_value=bull_text), \
             patch.object(debate, "_call_bear", return_value=bear_text), \
             patch.object(debate, "_call_judge", return_value=judge_data):
            out = debate.run_lightweight_debate(initial_decision, summary, "NVDA")

        assert "debate" in out.extra
        d = out.extra["debate"]
        assert d["bull_argument"] == bull_text
        assert d["bear_argument"] == bear_text
        assert d["judge_summary"] == judge_data["reasoning_summary"]
        assert d["judge_detail"] == judge_data["reasoning_detail"]
        assert d["judge_decision"] == "BUY"
        assert d["judge_confidence"] == 72
        assert d["judge_risk_level"] == "MEDIUM"

    def test_long_arguments_truncated_to_2000_chars(self, initial_decision, summary):
        from llm import debate

        long_bull = "Bull thesis. " * 1000  # ~13,000 chars
        long_bear = "Bear thesis. " * 1000

        judge_data = {
            "decision": "WAIT", "confidence": 50, "risk_level": "MEDIUM",
            "up_probability": 0.34, "neutral_probability": 0.33, "down_probability": 0.33,
            "reasoning_summary": "Even.", "reasoning_detail": "Balanced.",
        }

        with patch.object(debate, "get_client"), \
             patch.object(debate, "_call_bull", return_value=long_bull), \
             patch.object(debate, "_call_bear", return_value=long_bear), \
             patch.object(debate, "_call_judge", return_value=judge_data):
            out = debate.run_lightweight_debate(initial_decision, summary, "NVDA")

        # Truncation guards the eval-set JSONL from blowing up to MB-per-row.
        assert len(out.extra["debate"]["bull_argument"]) == 2000
        assert len(out.extra["debate"]["bear_argument"]) == 2000

    def test_failure_in_any_stage_returns_initial_unchanged(self, initial_decision, summary):
        """Graceful-degradation contract: if any stage raises, no extra mutation."""
        from llm import debate

        with patch.object(debate, "get_client"), \
             patch.object(debate, "_call_bull", side_effect=RuntimeError("api 500")):
            out = debate.run_lightweight_debate(initial_decision, summary, "NVDA")

        # The same DecisionOutput identity comes back; extra unchanged.
        assert out is initial_decision
        assert "debate" not in out.extra


# ── 2. to_dict() carries extra through ─────────────────────────────────────


class TestToDictCarriesExtra:
    def test_extra_present_when_debate_stashed(self, initial_decision, summary):
        from llm import debate

        judge_data = {
            "decision": "BUY", "confidence": 70, "risk_level": "LOW",
            "up_probability": 0.65, "neutral_probability": 0.20, "down_probability": 0.15,
            "reasoning_summary": "Yes.", "reasoning_detail": "Detail here.",
        }

        with patch.object(debate, "get_client"), \
             patch.object(debate, "_call_bull", return_value="bull"), \
             patch.object(debate, "_call_bear", return_value="bear"), \
             patch.object(debate, "_call_judge", return_value=judge_data):
            out = debate.run_lightweight_debate(initial_decision, summary, "NVDA")

        d = out.to_dict()
        assert "extra" in d
        assert "debate" in d["extra"]
        assert d["extra"]["debate"]["bull_argument"] == "bull"

    def test_extra_omitted_when_empty(self):
        """Sanity: to_dict() only emits 'extra' when there's something in it."""
        bare = DecisionOutput(
            decision="WAIT",
            confidence=50.0,
            risk_level="MEDIUM",
            reasoning=[],
            probabilities={"up": 0.33, "neutral": 0.34, "down": 0.33},
            source="test",
        )
        assert "extra" not in bare.to_dict()


# ── 3. save_decision round-trips the stash through disk ────────────────────


class TestSaveDecisionRoundtrip:
    def test_debate_text_survives_save_load(self, initial_decision, summary, tmp_path, monkeypatch):
        from llm import debate
        from engine import decision_log

        log_path = tmp_path / "decision_log.json"
        monkeypatch.setattr(decision_log, "LOG_PATH", str(log_path))

        judge_data = {
            "decision": "BUY", "confidence": 75, "risk_level": "LOW",
            "up_probability": 0.7, "neutral_probability": 0.20, "down_probability": 0.10,
            "reasoning_summary": "Strong setup.",
            "reasoning_detail": "Three confirming signals plus institutional flow.",
        }

        with patch.object(debate, "get_client"), \
             patch.object(debate, "_call_bull", return_value="bull verbose case"), \
             patch.object(debate, "_call_bear", return_value="bear verbose case"), \
             patch.object(debate, "_call_judge", return_value=judge_data):
            out = debate.run_lightweight_debate(initial_decision, summary, "NVDA")

        decision_log.save_decision(out, "NVDA", mode="swing", timeframe="1D", entry_price=480.50)

        records = json.loads(log_path.read_text(encoding="utf-8"))
        assert len(records) == 1
        rec = records[0]
        assert rec["ticker"] == "NVDA"
        assert "extra" in rec
        assert rec["extra"]["debate"]["bull_argument"] == "bull verbose case"
        assert rec["extra"]["debate"]["bear_argument"] == "bear verbose case"
        assert rec["extra"]["debate"]["judge_decision"] == "BUY"
        assert rec["extra"]["debate"]["judge_confidence"] == 75


# ── 4. Phase B eligibility plumbing ────────────────────────────────────────


class TestPhaseBExtraction:
    """Once the stash is on a record, build_dspy_eval_set must pick it up."""

    def test_extractor_finds_stashed_records(self, tmp_path, initial_decision, summary, monkeypatch):
        from llm import debate
        from engine import decision_log

        log_path = tmp_path / "decision_log.json"
        monkeypatch.setattr(decision_log, "LOG_PATH", str(log_path))

        judge_data = {
            "decision": "BUY", "confidence": 70, "risk_level": "LOW",
            "up_probability": 0.65, "neutral_probability": 0.20, "down_probability": 0.15,
            "reasoning_summary": "Yes.", "reasoning_detail": "x" * 60,
        }

        with patch.object(debate, "get_client"), \
             patch.object(debate, "_call_bull", return_value="bull " * 20), \
             patch.object(debate, "_call_bear", return_value="bear " * 20), \
             patch.object(debate, "_call_judge", return_value=judge_data):
            out = debate.run_lightweight_debate(initial_decision, summary, "NVDA")

        decision_log.save_decision(out, "NVDA", mode="swing", timeframe="1D")

        # Replicate the extractor's eligibility check directly to avoid
        # hitting yfinance in this unit test. The check is a 3-line gate
        # in build_dspy_eval_set.main(), faithfully reproduced here.
        records = json.loads(log_path.read_text(encoding="utf-8"))
        eligible = [
            r for r in records
            if isinstance(r.get("extra"), dict)
            and isinstance(r["extra"].get("debate"), dict)
            and len(r["extra"]["debate"].get("bull_argument", "")) >= 50
            and len(r["extra"]["debate"].get("bear_argument", "")) >= 50
        ]
        assert len(eligible) == 1
