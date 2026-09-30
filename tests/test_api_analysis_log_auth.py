"""Public technical analysis cannot mutate the operator's decision history."""

import sys
from types import ModuleType
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import api_server
from models.decision import DecisionOutput


def _offline_analysis_modules(saved, breaking_calls):
    decision = DecisionOutput(
        decision="BUY", confidence=70, risk_level="LOW",
        reasoning=["Synthetic technical signal"],
        probabilities={"up": 0.6, "neutral": 0.2, "down": 0.2},
        source="synthetic_test",
    )
    brain = ModuleType("core.brain")
    brain.OrallexaBrain = lambda ticker: type("FakeBrain", (), {
        "run_for_mode": lambda self, **kwargs: decision,
    })()
    confidence = ModuleType("models.confidence")
    confidence.guard_decision = lambda result: result
    breaking = ModuleType("engine.breaking_signals")

    def detect_breaking(result, ticker, *, persist=True):
        breaking_calls.append((ticker, persist))
        return {"type": "synthetic_alert", "ticker": ticker}

    breaking.detect_breaking = detect_breaking
    decision_log = ModuleType("engine.decision_log")
    decision_log.save_decision = lambda **kwargs: saved.append(kwargs)
    return {
        "core.brain": brain,
        "models.confidence": confidence,
        "engine.breaking_signals": breaking,
        "engine.decision_log": decision_log,
    }


@pytest.mark.parametrize("header, expected_persist", [
    ({}, False),
    ({"X-API-Key": "wrong"}, False),
    ({"X-API-Key": "paper-test-secret"}, True),
])
def test_public_analysis_returns_result_but_only_operator_persists(
    monkeypatch, header, expected_persist,
):
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.setenv("ORALLEXA_API_KEY", "paper-test-secret")
    saved, breaking_calls = [], []
    with patch.dict(sys.modules, _offline_analysis_modules(saved, breaking_calls)):
        with TestClient(api_server.app) as client:
            response = client.post("/api/analyze", data={"ticker": "NVDA"}, headers=header)

    assert response.status_code == 200
    assert response.json()["decision"] == "BUY"
    assert response.json()["breaking_signal"]["type"] == "synthetic_alert"
    assert breaking_calls == [("NVDA", expected_persist)]
    assert len(saved) == int(expected_persist)


def test_missing_server_key_cannot_persist_even_if_lifespan_is_skipped(monkeypatch):
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.delenv("ORALLEXA_API_KEY", raising=False)
    saved, breaking_calls = [], []
    with patch.dict(sys.modules, _offline_analysis_modules(saved, breaking_calls)):
        # The normal server refuses startup without a key. Exercise direct ASGI
        # calls too, where TestClient without a context skips that lifecycle.
        response = TestClient(api_server.app).post(
            "/api/analyze", data={"ticker": "NVDA"},
            headers={"X-API-Key": "unconfigured-key"},
        )

    assert response.status_code == 200
    assert saved == []
    assert breaking_calls == [("NVDA", False)]


def test_read_only_breaking_detection_does_not_write(monkeypatch):
    from engine import breaking_signals

    previous = {"ticker": "NVDA", "decision": "SELL", "confidence": 60,
                "probabilities": {"up": 0.2, "neutral": 0.2, "down": 0.6}}
    save = Mock()
    monkeypatch.setattr(breaking_signals, "_get_last_signal", lambda ticker: previous)
    monkeypatch.setattr(breaking_signals, "_save_breaking", save)
    current = DecisionOutput(
        decision="BUY", confidence=70, risk_level="LOW", reasoning=[],
        probabilities={"up": 0.6, "neutral": 0.2, "down": 0.2}, source="test",
    )
    alert = breaking_signals.detect_breaking(current, "NVDA", persist=False)
    assert alert["type"] == "decision_flip"
    save.assert_not_called()
