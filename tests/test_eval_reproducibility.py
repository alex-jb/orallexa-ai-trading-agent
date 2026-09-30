"""The declared family and modeled costs must survive missing data."""

import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from engine.backtest import simple_backtest
from engine.strategies import STRATEGY_REGISTRY
from eval.harness import EvaluationHarness, HarnessResult, StrategyEvaluation
from eval.report_generator import _generate_ranking_table
from eval.walk_forward import run_walk_forward
from eval import report_generator
from eval.statistical_tests import adjust_pvalues, run_statistical_tests, ttest_returns

NINE_STRATEGIES = ["double_ma", "macd_crossover", "bollinger_breakout", "rsi_reversal",
                   "trend_momentum", "alpha_combo", "dual_thrust", "ensemble_vote", "regime_ensemble"]


def _write_synthetic_alpaca_manifest(path):
    from eval.freeze_alpaca_data import TICKERS, PROTOCOL_IDS

    (path / "manifest.json").write_text(json.dumps({
        "protocol_id": PROTOCOL_IDS["iex"], "source": "Alpaca Historical Stock Bars GET API",
        "tickers": list(TICKERS), "sha256": {ticker: "0" * 64 for ticker in TICKERS},
        "parameters": {"feed": "iex", "adjustment": "split,dividend", "start": "2021-01-01",
                       "last_session_required": "2026-09-28"},
    }))


def test_90_pair_adjustment_includes_unobserved_tests():
    raw = [0.0001, 0.001] + [1.0] * 88
    bonf, bh = adjust_pvalues(raw)
    assert len(bonf) == len(bh) == 90
    assert bonf[:2] == pytest.approx([0.009, 0.09])
    assert bh[:2] == pytest.approx([0.009, 0.045])
    assert all(p == 1.0 for p in bonf[2:])


def test_adjustment_rejects_invalid_pvalues():
    with pytest.raises(ValueError):
        adjust_pvalues([0.02, float("nan")])


def test_missing_snapshots_stay_in_full_family_and_do_not_pass(tmp_path, monkeypatch):
    tickers = ["NVDA", "AAPL", "TSLA", "GOOG", "META", "INTC", "QQQ", "MSFT", "AMZN", "SPY"]
    result = EvaluationHarness(tickers=tickers, strategies=NINE_STRATEGIES, data_dir=tmp_path).run()
    assert result.total_evaluated == 0
    assert result.total_passed == 0
    assert len(result.evaluations) == 90
    assert all(e.verdict == "NOT EVALUATED" for e in result.evaluations)
    table = _generate_ranking_table(result)
    assert table.count("NOT EVALUATED") == 90
    monkeypatch.setattr(report_generator, "_CHARTS", tmp_path / "charts")
    report = report_generator.generate_report(result, output_path=tmp_path / "report.md")
    assert report.count("NOT EVALUATED") >= 90
    assert "0/90 predeclared" in report
    assert "10 bps" in report
    assert "Raw excess p" in report
    assert "do not validate a trading edge" in report


def test_transaction_and_slippage_costs_on_entry_and_exit():
    prices = pd.DataFrame({"Open": [100.0] * 4, "Close": [100.0] * 4,
                           "signal": [0, 1, 0, 0]})
    result = simple_backtest(prices, execution_mode="next_open")
    assert result["trade_cost"].tolist() == pytest.approx([0.0, 0.0, 0.002, 0.002])
    assert result["net_strategy_return"].sum() == pytest.approx(-0.004)


def test_last_close_signal_has_no_unexecuted_entry_cost():
    prices = pd.DataFrame({"Open": [100.0] * 3, "Close": [100.0] * 3,
                           "signal": [0, 0, 1]})
    result = simple_backtest(prices, execution_mode="next_open")
    assert result["trade_cost"].sum() == 0
    assert result["gross_strategy_return"].sum() == 0


def test_flat_oos_returns_cannot_be_declared_significant():
    assert ttest_returns(np.zeros(252)) == (0.0, 1.0)
    result = run_statistical_tests(np.zeros(252), "flat", "NVDA", num_strategies_tested=90)
    assert result.p_value == 1.0
    assert result.dsr == 0.0


def test_pinned_snapshot_produces_oos_test_and_hash(tmp_path):
    rng = np.random.default_rng(19)
    close = 100 + np.cumsum(rng.normal(0.05, 1.0, 520))
    dates = pd.bdate_range("2021-01-01", periods=520, name="Date")
    df = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                       "Close": close, "Volume": 100000}, index=dates)
    snapshot = tmp_path / "NVDA.csv"
    df.to_csv(snapshot)
    harness = EvaluationHarness(tickers=["NVDA"], strategies=["double_ma"],
                                data_dir=tmp_path, mc_seed=42, mc_iterations=10)
    harness.adaptive = False
    result = harness.run()
    assert result.total_evaluated == 1
    assert result.data_sha256["NVDA"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    st = result.evaluations[0].statistical
    assert st is not None
    assert st.n_observations == 4 * 63  # four 63-bar windows, not 520 in-sample bars
    assert st.p_bonferroni == pytest.approx(st.p_value)


def test_matched_oos_entry_excludes_training_overnight_and_charges_both_entries():
    dates = pd.bdate_range("2025-01-01", periods=315)
    prices = pd.DataFrame({"Open": 100.0, "High": 122.0, "Low": 99.0,
                           "Close": 100.0, "Volume": 100000}, index=dates)
    # A gap after the final training close cannot be earned by a rule fitted
    # through that close. The opening rule and benchmark buy the same ticker.
    prices.iloc[252, prices.columns.get_loc("Open")] = 110.0
    prices.iloc[252, prices.columns.get_loc("Close")] = 121.0
    rule = lambda df, _params: pd.Series(1, index=df.index)
    wf = run_walk_forward(prices, rule, "synthetic_hold", {},
                          initial_train_days=252, test_days=63,
                          min_windows=1, adaptive=False)
    expected = (1 - 0.002) * (121 / 110) - 1
    assert wf.oos_returns[0] == pytest.approx(expected)
    assert wf.oos_benchmark_returns[0] == pytest.approx(expected)
    assert wf.oos_excess_returns == pytest.approx([0.0] * 63)
    assert wf.windows[0].num_trades == 1


def test_positive_absolute_net_return_can_fail_matched_excess_gate(tmp_path, monkeypatch):
    dates = pd.bdate_range("2021-01-01", periods=520, name="Date")
    close = 100 * np.power(1.01, np.arange(520))
    df = pd.DataFrame({"Open": close, "High": close * 1.001,
                       "Low": close * 0.999, "Close": close,
                       "Volume": 100000}, index=dates)
    df.to_csv(tmp_path / "NVDA.csv")

    def brief_long_signal(data, _params):
        # Each OOS window buys at the first open and then sits out most of a
        # steadily rising ticker. Absolute net returns remain positive.
        return pd.Series(((np.arange(len(data)) - 251) % 63 < 16).astype(int),
                         index=data.index)

    monkeypatch.setitem(STRATEGY_REGISTRY, "brief_long_signal", brief_long_signal)
    harness = EvaluationHarness(tickers=["NVDA"], strategies=["brief_long_signal"],
                                data_dir=tmp_path, mc_seed=42, mc_iterations=10)
    harness.adaptive = False
    ev = harness.run().evaluations[0]
    assert ev.absolute_net_p_value < 0.05
    assert ev.statistical.p_value > 0.95
    assert np.mean(ev.walk_forward.oos_excess_returns) < 0
    assert ev.statistical.p_bonferroni == pytest.approx(ev.statistical.p_value)
    assert ev.verdict == "FAIL"


def test_strategy_failure_remains_unevaluated_even_with_complete_snapshot(tmp_path, monkeypatch):
    close = np.linspace(100, 120, 520)
    df = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                       "Close": close, "Volume": 100000},
                      index=pd.bdate_range("2021-01-01", periods=520, name="Date"))
    df.to_csv(tmp_path / "NVDA.csv")

    def broken(_data, _params):
        raise RuntimeError("synthetic strategy failure")

    monkeypatch.setitem(STRATEGY_REGISTRY, "broken", broken)
    result = EvaluationHarness(tickers=["NVDA"], strategies=["broken"],
                               data_dir=tmp_path, mc_iterations=10).run()
    assert result.total_evaluated == 0
    assert result.evaluations[0].verdict == "NOT EVALUATED"
    assert result.evaluations[0].overall_pass is False


def test_snapshot_hash_mismatch_prevents_any_evaluation(tmp_path):
    snapshot = tmp_path / "NVDA.csv"
    snapshot.write_text("Date,Open,High,Low,Close,Volume\n2021-01-01,100,101,99,100,1000\n")
    (tmp_path / "manifest.json").write_text(json.dumps({"sha256": {"NVDA": "0" * 64}}))
    result = EvaluationHarness(tickers=["NVDA"], strategies=["double_ma"],
                               data_dir=tmp_path).run()
    assert result.total_evaluated == 0
    assert result.evaluations[0].verdict == "NOT EVALUATED"


def test_cli_rejects_incomplete_family_before_writing_report(tmp_path, monkeypatch):
    import sys
    from eval import run_harness

    _write_synthetic_alpaca_manifest(tmp_path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("incomplete run must not generate report artifacts")

    monkeypatch.setattr(report_generator, "generate_report", forbidden)
    monkeypatch.setattr(sys, "argv", ["run_harness", "--tickers", "NVDA",
                                   "--strategies", "double_ma", "--data-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        run_harness.main()
    assert exc.value.code == 2


def test_alpaca_result_defaults_to_private_report_without_charts(tmp_path, monkeypatch):
    import sys
    from eval import run_harness

    _write_synthetic_alpaca_manifest(tmp_path)
    result = HarnessResult(tickers=["NVDA"], strategies=["double_ma"],
                           evaluations=[StrategyEvaluation("double_ma", "NVDA", verdict="FAIL")],
                           total_evaluated=1)
    monkeypatch.setattr(EvaluationHarness, "run", lambda self, progress_callback=None: result)
    calls = []
    monkeypatch.setattr(report_generator, "generate_report", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(sys, "argv", ["run_harness", "--tickers", "NVDA", "--strategies", "double_ma",
                                   "--data-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        run_harness.main()
    assert exc.value.code == 0
    assert calls == [{"output_path": tmp_path / "evaluation_report.md", "generate_charts": False}]


def test_alpaca_result_rejects_tracked_docs_output_before_evaluation(tmp_path, monkeypatch):
    import sys
    from eval import run_harness

    _write_synthetic_alpaca_manifest(tmp_path)
    docs_report = Path(__file__).resolve().parents[1] / "docs/evaluation_report.md"
    monkeypatch.setattr(sys, "argv", ["run_harness", "--tickers", "NVDA", "--strategies", "double_ma",
                                   "--data-dir", str(tmp_path), "--output", str(docs_report)])
    with pytest.raises(SystemExit) as exc:
        run_harness.main()
    assert exc.value.code == 2


def test_cli_requires_freeze_manifest_for_pinned_data(tmp_path, monkeypatch):
    import sys
    from eval import run_harness

    monkeypatch.setattr(sys, "argv", ["run_harness", "--tickers", "NVDA",
                                   "--strategies", "double_ma", "--data-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        run_harness.main()
    assert exc.value.code == 2
