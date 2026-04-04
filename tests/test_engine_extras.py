"""
tests/test_engine_extras.py
────────────────────────────────────────────────────────────────────────────
Tests for engine modules: decision_log, demo_data, factor_engine, multi_strategy.
~35 tests covering core functionality with synthetic data, no external deps.
"""

import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

# ── path setup ──────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.decision import DecisionOutput


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES — synthetic OHLCV + indicators
# ═══════════════════════════════════════════════════════════════════════════

def _make_ohlcv(rows: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV DataFrame with realistic indicator columns."""
    rng = np.random.RandomState(seed)
    dates = pd.bdate_range("2024-01-01", periods=rows)

    close = 100.0 + np.cumsum(rng.randn(rows) * 0.5)
    high = close + rng.uniform(0.2, 1.5, rows)
    low = close - rng.uniform(0.2, 1.5, rows)
    opn = close + rng.uniform(-0.5, 0.5, rows)
    volume = rng.randint(1_000_000, 10_000_000, rows).astype(float)

    df = pd.DataFrame({
        "Open": opn,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)

    # Technical indicators required by strategies
    df["MA5"] = df["Close"].rolling(5, min_periods=1).mean()
    df["MA10"] = df["Close"].rolling(10, min_periods=1).mean()
    df["MA20"] = df["Close"].rolling(20, min_periods=1).mean()
    df["MA50"] = df["Close"].rolling(50, min_periods=1).mean()

    df["RSI"] = 50 + rng.randn(rows) * 15
    df["RSI"] = df["RSI"].clip(10, 90)

    df["MACD"] = rng.randn(rows) * 0.5
    df["MACD_Signal"] = df["MACD"].rolling(9, min_periods=1).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    bb_mid = df["MA20"]
    bb_std = df["Close"].rolling(20, min_periods=1).std().fillna(0.5)
    df["BB_Mid"] = bb_mid
    df["BB_Upper"] = bb_mid + 2 * bb_std
    df["BB_Lower"] = bb_mid - 2 * bb_std
    df["BB_Pct"] = (df["Close"] - df["BB_Lower"]) / (df["BB_Upper"] - df["BB_Lower"] + 1e-9)

    df["ADX"] = 20 + rng.randn(rows) * 10
    df["ADX"] = df["ADX"].clip(5, 80)

    df["ATR"] = (df["High"] - df["Low"]).rolling(14, min_periods=1).mean()

    return df


def _make_decision(**overrides) -> DecisionOutput:
    defaults = dict(
        decision="BUY",
        confidence=72.5,
        risk_level="MEDIUM",
        reasoning=["RSI oversold", "Volume spike"],
        probabilities={"up": 0.6, "neutral": 0.25, "down": 0.15},
        source="test",
    )
    defaults.update(overrides)
    return DecisionOutput(**defaults)


# ═══════════════════════════════════════════════════════════════════════════
# decision_log tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDecisionLog:
    """Tests for engine/decision_log.py."""

    def test_save_and_load_are_callable(self):
        from engine.decision_log import save_decision, load_decisions
        assert callable(save_decision)
        assert callable(load_decisions)

    def test_save_decision_writes_record(self, tmp_path):
        from engine import decision_log

        log_file = tmp_path / "decision_log.json"
        with patch.object(decision_log, "LOG_PATH", str(log_file)):
            dec = _make_decision()
            decision_log.save_decision(dec, ticker="NVDA", mode="scalp", timeframe="5m", entry_price=142.5)

            data = json.loads(log_file.read_text(encoding="utf-8"))
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["ticker"] == "NVDA"
            assert data[0]["decision"] == "BUY"
            assert data[0]["confidence"] == 72.5

    def test_load_decisions_empty_when_no_file(self, tmp_path):
        from engine import decision_log

        log_file = tmp_path / "nonexistent.json"
        with patch.object(decision_log, "LOG_PATH", str(log_file)):
            result = decision_log.load_decisions()
            assert result == []

    def test_save_multiple_newest_first(self, tmp_path):
        from engine import decision_log

        log_file = tmp_path / "decision_log.json"
        with patch.object(decision_log, "LOG_PATH", str(log_file)):
            for ticker in ["AAPL", "TSLA", "NVDA"]:
                decision_log.save_decision(
                    _make_decision(), ticker=ticker, mode="scalp", timeframe="5m"
                )

            data = decision_log.load_decisions(n=50)
            assert len(data) == 3
            # newest (NVDA) first
            assert data[0]["ticker"] == "NVDA"
            assert data[2]["ticker"] == "AAPL"

    def test_load_decisions_respects_n_limit(self, tmp_path):
        from engine import decision_log

        log_file = tmp_path / "decision_log.json"
        with patch.object(decision_log, "LOG_PATH", str(log_file)):
            for i in range(10):
                decision_log.save_decision(
                    _make_decision(), ticker=f"T{i}", mode="scalp", timeframe="5m"
                )
            result = decision_log.load_decisions(n=3)
            assert len(result) == 3

    def test_save_caps_at_500(self, tmp_path):
        from engine import decision_log

        log_file = tmp_path / "decision_log.json"
        # Pre-populate with 500 entries
        existing = [{"ticker": f"X{i}"} for i in range(500)]
        log_file.write_text(json.dumps(existing), encoding="utf-8")

        with patch.object(decision_log, "LOG_PATH", str(log_file)):
            decision_log.save_decision(
                _make_decision(), ticker="NEW", mode="scalp", timeframe="5m"
            )
            data = json.loads(log_file.read_text(encoding="utf-8"))
            assert len(data) == 500
            assert data[0]["ticker"] == "NEW"

    def test_record_contains_expected_keys(self, tmp_path):
        from engine import decision_log

        log_file = tmp_path / "decision_log.json"
        with patch.object(decision_log, "LOG_PATH", str(log_file)):
            decision_log.save_decision(
                _make_decision(), ticker="AMD", mode="swing", timeframe="1D",
                entry_price=128.0, notes="test note"
            )
            data = json.loads(log_file.read_text(encoding="utf-8"))
            record = data[0]
            for key in ["timestamp", "ticker", "mode", "timeframe", "entry_price",
                        "notes", "decision", "confidence", "risk_level",
                        "reasoning", "probabilities", "source"]:
                assert key in record, f"Missing key: {key}"

    def test_load_handles_corrupt_json(self, tmp_path):
        from engine import decision_log

        log_file = tmp_path / "decision_log.json"
        log_file.write_text("{bad json", encoding="utf-8")

        with patch.object(decision_log, "LOG_PATH", str(log_file)):
            result = decision_log.load_decisions()
            assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# demo_data tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDemoData:
    """Tests for engine/demo_data.py."""

    def test_mock_analyze_returns_expected_keys(self):
        from engine.demo_data import mock_analyze
        result = mock_analyze("NVDA", mode="scalp", timeframe="5m")
        for key in ["decision", "confidence", "risk_level", "signal_strength",
                     "probabilities", "reasoning", "recommendation", "source"]:
            assert key in result, f"Missing key: {key}"

    def test_mock_analyze_decision_values(self):
        from engine.demo_data import mock_analyze
        result = mock_analyze("AAPL")
        assert result["decision"] in ("BUY", "SELL", "WAIT")
        assert result["risk_level"] in ("LOW", "MEDIUM", "HIGH")

    def test_mock_analyze_confidence_range(self):
        from engine.demo_data import mock_analyze
        for _ in range(20):
            result = mock_analyze("TSLA")
            assert 60 <= result["confidence"] <= 95

    def test_mock_analyze_probabilities_sum(self):
        from engine.demo_data import mock_analyze
        result = mock_analyze("NVDA")
        probs = result["probabilities"]
        assert "up" in probs and "neutral" in probs and "down" in probs
        # Allow small floating point tolerance
        assert abs(probs["up"] + probs["neutral"] + probs["down"] - 1.0) < 0.05

    def test_mock_analyze_source_contains_mode(self):
        from engine.demo_data import mock_analyze
        result = mock_analyze("NVDA", mode="swing")
        assert "swing" in result["source"]

    def test_mock_news_returns_items(self):
        from engine.demo_data import mock_news
        result = mock_news("NVDA")
        assert "ticker" in result
        assert "items" in result
        assert len(result["items"]) > 0
        item = result["items"][0]
        assert "title" in item
        assert "sentiment" in item
        assert item["sentiment"] in ("bullish", "bearish", "neutral")

    def test_mock_deep_analysis_has_reports(self):
        from engine.demo_data import mock_deep_analysis
        result = mock_deep_analysis("NVDA")
        assert "reports" in result
        assert "investment_plan" in result
        assert "ml_models" in result
        assert len(result["ml_models"]) == 3

    def test_mock_live_price_reasonable(self):
        from engine.demo_data import mock_live, DEMO_TICKERS
        result = mock_live("NVDA")
        base_price = DEMO_TICKERS["NVDA"]["price"]
        assert result["price"] > base_price * 0.9
        assert result["price"] < base_price * 1.1

    def test_mock_profile_keys(self):
        from engine.demo_data import mock_profile
        result = mock_profile()
        for key in ["style", "win_rate", "today", "patterns", "preferred_mode"]:
            assert key in result

    def test_mock_watchlist_scan_sorted_by_signal(self):
        from engine.demo_data import mock_watchlist_scan
        result = mock_watchlist_scan(["NVDA", "AAPL", "TSLA"])
        tickers = result["tickers"]
        assert len(tickers) == 3
        strengths = [t["signal_strength"] for t in tickers]
        assert strengths == sorted(strengths, reverse=True)

    def test_mock_daily_intel_structure(self):
        from engine.demo_data import mock_daily_intel
        result = mock_daily_intel()
        for key in ["date", "market_mood", "gainers", "losers",
                     "volume_spikes", "sectors", "headlines", "ai_picks"]:
            assert key in result

    def test_demo_tickers_have_required_fields(self):
        from engine.demo_data import DEMO_TICKERS
        for ticker, info in DEMO_TICKERS.items():
            assert "name" in info
            assert "price" in info
            assert "sector" in info
            assert info["price"] > 0


# ═══════════════════════════════════════════════════════════════════════════
# factor_engine tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFactorEngine:
    """Tests for engine/factor_engine.py."""

    def test_compute_all_returns_dict(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        fe = FactorEngine(df)
        factors = fe.compute_all()
        assert isinstance(factors, dict)
        assert len(factors) >= 5

    def test_each_factor_is_series_aligned_to_index(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        fe = FactorEngine(df)
        factors = fe.compute_all()
        for name, series in factors.items():
            assert isinstance(series, pd.Series), f"{name} is not a Series"
            assert len(series) == len(df), f"{name} length mismatch"

    def test_momentum_factor(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        fe = FactorEngine(df)
        result = fe.momentum_factor()
        assert isinstance(result, pd.Series)
        assert "momentum" in fe._factors

    def test_volatility_factor(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        fe = FactorEngine(df)
        result = fe.volatility_factor()
        assert isinstance(result, pd.Series)
        assert "volatility" in fe._factors

    def test_volume_factor(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        fe = FactorEngine(df)
        result = fe.volume_factor()
        assert isinstance(result, pd.Series)
        assert "volume" in fe._factors

    def test_trend_factor_uses_ma_columns(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        fe = FactorEngine(df)
        result = fe.trend_factor()
        assert isinstance(result, pd.Series)
        assert "trend" in fe._factors

    def test_reversal_factor(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        fe = FactorEngine(df)
        result = fe.reversal_factor()
        assert isinstance(result, pd.Series)
        assert "reversal" in fe._factors

    def test_rsi_reversal_factor_with_rsi(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        fe = FactorEngine(df)
        result = fe.rsi_reversal_factor()
        assert isinstance(result, pd.Series)
        assert "rsi_reversal" in fe._factors

    def test_rsi_reversal_factor_without_rsi(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        df = df.drop(columns=["RSI"])
        fe = FactorEngine(df)
        result = fe.rsi_reversal_factor()
        assert (result == 0.0).all()

    def test_atr_breakout_factor_without_atr(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        df = df.drop(columns=["ATR"])
        fe = FactorEngine(df)
        result = fe.atr_breakout_factor()
        assert (result == 0.0).all()

    def test_composite_alpha_returns_series(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        fe = FactorEngine(df)
        fe.compute_all()
        alpha = fe.composite_alpha()
        assert isinstance(alpha, pd.Series)
        assert len(alpha) == len(df)

    def test_composite_alpha_auto_computes(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        fe = FactorEngine(df)
        # Don't call compute_all; composite_alpha should do it
        alpha = fe.composite_alpha()
        assert len(fe._factors) >= 5

    def test_factor_table_returns_dataframe(self):
        from engine.factor_engine import FactorEngine
        df = _make_ohlcv(100)
        fe = FactorEngine(df)
        table = fe.factor_table()
        assert isinstance(table, pd.DataFrame)
        assert table.shape[0] == len(df)
        assert table.shape[1] >= 5

    def test_factor_signal_returns_binary_series(self):
        from engine.factor_engine import factor_signal
        df = _make_ohlcv(200)
        result = factor_signal(df, {"alpha_threshold": 0.5, "exit_threshold": 0.0})
        assert isinstance(result, pd.Series)
        assert set(result.unique()).issubset({0, 1})

    def test_rank_tickers_by_alpha(self):
        from engine.factor_engine import rank_tickers_by_alpha
        ticker_dfs = {
            "AAPL": _make_ohlcv(100, seed=1),
            "NVDA": _make_ohlcv(100, seed=2),
            "TSLA": _make_ohlcv(100, seed=3),
        }
        result = rank_tickers_by_alpha(ticker_dfs, lookback_days=20)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        assert "ticker" in result.columns
        assert "alpha_score" in result.columns

    def test_rank_tickers_skips_short_data(self):
        from engine.factor_engine import rank_tickers_by_alpha
        ticker_dfs = {
            "SHORT": _make_ohlcv(5, seed=1),
        }
        result = rank_tickers_by_alpha(ticker_dfs, lookback_days=20)
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════════════
# multi_strategy tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiStrategy:
    """Tests for engine/multi_strategy.py."""

    def test_run_multi_strategy_analysis_returns_dict(self):
        from engine.multi_strategy import run_multi_strategy_analysis
        df = _make_ohlcv(200)
        train = df.iloc[:140]
        test = df.iloc[140:]
        result = run_multi_strategy_analysis(train, test, ticker="TEST")
        assert isinstance(result, dict)
        assert result["ticker"] == "TEST"

    def test_analysis_identifies_best_strategy(self):
        from engine.multi_strategy import run_multi_strategy_analysis
        df = _make_ohlcv(200)
        train = df.iloc[:140]
        test = df.iloc[140:]
        result = run_multi_strategy_analysis(train, test, ticker="NVDA")
        assert result["best_strategy"] is not None
        assert result["best_strategy"] in [
            "double_ma", "macd_crossover", "bollinger_breakout",
            "rsi_reversal", "trend_momentum", "alpha_combo",
            "dual_thrust", "ensemble_vote", "regime_ensemble",
        ]

    def test_analysis_returns_multiple_strategy_results(self):
        from engine.multi_strategy import run_multi_strategy_analysis
        df = _make_ohlcv(200)
        train = df.iloc[:140]
        test = df.iloc[140:]
        result = run_multi_strategy_analysis(train, test, ticker="NVDA")
        assert len(result["all_results"]) >= 5
        assert len(result["ranking"]) >= 1

    def test_analysis_has_train_and_test_metrics(self):
        from engine.multi_strategy import run_multi_strategy_analysis
        df = _make_ohlcv(200)
        train = df.iloc[:140]
        test = df.iloc[140:]
        result = run_multi_strategy_analysis(train, test, ticker="NVDA")
        for key in ["sharpe", "total_return", "max_drawdown", "win_rate", "n_trades"]:
            assert key in result["train_metrics"], f"Missing train metric: {key}"
            assert key in result["test_metrics"], f"Missing test metric: {key}"

    def test_runner_summary_table(self):
        from engine.multi_strategy import MultiStrategyRunner
        df = _make_ohlcv(200)
        train = df.iloc[:140]
        test = df.iloc[140:]
        runner = MultiStrategyRunner(train, test)
        runner.run_all()
        table = runner.summary_table()
        assert isinstance(table, pd.DataFrame)
        assert "strategy" in table.columns
        assert len(table) >= 5

    def test_runner_get_best_by_different_metrics(self):
        from engine.multi_strategy import MultiStrategyRunner
        df = _make_ohlcv(200)
        train = df.iloc[:140]
        test = df.iloc[140:]
        runner = MultiStrategyRunner(train, test)
        runner.run_all()

        best_sharpe = runner.get_best(rank_by="sharpe", split="train")
        best_return = runner.get_best(rank_by="total_return", split="test")
        assert "strategy" in best_sharpe
        assert "strategy" in best_return

    def test_runner_strategy_ranking_sorted(self):
        from engine.multi_strategy import MultiStrategyRunner
        df = _make_ohlcv(200)
        train = df.iloc[:140]
        test = df.iloc[140:]
        runner = MultiStrategyRunner(train, test)
        runner.run_all()
        ranking = runner.get_strategy_ranking()
        assert len(ranking) >= 2
        sharpes = [s for _, s in ranking]
        assert sharpes == sorted(sharpes, reverse=True)

    def test_ensemble_signal(self):
        from engine.multi_strategy import ensemble_signal
        df = _make_ohlcv(200)
        result = ensemble_signal(df, ["double_ma", "macd_crossover", "rsi_reversal"])
        assert isinstance(result, pd.Series)
        assert set(result.unique()).issubset({0, 1})

    def test_ensemble_signal_empty_strategies(self):
        from engine.multi_strategy import ensemble_signal
        df = _make_ohlcv(100)
        result = ensemble_signal(df, ["nonexistent_strategy"])
        assert (result == 0).all()

    def test_run_strategy_backtest_metrics(self):
        from engine.multi_strategy import _run_strategy_backtest
        df = _make_ohlcv(100)
        signal = pd.Series(np.where(df["RSI"] < 50, 1, 0), index=df.index)
        metrics = _run_strategy_backtest(df, signal)
        assert isinstance(metrics, dict)
        for key in ["total_return", "market_return", "sharpe",
                     "max_drawdown", "win_rate", "n_trades", "calmar", "excess_return"]:
            assert key in metrics

    def test_runner_with_custom_params(self):
        from engine.multi_strategy import MultiStrategyRunner
        df = _make_ohlcv(200)
        train = df.iloc[:140]
        test = df.iloc[140:]
        runner = MultiStrategyRunner(
            train, test,
            strategies_to_run=["double_ma"],
            custom_params={"double_ma": {"fast_period": 10, "slow_period": 30}},
        )
        runner.run_all()
        assert "double_ma" in runner.results
        assert runner.results["double_ma"]["params"]["fast_period"] == 10
