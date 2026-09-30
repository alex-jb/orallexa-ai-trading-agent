"""Paid API budget admission; no real provider or broker calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
import sys

import pytest

from llm.call_logger import PRICING, logged_create
import llm.weekly_budget as weekly


MODEL = "claude-haiku-4-5-20251001"
MESSAGES = [{"role": "user", "content": "hi"}]


@pytest.fixture(autouse=True)
def clean_budget(monkeypatch):
    monkeypatch.setattr(weekly, "_active_budget", None)
    yield
    monkeypatch.setattr(weekly, "_active_budget", None)


def test_concurrent_reservations_share_single_week_cap(tmp_path):
    weekly.activate_weekly_budget("0.0015", tmp_path / "budget.sqlite3")

    def attempt(_):
        try:
            return weekly.reserve_if_active(MODEL, 100, MESSAGES, PRICING)
        except weekly.WeeklyBudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=12) as pool:
        reservations = list(pool.map(attempt, range(24)))
    assert len([r for r in reservations if r]) == 1


def test_logged_call_settles_usage_and_preserves_failed_reservation(tmp_path, monkeypatch):
    weekly.activate_weekly_budget("0.002", tmp_path / "budget.sqlite3")
    monkeypatch.setattr("llm.call_logger._append_record", lambda _: None)
    monkeypatch.setattr("llm.call_logger._send_to_posthog", lambda _: None)
    monkeypatch.setattr("llm.call_logger._send_to_langfuse", lambda _: None)

    ok = SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=10))
    class FakeClient:
        def __init__(self):
            self.calls = 0
            self.messages = self

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("provider failure after request")
            return ok

    fake = FakeClient()
    _, record = logged_create(fake, request_type="test", model=MODEL, max_tokens=100, messages=MESSAGES)
    assert record.estimated_cost_usd > 0
    with pytest.raises(RuntimeError, match="provider failure"):
        logged_create(fake, request_type="test", model=MODEL, max_tokens=100, messages=MESSAGES)
    with pytest.raises(weekly.WeeklyBudgetExceeded):
        logged_create(fake, request_type="test", model=MODEL, max_tokens=100, messages=MESSAGES)
    assert fake.calls == 2


def test_ledger_failure_after_billed_response_still_logs_call(monkeypatch):
    import llm.call_logger as call_logger

    records = []
    monkeypatch.setattr(weekly, "reserve_if_active", lambda *args: "reserved")
    def fail_settle(*_):
        raise OSError("ledger down")
    monkeypatch.setattr(weekly, "settle_if_active", fail_settle)
    monkeypatch.setattr(call_logger, "_append_record", records.append)
    monkeypatch.setattr(call_logger, "_send_to_posthog", lambda _: None)
    monkeypatch.setattr(call_logger, "_send_to_langfuse", lambda _: None)
    fake = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: SimpleNamespace(
        usage=SimpleNamespace(input_tokens=10, output_tokens=10))))

    with pytest.raises(OSError, match="ledger down"):
        logged_create(fake, request_type="test", model=MODEL, max_tokens=100, messages=MESSAGES)
    assert len(records) == 1
    assert records[0].estimated_cost_usd > 0


def test_unknown_model_bad_cap_and_unavailable_database_fail_closed(tmp_path):
    with pytest.raises(ValueError):
        weekly.WeeklyLLMBudget("NaN", tmp_path / "bad.sqlite3")
    with pytest.raises(ValueError):
        weekly.WeeklyLLMBudget("-1", tmp_path / "bad.sqlite3")
    weekly.activate_weekly_budget("1", tmp_path / "budget.sqlite3")
    with pytest.raises(weekly.WeeklyBudgetExceeded, match="Unknown"):
        weekly.reserve_if_active("unpriced-foo", 100, MESSAGES, PRICING)
    broken = weekly.WeeklyLLMBudget("1", tmp_path / "broken.sqlite3")
    broken.path.unlink()
    with pytest.raises(OSError):
        broken.reserve(MODEL, 100, MESSAGES, PRICING)


def test_utc_monday_rollover_excludes_previous_week(tmp_path):
    budget = weekly.WeeklyLLMBudget("0.0015", tmp_path / "budget.sqlite3")
    assert budget.week_start(datetime(2026, 9, 27, 23, 59, tzinfo=timezone.utc)) == "2026-09-21"
    assert budget.week_start(datetime(2026, 9, 28, 0, tzinfo=timezone.utc)) == "2026-09-28"
    with budget._connect() as conn:
        conn.execute(
            "INSERT INTO llm_reservations VALUES (?, ?, ?, ?, ?, NULL)",
            ("old", "2026-09-21", 1_500, MODEL, "2026-09-21T00:00:00Z"),
        )
    assert budget.reserve(MODEL, 100, MESSAGES, PRICING)


def test_authenticated_api_configures_budget_and_demo_uses_mocks(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import api_server

    monkeypatch.setenv("ORALLEXA_WEEKLY_LLM_BUDGET_DB", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("ORALLEXA_WEEKLY_LLM_BUDGET_USD", "0")
    monkeypatch.setenv("ORALLEXA_API_KEY", "test-secret")
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    with TestClient(api_server.app) as client:
        response = client.post("/api/deep-analysis", headers={"X-API-Key": "bad"})
        assert response.status_code == 401
        assert weekly._active_budget is None
        with patch.dict(sys.modules, {"engine.scenario_sim": SimpleNamespace(run_scenario=lambda **_: {"ok": True})}):
            response = client.post(
                "/api/scenario", data={"scenario": "hypothetical"},
                headers={"X-API-Key": "test-secret"},
            )
        assert response.status_code == 200
        assert weekly._active_budget is not None
        with pytest.raises(weekly.WeeklyBudgetExceeded):
            weekly.reserve_if_active(MODEL, 100, MESSAGES, PRICING)

    monkeypatch.setattr(api_server, "DEMO_MODE", True)
    monkeypatch.setattr(weekly, "_active_budget", None)
    with TestClient(api_server.app) as client:
        assert client.post("/api/deep-analysis", data={"ticker": "NVDA"}).status_code == 200
    assert weekly._active_budget is None


def test_authenticated_scenario_cannot_call_model_after_budget_exhausted(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import api_server

    monkeypatch.setenv("ORALLEXA_WEEKLY_LLM_BUDGET_DB", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("ORALLEXA_WEEKLY_LLM_BUDGET_USD", "0")
    monkeypatch.setenv("ORALLEXA_API_KEY", "test-secret")
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    class FakeClient:
        def __init__(self):
            self.calls = 0
            self.messages = self

        def create(self, **kwargs):
            self.calls += 1
            raise AssertionError("provider was reached")

    fake = FakeClient()

    def model_route(**_):
        logged_create(fake, request_type="scenario", model=MODEL, max_tokens=100, messages=MESSAGES)

    with patch.dict(sys.modules, {"engine.scenario_sim": SimpleNamespace(run_scenario=model_route)}):
        with TestClient(api_server.app) as client:
            response = client.post(
                "/api/scenario", data={"scenario": "hypothetical"},
                headers={"X-API-Key": "test-secret"},
            )
    assert response.status_code == 500  # current route catches all generation errors
    assert "Weekly API LLM budget exhausted" in response.json()["detail"]
    assert fake.calls == 0


def test_budget_store_failure_does_not_block_paper_broker_auth(tmp_path, monkeypatch):
    import api_server
    from fastapi import HTTPException

    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.setenv("ORALLEXA_API_KEY", "test-secret")
    path = tmp_path / "api.sqlite3"
    monkeypatch.setenv("ORALLEXA_WEEKLY_LLM_BUDGET_DB", str(path))
    api_server._require_paid_api_key("test-secret")
    path.unlink()
    # Broker close routes still authenticate, regardless of the LLM ledger.
    assert api_server._require_api_key("test-secret") is None
    with pytest.raises(HTTPException) as exc:
        api_server._require_paid_api_key("test-secret")
    assert exc.value.status_code == 503
