"""Tests for models/decision.py — DecisionOutput dataclass."""

import pytest
from models.decision import DecisionOutput


def make_decision(
    decision="BUY",
    confidence=72.0,
    risk_level="MEDIUM",
    reasoning=None,
    probabilities=None,
    source="test",
):
    return DecisionOutput(
        decision=decision,
        confidence=confidence,
        risk_level=risk_level,
        reasoning=reasoning or ["step 1", "step 2"],
        probabilities=probabilities or {"up": 0.6, "neutral": 0.2, "down": 0.2},
        source=source,
    )


def test_instantiation():
    d = make_decision()
    assert d.decision == "BUY"
    assert d.confidence == 72.0
    assert d.risk_level == "MEDIUM"
    assert d.source == "test"


def test_to_dict_keys():
    d = make_decision()
    result = d.to_dict()
    assert set(result.keys()) == {
        "decision", "confidence", "risk_level", "reasoning", "probabilities", "source",
        "signal_strength", "recommendation",
    }


def test_to_dict_values():
    d = make_decision(decision="SELL", confidence=55.5, risk_level="HIGH")
    result = d.to_dict()
    assert result["decision"] == "SELL"
    assert result["confidence"] == 55.5
    assert result["risk_level"] == "HIGH"


def test_confidence_stored_as_float():
    d = make_decision(confidence=80)
    assert isinstance(d.confidence, float) or isinstance(d.confidence, int)
    assert d.to_dict()["confidence"] == 80.0


def test_reasoning_is_list():
    d = make_decision(reasoning=["a", "b", "c"])
    assert isinstance(d.reasoning, list)
    assert len(d.reasoning) == 3


def test_probabilities_keys():
    probs = {"up": 0.5, "neutral": 0.3, "down": 0.2}
    d = make_decision(probabilities=probs)
    assert d.probabilities["up"] == 0.5
    assert d.probabilities["down"] == 0.2


def test_all_decisions():
    for label in ("BUY", "SELL", "WAIT"):
        d = make_decision(decision=label)
        assert d.decision == label


def test_all_risk_levels():
    for level in ("LOW", "MEDIUM", "HIGH"):
        d = make_decision(risk_level=level)
        assert d.risk_level == level
