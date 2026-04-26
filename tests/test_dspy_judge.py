"""
tests/test_dspy_judge.py
──────────────────────────────────────────────────────────────────
Tests for llm/dspy_judge.py — lazy-import guard + judge_dspy/compare
behavior with a stubbed dspy module.

dspy is NOT a project dependency. These tests inject a fake dspy
module via sys.modules so the code path can be exercised without
installing dspy-ai. The single test that proves the install-hint
error is also here.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


# ── Fake dspy module factory ───────────────────────────────────────────────


def _build_fake_dspy(prediction_fields: dict):
    """
    Build a minimal sys.modules['dspy'] stub that satisfies what
    llm/dspy_judge.py imports. Returns the module + the recorded
    Predict().__call__ result for assertions.
    """
    fake = types.ModuleType("dspy")

    # `dspy.Signature` — class with InputField/OutputField as class vars
    class FakeSignature:
        # Subclasses are defined inside _ensure_dspy via class body.
        # The body runs InputField/OutputField as class-attribute values
        # which our fake just resolves to None placeholders.
        pass

    fake.Signature = FakeSignature

    # `dspy.InputField()` / `dspy.OutputField()` return placeholders.
    # The real dspy uses descriptors; for our purposes they just need
    # to exist as functions so the class body doesn't crash.
    def _field(*_, **__):
        return None
    fake.InputField = _field
    fake.OutputField = _field

    # `dspy.LM(...)` — store args, return a sentinel
    class FakeLM:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
    fake.LM = FakeLM

    # `dspy.configure(lm=...)` — record the call
    fake._configured_with = None
    def configure(lm=None, **_):
        fake._configured_with = lm
    fake.configure = configure

    # `dspy.Predict(SignatureCls)` returns a callable that produces a
    # Prediction-like object with `prediction_fields` as attributes.
    class FakePrediction:
        def __init__(self, fields: dict):
            for k, v in fields.items():
                setattr(self, k, v)

    class FakePredict:
        def __init__(self, sig_cls):
            self.sig_cls = sig_cls

        def __call__(self, **kwargs):
            return FakePrediction(prediction_fields)

    fake.Predict = FakePredict
    return fake


def _install_fake_dspy(monkeypatch, prediction_fields: dict) -> types.ModuleType:
    fake = _build_fake_dspy(prediction_fields)
    monkeypatch.setitem(sys.modules, "dspy", fake)
    # Also reset the module-level cache in dspy_judge so each test gets
    # a clean configure path.
    import llm.dspy_judge as dj
    dj._dspy_configured = False
    dj._predict_cls = None
    return fake


# ── Lazy import guard ──────────────────────────────────────────────────────


class TestLazyImport:
    def test_missing_dspy_raises_clear_error(self, monkeypatch):
        """When dspy isn't installed, error message must point at install."""
        # Force the import to fail
        monkeypatch.setitem(sys.modules, "dspy", None)
        import llm.dspy_judge as dj
        dj._dspy_configured = False
        dj._predict_cls = None
        with pytest.raises(RuntimeError, match="dspy-ai not installed"):
            dj._ensure_dspy()


# ── _ensure_dspy ───────────────────────────────────────────────────────────


class TestEnsureDspy:
    def test_configures_lm_once(self, monkeypatch):
        fake = _install_fake_dspy(monkeypatch, {
            "decision": "BUY", "confidence": 75,
            "risk_level": "LOW", "reasoning_detail": "Strong setup.",
        })
        from llm.dspy_judge import _ensure_dspy
        p1 = _ensure_dspy()
        p2 = _ensure_dspy()
        assert p1 is p2  # cached
        assert fake._configured_with is not None  # configured exactly once

    def test_lm_route_uses_anthropic_prefix(self, monkeypatch):
        fake = _install_fake_dspy(monkeypatch, {
            "decision": "WAIT", "confidence": 50,
            "risk_level": "MEDIUM", "reasoning_detail": "x",
        })
        from llm.dspy_judge import _ensure_dspy
        _ensure_dspy()
        lm = fake._configured_with
        assert lm.args and lm.args[0].startswith("anthropic/")


# ── judge_dspy ─────────────────────────────────────────────────────────────


class TestJudgeDspy:
    def test_happy_path_returns_normalized_dict(self, monkeypatch):
        _install_fake_dspy(monkeypatch, {
            "decision": "buy",     # lowercase — should be normalized
            "confidence": "82",     # string — should coerce
            "risk_level": "low",
            "reasoning_detail": "Bull case clearly stronger across all factors.",
        })
        from llm.dspy_judge import judge_dspy
        out = judge_dspy("bull text", "bear text", ticker="NVDA")
        assert out["decision"] == "BUY"
        assert out["confidence"] == 82
        assert out["risk_level"] == "LOW"
        assert out["source"] == "dspy"

    def test_invalid_decision_falls_back_to_wait(self, monkeypatch):
        _install_fake_dspy(monkeypatch, {
            "decision": "MAYBE", "confidence": 60,
            "risk_level": "MEDIUM", "reasoning_detail": "x",
        })
        from llm.dspy_judge import judge_dspy
        out = judge_dspy("bull", "bear")
        assert out["decision"] == "WAIT"

    def test_confidence_clamped_to_0_100(self, monkeypatch):
        _install_fake_dspy(monkeypatch, {
            "decision": "BUY", "confidence": 999,
            "risk_level": "LOW", "reasoning_detail": "",
        })
        from llm.dspy_judge import judge_dspy
        out = judge_dspy("bull", "bear")
        assert out["confidence"] == 100

    def test_garbage_confidence_defaults_to_50(self, monkeypatch):
        _install_fake_dspy(monkeypatch, {
            "decision": "WAIT", "confidence": "n/a",
            "risk_level": "MEDIUM", "reasoning_detail": "",
        })
        from llm.dspy_judge import judge_dspy
        out = judge_dspy("bull", "bear")
        assert out["confidence"] == 50

    def test_invalid_risk_level_normalized(self, monkeypatch):
        _install_fake_dspy(monkeypatch, {
            "decision": "BUY", "confidence": 70,
            "risk_level": "EXTREME", "reasoning_detail": "x",
        })
        from llm.dspy_judge import judge_dspy
        out = judge_dspy("bull", "bear")
        assert out["risk_level"] == "MEDIUM"

    def test_reasoning_truncated_at_600(self, monkeypatch):
        _install_fake_dspy(monkeypatch, {
            "decision": "BUY", "confidence": 70,
            "risk_level": "MEDIUM",
            "reasoning_detail": "x" * 1000,
        })
        from llm.dspy_judge import judge_dspy
        out = judge_dspy("bull", "bear")
        assert len(out["reasoning_detail"]) == 600

    def test_runtime_error_propagates_for_install_hint(self, monkeypatch):
        """When dspy isn't installed, judge_dspy should raise so users see hint."""
        monkeypatch.setitem(sys.modules, "dspy", None)
        import llm.dspy_judge as dj
        dj._dspy_configured = False
        dj._predict_cls = None
        with pytest.raises(RuntimeError, match="dspy-ai not installed"):
            dj.judge_dspy("bull", "bear")


# ── compare_judges ─────────────────────────────────────────────────────────


class TestCompareJudges:
    def test_agreement_path(self, monkeypatch):
        _install_fake_dspy(monkeypatch, {
            "decision": "BUY", "confidence": 80,
            "risk_level": "LOW", "reasoning_detail": "x",
        })
        # Stub out the hand-tuned _call_judge to return matching BUY
        from models.decision import DecisionOutput
        hand_decision = DecisionOutput(
            decision="BUY",
            confidence=75.0,
            risk_level="LOW",
            reasoning=[],
            probabilities={"up": 0.7, "neutral": 0.2, "down": 0.1},
            source="hand",
            signal_strength=70.0,
        )
        from llm.dspy_judge import compare_judges
        with patch("llm.debate._call_judge", return_value=hand_decision), \
             patch("llm.claude_client.get_client", return_value=MagicMock()):
            out = compare_judges("bull", "bear", ticker="NVDA")
        assert out["agree"] is True
        assert out["hand_tuned"]["decision"] == "BUY"
        assert out["dspy"]["decision"] == "BUY"
        assert out["conf_delta"] == 80 - 75

    def test_disagreement_path(self, monkeypatch):
        _install_fake_dspy(monkeypatch, {
            "decision": "SELL", "confidence": 70,
            "risk_level": "HIGH", "reasoning_detail": "x",
        })
        from models.decision import DecisionOutput
        hand_decision = DecisionOutput(
            decision="BUY", confidence=75.0, risk_level="LOW",
            reasoning=[], probabilities={"up": 0.7, "neutral": 0.2, "down": 0.1},
            source="hand", signal_strength=70.0,
        )
        from llm.dspy_judge import compare_judges
        with patch("llm.debate._call_judge", return_value=hand_decision), \
             patch("llm.claude_client.get_client", return_value=MagicMock()):
            out = compare_judges("bull", "bear")
        assert out["agree"] is False

    def test_hand_tuned_failure_still_reports_dspy(self, monkeypatch):
        _install_fake_dspy(monkeypatch, {
            "decision": "BUY", "confidence": 80,
            "risk_level": "LOW", "reasoning_detail": "x",
        })
        from llm.dspy_judge import compare_judges
        with patch("llm.debate._call_judge", side_effect=RuntimeError("hand failed")):
            out = compare_judges("bull", "bear")
        assert out["hand_tuned"] is None
        assert out["dspy"]["decision"] == "BUY"
        assert out["agree"] is False
        assert out["conf_delta"] is None
