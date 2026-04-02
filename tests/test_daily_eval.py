"""Tests for eval/daily_eval.py — daily evaluation runner and drift tracking."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.daily_eval import run_daily_eval, show_drift_history, main, _HISTORY_DIR


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_harness_result():
    """Create a mock HarnessResult for testing."""
    mock_wf = MagicMock()
    mock_wf.avg_oos_sharpe = 0.5
    mock_wf.pct_positive_sharpe = 0.6
    mock_wf.avg_information_ratio = 0.3

    mock_eval = MagicMock()
    mock_eval.strategy_name = "double_ma"
    mock_eval.ticker = "NVDA"
    mock_eval.walk_forward = mock_wf
    mock_eval.overall_pass = True

    result = MagicMock()
    result.evaluations = [mock_eval]
    result.total_evaluated = 1
    result.total_passed = 1
    return result


@pytest.fixture
def tmp_history(tmp_path, monkeypatch):
    """Redirect history directory to tmp."""
    import eval.daily_eval as de
    monkeypatch.setattr(de, "_HISTORY_DIR", tmp_path)
    return tmp_path


# ═══════════════════════════════════════════════════════════════════════════
# run_daily_eval TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestRunDailyEval:
    @patch("eval.report_generator.generate_report")
    @patch("eval.report_generator._result_to_dict")
    @patch("eval.harness.EvaluationHarness")
    def test_creates_snapshot_file(self, MockHarness, mock_to_dict, mock_report, mock_harness_result, tmp_history):
        instance = MockHarness.return_value
        instance.run.return_value = mock_harness_result
        mock_to_dict.return_value = {"test": True}

        snapshot = run_daily_eval(tickers=["NVDA"], seed=42)

        assert "run_date" in snapshot
        assert "strategy_summary" in snapshot
        # Check snapshot file was created
        snapshot_files = list(tmp_history.glob("eval_*.json"))
        assert len(snapshot_files) == 1

    @patch("eval.report_generator.generate_report")
    @patch("eval.report_generator._result_to_dict")
    @patch("eval.harness.EvaluationHarness")
    def test_appends_to_drift_log(self, MockHarness, mock_to_dict, mock_report, mock_harness_result, tmp_history):
        instance = MockHarness.return_value
        instance.run.return_value = mock_harness_result
        mock_to_dict.return_value = {"test": True}

        run_daily_eval(tickers=["NVDA"], seed=42)

        drift_path = tmp_history / "drift.jsonl"
        assert drift_path.exists()
        with open(drift_path) as f:
            lines = f.readlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert "date" in entry
        assert "total_evaluated" in entry
        assert "top_sharpe" in entry
        assert "avg_sharpe" in entry

    @patch("eval.report_generator.generate_report")
    @patch("eval.report_generator._result_to_dict")
    @patch("eval.harness.EvaluationHarness")
    def test_strategy_summary_structure(self, MockHarness, mock_to_dict, mock_report, mock_harness_result, tmp_history):
        instance = MockHarness.return_value
        instance.run.return_value = mock_harness_result
        mock_to_dict.return_value = {}

        snapshot = run_daily_eval(tickers=["NVDA"], seed=42)

        summary = snapshot["strategy_summary"]
        assert "double_ma_NVDA" in summary
        entry = summary["double_ma_NVDA"]
        assert entry["strategy"] == "double_ma"
        assert entry["ticker"] == "NVDA"
        assert "oos_sharpe" in entry
        assert "passed" in entry


# ═══════════════════════════════════════════════════════════════════════════
# show_drift_history TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestShowDriftHistory:
    def test_no_history_prints_message(self, tmp_history, capsys):
        show_drift_history()
        captured = capsys.readouterr()
        assert "No drift history" in captured.out

    def test_with_history_prints_table(self, tmp_history, capsys):
        drift_path = tmp_history / "drift.jsonl"
        entry = {"date": "2026-04-02", "total_evaluated": 70, "total_passed": 30, "top_sharpe": 1.5, "avg_sharpe": 0.4}
        drift_path.write_text(json.dumps(entry) + "\n")

        show_drift_history()
        captured = capsys.readouterr()
        assert "2026-04-02" in captured.out
        assert "Sharpe Drift" in captured.out


# ═══════════════════════════════════════════════════════════════════════════
# CLI TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestCLI:
    def test_history_flag(self, tmp_history, monkeypatch):
        monkeypatch.setattr("sys.argv", ["daily_eval.py", "--history"])
        # Should not raise
        main()

    @patch("eval.daily_eval.run_daily_eval")
    def test_tickers_parsing(self, mock_run, monkeypatch):
        mock_run.return_value = {}
        monkeypatch.setattr("sys.argv", ["daily_eval.py", "--tickers", "NVDA,AAPL"])
        main()
        args = mock_run.call_args
        assert args[0][0] == ["NVDA", "AAPL"] or args[1].get("tickers") == ["NVDA", "AAPL"]

    @patch("eval.daily_eval.run_daily_eval")
    def test_seed_passthrough(self, mock_run, monkeypatch):
        mock_run.return_value = {}
        monkeypatch.setattr("sys.argv", ["daily_eval.py", "--seed", "123"])
        main()
        args = mock_run.call_args
        # seed should be 123
        assert 123 in args[0] or args[1].get("seed") == 123
