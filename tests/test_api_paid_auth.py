"""Public demo never reaches paid LLMs; real paid routes require API auth."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

# The protected API refuses a keyless non-demo import before ASGI startup.
with patch.dict(os.environ, {"ORALLEXA_API_KEY": "test-secret"}):
    import api_server


PAID_ROUTES = [
    ("POST", "/api/deep-analysis", {}),
    ("POST", "/api/deep-analysis-stream", {}),
    ("POST", "/api/chart-analysis", {"files": {"file": ("chart.png", b"fake", "image/png")}}),
    ("GET", "/api/daily-intel", {}),
    ("GET", "/api/daily-intel?force=true", {}),
    ("POST", "/api/daily-intel/refresh", {}),
    ("POST", "/api/scenario", {"data": {"scenario": "hypothetical"}}),
    ("POST", "/api/evolve-strategies", {}),
    ("POST", "/api/analyze", {"data": {"use_claude": "true"}}),
    ("POST", "/api/analyze", {"data": {"use_debate": "true"}}),
    ("GET", "/api/regime/NVDA?use_llm=true", {}),
]


@pytest.mark.parametrize("method,path,kwargs", PAID_ROUTES)
def test_paid_routes_reject_anonymous_and_wrong_key(monkeypatch, method, path, kwargs):
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.setenv("ORALLEXA_API_KEY", "test-secret")
    with TestClient(api_server.app) as client:
        assert client.request(method, path, **kwargs).status_code == 401
        assert client.request(method, path, headers={"X-API-Key": "wrong"}, **kwargs).status_code == 401


@pytest.mark.parametrize("path,kwargs", [
    ("/api/scenario", {"data": {"scenario": "hypothetical"}}),
    ("/api/evolve-strategies", {}),
])
def test_unmocked_demo_routes_never_call_model(monkeypatch, path, kwargs):
    monkeypatch.setattr(api_server, "DEMO_MODE", True)
    monkeypatch.delenv("ORALLEXA_API_KEY", raising=False)
    model_call = Mock()
    # The route dependency must reject before any heavyweight import or call.
    with patch.dict(sys.modules, {"engine.scenario_sim": SimpleNamespace(run_scenario=model_call)}):
        with TestClient(api_server.app) as client:
            response = client.post(path, **kwargs)
    assert response.status_code == 403
    model_call.assert_not_called()


def test_demo_analysis_still_returns_mock_without_key(monkeypatch):
    monkeypatch.setattr(api_server, "DEMO_MODE", True)
    monkeypatch.delenv("ORALLEXA_API_KEY", raising=False)
    with TestClient(api_server.app) as client:
        response = client.post("/api/deep-analysis", data={"ticker": "NVDA"})
        optional = client.post("/api/analyze", data={"ticker": "NVDA", "use_debate": "true"})
    assert response.status_code == 200
    assert optional.status_code == 200
    assert optional.json()["source"].startswith("demo_")


@pytest.mark.parametrize("method,path,kwargs", [
    ("POST", "/api/chart-analysis", {"files": {"file": ("chart.png", b"fake", "image/png")}}),
    ("GET", "/api/daily-intel", {}),
    ("GET", "/api/regime/NVDA?use_llm=true", {}),
])
def test_other_mocked_demo_routes_still_work_without_key(monkeypatch, method, path, kwargs):
    monkeypatch.setattr(api_server, "DEMO_MODE", True)
    monkeypatch.delenv("ORALLEXA_API_KEY", raising=False)
    with TestClient(api_server.app) as client:
        response = client.request(method, path, **kwargs)
    assert response.status_code == 200


def test_valid_key_reaches_mocked_scenario(monkeypatch):
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.setenv("ORALLEXA_API_KEY", "test-secret")
    model_call = Mock(return_value={"scenario": "hypothetical", "impacts": []})
    with patch.dict(sys.modules, {"engine.scenario_sim": SimpleNamespace(run_scenario=model_call)}):
        with TestClient(api_server.app) as client:
            response = client.post(
                "/api/scenario", data={"scenario": "hypothetical"},
                headers={"X-API-Key": "test-secret"},
            )
    assert response.status_code == 200
    assert response.json()["scenario"] == "hypothetical"
    model_call.assert_called_once()


def test_lifespan_bypass_without_key_still_rejects_paid_call(monkeypatch):
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.delenv("ORALLEXA_API_KEY", raising=False)
    assert TestClient(api_server.app).post(
        "/api/scenario", data={"scenario": "hypothetical"}
    ).status_code == 503
