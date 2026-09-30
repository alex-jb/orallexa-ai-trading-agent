"""Offline safety checks for the legacy daily pilot entry point."""
import json
import plistlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from scripts import run_daily_pilot as pilot


def _no_external_calls(monkeypatch, *, failure=False, log_failure=False):
    calls = []

    class FakeBrain:
        def __init__(self, ticker):
            calls.append(("brain", ticker))

        def run_prediction(self, **kwargs):
            assert kwargs == {"use_claude": False, "mode": "swing"}
            calls.append(("prediction", kwargs))
            reasoning = ["Prediction failed: no bars"] if failure else ["technical only"]
            return SimpleNamespace(
                decision="WAIT", confidence=42, risk_level="HIGH",
                reasoning=reasoning,
            )

    class ForbiddenBroker:
        def __init__(self, *args, **kwargs):
            pytest.fail("Legacy pilot must not instantiate a paper broker")

    def forbidden_llm(*args, **kwargs):
        pytest.fail("Legacy pilot must not call a paid model")

    def save_decision(**kwargs):
        if log_failure:
            return False
        assert kwargs["notes"] == "run_daily_pilot:technical_only:no_debate"
        calls.append(("log", kwargs["ticker"]))

    monkeypatch.setitem(sys.modules, "core.brain", ModuleType("core.brain"))
    sys.modules["core.brain"].OrallexaBrain = FakeBrain
    monkeypatch.setitem(sys.modules, "engine.decision_log", ModuleType("engine.decision_log"))
    sys.modules["engine.decision_log"].save_decision = save_decision
    monkeypatch.setitem(sys.modules, "bot.alpaca_executor", ModuleType("bot.alpaca_executor"))
    sys.modules["bot.alpaca_executor"].AlpacaExecutor = ForbiddenBroker
    monkeypatch.setitem(sys.modules, "llm.ui_analysis", ModuleType("llm.ui_analysis"))
    sys.modules["llm.ui_analysis"].prediction_decision_report = forbidden_llm
    return calls


@pytest.mark.parametrize("flags", [[], ["--dry-run"]])
def test_default_and_legacy_dry_run_are_model_free_order_free(monkeypatch, tmp_path, flags):
    calls = _no_external_calls(monkeypatch)
    path = tmp_path / "pilot.jsonl"

    assert pilot.main([*flags, "--out", str(path)]) == 0
    row = json.loads(path.read_text().strip())
    assert row["mode"] == "technical_only_no_debate"
    assert row["decisions_logged"] == 7
    assert (row["debate_rows"], row["orders_submitted"], row["llm_calls"], row["llm_cost_usd"]) == (0, 0, 0, 0)
    assert len([call for call in calls if call[0] == "log"]) == 7


@pytest.mark.parametrize("flags", [
    ["--execute-paper"], ["--use-claude"], ["--confidence", "70"],
    ["--tickers", ""], ["--tickers", "NVDA,NVDA"],
    ["--tickers", "A,B,C,D,E,F,G,H"], ["--tickers", "AAPL;BAD"],
])
def test_unsafe_or_invalid_cli_is_rejected_before_data_fetch(monkeypatch, tmp_path, flags):
    calls = _no_external_calls(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        pilot.main([*flags, "--out", str(tmp_path / "pilot.jsonl")])
    assert exc.value.code == 2
    assert calls == []
    assert not list(tmp_path.glob("*.jsonl"))


@pytest.mark.parametrize("failure,log_failure,expected", [
    (True, False, "predict_failed"), (False, True, "log_failed"),
])
def test_failed_prediction_or_write_is_not_reported_as_logged(
    monkeypatch, tmp_path, failure, log_failure, expected
):
    _no_external_calls(monkeypatch, failure=failure, log_failure=log_failure)
    path = tmp_path / "pilot.jsonl"
    assert pilot.main(["--tickers", "AAPL", "--out", str(path)]) == 2
    row = json.loads(path.read_text().strip())
    assert row["results"][0]["status"] == expected
    assert row["decisions_logged"] == row["orders_submitted"] == row["debate_rows"] == 0


def test_launchd_job_does_not_load_keys_or_enable_orders():
    path = Path(pilot.__file__).parent / "launchd" / "com.alexji.orallexa-paper-daily.plist"
    job = plistlib.loads(path.read_bytes())
    command = job["ProgramArguments"][-1]
    assert "--dry-run" in command
    assert "--execute-paper" not in command
    assert "--use-claude" not in command
    assert "source .env" not in command
    assert "pilot.jsonl" in command


def test_decision_log_reports_failed_write(monkeypatch, tmp_path):
    from engine import decision_log

    path = tmp_path / "a_directory"
    path.mkdir()
    monkeypatch.setattr(decision_log, "LOG_PATH", str(path))
    decision = SimpleNamespace(to_dict=lambda: {"decision": "WAIT"})
    assert decision_log.save_decision(decision, "AAPL", "swing", "1D") is False
