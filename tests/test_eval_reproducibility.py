"""The declared family and modeled costs must survive missing data."""

import hashlib
import numpy as np
import pandas as pd
import pytest

from engine.backtest import simple_backtest
from eval.harness import EvaluationHarness
from eval.report_generator import _generate_ranking_table
from eval import report_generator
from eval.statistical_tests import adjust_pvalues, run_statistical_tests, ttest_returns

NINE_STRATEGIES = ["double_ma", "macd_crossover", "bollinger_breakout", "rsi_reversal",
                   "trend_momentum", "alpha_combo", "dual_thrust", "ensemble_vote", "regime_ensemble"]


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


def test_transaction_and_slippage_costs_on_entry_and_exit():
    prices = pd.DataFrame({"Close": [100.0, 100.0, 100.0], "signal": [0, 1, 0]})
    result = simple_backtest(prices)
    assert result["trade_cost"].tolist() == pytest.approx([0.0, 0.002, 0.002])
    assert result["net_strategy_return"].sum() == pytest.approx(-0.004)


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
