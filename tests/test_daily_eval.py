"""Tests for eval/daily_eval.py — daily evaluation runner and drift tracking."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_history(tmp_path, monkeypatch):
    """Redirect history directory to tmp."""
    import eval.daily_eval as de
    monkeypatch.setattr(de, "_HISTORY_DIR", tmp_path)
    return tmp_path


# ═══════════════════════════════════════════════════════════════════════════
# show_drift_history TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestShowDriftHistory:
    def test_no_history_prints_message(self, tmp_history, capsys):
        from eval.daily_eval import show_drift_history
        show_drift_history()
        captured = capsys.readouterr()
        assert "No drift history" in captured.out

    def test_with_history_prints_table(self, tmp_history, capsys):
        from eval.daily_eval import show_drift_history
        drift_path = tmp_history / "drift.jsonl"
        entry = {"date": "2026-04-02", "total_evaluated": 70, "total_passed": 30, "top_sharpe": 1.5, "avg_sharpe": 0.4}
        drift_path.write_text(json.dumps(entry) + "\n")

        show_drift_history()
        captured = capsys.readouterr()
        assert "2026-04-02" in captured.out
        assert "Sharpe Drift" in captured.out

    def test_multiple_entries(self, tmp_history, capsys):
        from eval.daily_eval import show_drift_history
        drift_path = tmp_history / "drift.jsonl"
        entries = [
            {"date": "2026-04-01", "total_evaluated": 70, "total_passed": 28, "top_sharpe": 1.2, "avg_sharpe": 0.3},
            {"date": "2026-04-02", "total_evaluated": 70, "total_passed": 30, "top_sharpe": 1.5, "avg_sharpe": 0.4},
        ]
        drift_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        show_drift_history()
        captured = capsys.readouterr()
        assert "2026-04-01" in captured.out
        assert "2026-04-02" in captured.out


# ═══════════════════════════════════════════════════════════════════════════
# CLI TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestCLI:
    def test_history_flag(self, tmp_history, monkeypatch):
        from eval.daily_eval import main
        monkeypatch.setattr("sys.argv", ["daily_eval.py", "--history"])
        main()

    @patch("eval.daily_eval.run_daily_eval")
    def test_tickers_parsing(self, mock_run, monkeypatch):
        from eval.daily_eval import main
        mock_run.return_value = {}
        monkeypatch.setattr("sys.argv", ["daily_eval.py", "--tickers", "NVDA,AAPL"])
        main()
        tickers_arg = mock_run.call_args[0][0] if mock_run.call_args[0] else mock_run.call_args[1].get("tickers")
        assert tickers_arg == ["NVDA", "AAPL"]

    @patch("eval.daily_eval.run_daily_eval")
    def test_seed_passthrough(self, mock_run, monkeypatch):
        from eval.daily_eval import main
        mock_run.return_value = {}
        monkeypatch.setattr("sys.argv", ["daily_eval.py", "--seed", "123"])
        main()
        # Check seed=123 was passed
        call_kwargs = mock_run.call_args[1] if mock_run.call_args[1] else {}
        call_args = mock_run.call_args[0] if mock_run.call_args[0] else ()
        assert 123 in call_args or call_kwargs.get("seed") == 123

    def test_no_schedule_flag(self):
        """Verify --schedule flag was removed."""
        from eval.daily_eval import main
        import argparse
        # Parse with --schedule should fail
        parser = argparse.ArgumentParser()
        parser.add_argument("--tickers")
        parser.add_argument("--history", action="store_true")
        parser.add_argument("--seed", type=int, default=42)
        # The actual parser should not have --schedule
        # Just verify the function doesn't exist
        import eval.daily_eval as de
        assert not hasattr(de, "run_scheduled")


# ═══════════════════════════════════════════════════════════════════════════
# run_daily_eval UNIT TESTS (mocked heavily to avoid slow imports)
# ═══════════════════════════════════════════════════════════════════════════

class TestRunDailyEvalUnit:
    """Test run_daily_eval logic using module-level pre-patching to avoid heavy imports."""

    def _make_mock_result(self, strategy="double_ma", ticker="NVDA", sharpe=0.5, passed=True):
        mock_wf = MagicMock()
        mock_wf.avg_oos_sharpe = sharpe
        mock_wf.pct_positive_sharpe = 0.6
        mock_wf.avg_information_ratio = 0.3

        mock_eval = MagicMock()
        mock_eval.strategy_name = strategy
        mock_eval.ticker = ticker
        mock_eval.walk_forward = mock_wf
        mock_eval.overall_pass = passed

        mock_result = MagicMock()
        mock_result.evaluations = [mock_eval]
        mock_result.total_evaluated = 1
        mock_result.total_passed = 1 if passed else 0
        return mock_result

    def test_snapshot_file_written(self, tmp_history):
        """Test snapshot JSON is written to history dir."""
        result = self._make_mock_result()

        # Pre-populate modules cache to avoid heavy imports
        mock_harness_mod = MagicMock()
        mock_harness_cls = MagicMock()
        mock_harness_cls.return_value.run.return_value = result
        mock_harness_mod.EvaluationHarness = mock_harness_cls

        mock_report_mod = MagicMock()
        mock_report_mod._result_to_dict.return_value = {"base": True}

        with patch.dict("sys.modules", {
            "eval.harness": mock_harness_mod,
            "eval.report_generator": mock_report_mod,
        }):
            # Re-import to pick up mocked modules
            import importlib
            import eval.daily_eval as de
            importlib.reload(de)
            de._HISTORY_DIR = tmp_history

            snapshot = de.run_daily_eval(tickers=["NVDA"], seed=42)

        assert "run_date" in snapshot
        assert "strategy_summary" in snapshot
        assert "double_ma_NVDA" in snapshot["strategy_summary"]
        snapshot_files = list(tmp_history.glob("eval_*.json"))
        assert len(snapshot_files) == 1

    def test_drift_log_appended(self, tmp_history):
        """Test drift.jsonl entry is created."""
        result = self._make_mock_result(sharpe=0.8, passed=False)

        mock_harness_mod = MagicMock()
        mock_harness_cls = MagicMock()
        mock_harness_cls.return_value.run.return_value = result
        mock_harness_mod.EvaluationHarness = mock_harness_cls

        mock_report_mod = MagicMock()
        mock_report_mod._result_to_dict.return_value = {}

        with patch.dict("sys.modules", {
            "eval.harness": mock_harness_mod,
            "eval.report_generator": mock_report_mod,
        }):
            import importlib
            import eval.daily_eval as de
            importlib.reload(de)
            de._HISTORY_DIR = tmp_history

            de.run_daily_eval(tickers=["AAPL"], seed=42)

        drift_path = tmp_history / "drift.jsonl"
        assert drift_path.exists()
        entry = json.loads(drift_path.read_text().strip())
        assert entry["total_evaluated"] == 1
        assert entry["top_sharpe"] == 0.8
