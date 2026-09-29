"""Protected API routes fail closed, including when startup is bypassed."""

from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import api_server


ORDER_ROUTES = [
    ("GET", "/api/alpaca/account"),
    ("GET", "/api/alpaca/positions"),
    ("GET", "/api/alpaca/orders"),
    ("POST", "/api/alpaca/execute"),
    ("POST", "/api/alpaca/close/NVDA"),
    ("POST", "/api/alpaca/close-all"),
]


def test_non_demo_refuses_to_start_without_key(monkeypatch):
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.delenv("ORALLEXA_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ORALLEXA_API_KEY is required"):
        with TestClient(api_server.app):
            pass


@pytest.mark.parametrize("method,path", ORDER_ROUTES)
def test_order_routes_fail_closed_without_configured_key(monkeypatch, method, path):
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.delenv("ORALLEXA_API_KEY", raising=False)
    # TestClient without a context manager does not run startup.
    response = TestClient(api_server.app).request(method, path)
    assert response.status_code == 503


@pytest.mark.parametrize("method,path", ORDER_ROUTES)
def test_order_routes_reject_missing_and_wrong_key(monkeypatch, method, path):
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.setenv("ORALLEXA_API_KEY", "paper-test-secret")
    with TestClient(api_server.app) as client:
        assert client.request(method, path).status_code == 401
        assert client.request(method, path, headers={"X-API-Key": "wrong"}).status_code == 401


@pytest.mark.parametrize("method,path", ORDER_ROUTES)
@pytest.mark.parametrize("configured", [False, True])
def test_demo_never_reaches_broker(monkeypatch, method, path, configured):
    monkeypatch.setattr(api_server, "DEMO_MODE", True)
    if configured:
        monkeypatch.setenv("ORALLEXA_API_KEY", "paper-test-secret")
    else:
        monkeypatch.delenv("ORALLEXA_API_KEY", raising=False)
    with patch("bot.alpaca_executor.AlpacaExecutor") as executor:
        with TestClient(api_server.app) as client:
            response = client.request(method, path, headers={"X-API-Key": "paper-test-secret"})
        assert response.status_code == 403
        executor.assert_not_called()


def test_valid_key_reaches_paper_account(monkeypatch):
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.setenv("ORALLEXA_API_KEY", "paper-test-secret")
    with patch("bot.alpaca_executor.AlpacaExecutor") as executor:
        executor.return_value.connected = True
        executor.return_value.get_account.return_value = {"status": "paper"}
        with TestClient(api_server.app) as client:
            response = client.get("/api/alpaca/account", headers={"X-API-Key": "paper-test-secret"})
    assert response.status_code == 200
    assert response.json() == {"status": "paper"}
