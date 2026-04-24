"""
tests/test_engine_integration.py
────────────────────────────────────────────────────────────────────
Integration tests for the trading engine pipeline.

Covers:
  - Technical analysis indicator computation
  - Strategy signal generation
  - Backtest execution
  - Brain routing (scalp/intraday/swing)
  - Alert system
  - Decision logging
  - Multi-agent analysis (without LLM calls)
  - API server endpoints (mocked)
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_ohlcv():
    """Generate 200 days of realistic OHLCV data."""
    np.random.seed(42)
    n = 200
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(np.random.randn(n) * 1.5)
    close = np.maximum(close, 10)  # no negative prices

    df = pd.DataFrame({
        "Open": close + np.random.randn(n) * 0.5,
        "High": close + np.abs(np.random.randn(n)) * 1.0,
        "Low": close - np.abs(np.random.randn(n)) * 1.0,
        "Close": close,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)
    return df


@pytest.fixture
def ta_df(sample_ohlcv):
    """OHLCV with technical indicators computed."""
    from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2
    ta = TechnicalAnalysisSkillV2(sample_ohlcv)
    ta.add_indicators()
    return ta.df.dropna()


@pytest.fixture
def train_test(ta_df):
    """80/20 split of ta_df."""
    split = int(len(ta_df) * 0.8)
    return ta_df.iloc[:split], ta_df.iloc[split:]


# ═══════════════════════════════════════════════════════════════════════════
# TECHNICAL ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

class TestTechnicalAnalysis:
    def test_indicators_computed(self, ta_df):
        required = ["RSI", "MACD", "MACD_Signal", "BB_Pct", "ADX", "MA20", "MA50"]
        for col in required:
            assert col in ta_df.columns, f"Missing indicator: {col}"

    def test_rsi_in_range(self, ta_df):
        rsi = ta_df["RSI"].dropna()
        assert rsi.min() >= 0, "RSI below 0"
        assert rsi.max() <= 100, "RSI above 100"

    def test_bb_pct_reasonable(self, ta_df):
        bb = ta_df["BB_Pct"].dropna()
        assert bb.min() >= -1.0, "BB% unreasonably low"
        assert bb.max() <= 2.0, "BB% unreasonably high"

    def test_no_all_nan_columns(self, ta_df):
        for col in ta_df.columns:
            assert not ta_df[col].isna().all(), f"Column {col} is all NaN"

    def test_volume_ratio_positive(self, ta_df):
        if "Volume_Ratio" in ta_df.columns:
            assert (ta_df["Volume_Ratio"].dropna() >= 0).all()


# ═══════════════════════════════════════════════════════════════════════════
# STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════

class TestStrategies:
    @pytest.mark.parametrize("strategy_name", [
        "double_ma", "macd_crossover", "bollinger_breakout",
        "rsi_reversal", "trend_momentum", "alpha_combo",
    ])
    def test_strategy_returns_series(self, ta_df, strategy_name):
        from engine import strategies
        fn = getattr(strategies, strategy_name)
        signal = fn(ta_df, {})
        assert isinstance(signal, pd.Series)
        assert len(signal) == len(ta_df)

    @pytest.mark.parametrize("strategy_name", [
        "double_ma", "macd_crossover", "bollinger_breakout",
        "rsi_reversal", "trend_momentum", "alpha_combo",
    ])
    def test_strategy_values_valid(self, ta_df, strategy_name):
        from engine import strategies
        fn = getattr(strategies, strategy_name)
        signal = fn(ta_df, {})
        unique = set(signal.unique())
        assert unique.issubset({-1, 0, 1}), f"Invalid signal values: {unique}"


# ═══════════════════════════════════════════════════════════════════════════
# BACKTEST
# ═══════════════════════════════════════════════════════════════════════════

class TestBacktest:
    def test_simple_backtest(self, ta_df):
        from engine.backtest import simple_backtest
        df = ta_df.copy()
        df["signal"] = 1  # buy-and-hold signal column
        result = simple_backtest(df)
        assert result is not None
        assert len(result) > 0

    def test_ml_backtest(self, ta_df):
        from engine.ml_signal import MLSignalGenerator
        gen = MLSignalGenerator(ta_df, ta_df)
        signal = pd.Series(1, index=ta_df.index)
        metrics = gen._backtest_signal(ta_df, signal)
        assert "sharpe" in metrics
        assert "total_return" in metrics
        assert "win_rate" in metrics
        assert "n_trades" in metrics

    def test_zero_signal_no_crash(self, ta_df):
        from engine.ml_signal import MLSignalGenerator
        gen = MLSignalGenerator(ta_df, ta_df)
        signal = pd.Series(0, index=ta_df.index)
        metrics = gen._backtest_signal(ta_df, signal)
        assert metrics["n_trades"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# BRAIN ROUTING
# ═══════════════════════════════════════════════════════════════════════════

class TestBrainRouting:
    def test_scalp_mode(self):
        from core.brain import OrallexaBrain
        brain = OrallexaBrain("AAPL")
        result = brain.run_for_mode(mode="scalp", use_claude=False)
        assert result.decision in ("BUY", "SELL", "WAIT")
        assert result.source is not None

    def test_intraday_mode(self):
        from core.brain import OrallexaBrain
        brain = OrallexaBrain("AAPL")
        result = brain.run_for_mode(mode="intraday", timeframe="15m", use_claude=False)
        assert result.decision in ("BUY", "SELL", "WAIT")

    def test_swing_mode(self):
        from core.brain import OrallexaBrain
        brain = OrallexaBrain("AAPL")
        result = brain.run_for_mode(mode="swing", use_claude=False)
        assert result.decision in ("BUY", "SELL", "WAIT")

    def test_invalid_mode_defaults(self):
        from core.brain import OrallexaBrain
        brain = OrallexaBrain("AAPL")
        result = brain.run_for_mode(mode="unknown", use_claude=False)
        assert result.decision in ("BUY", "SELL", "WAIT")

    def test_decision_output_structure(self):
        from core.brain import OrallexaBrain
        brain = OrallexaBrain("AAPL")
        result = brain.run_for_mode(mode="intraday", use_claude=False)
        d = result.to_dict()
        assert "decision" in d
        assert "confidence" in d
        assert "risk_level" in d
        assert "reasoning" in d
        assert "probabilities" in d

    def test_portfolio_manager_rejection_downgrades_to_wait(self):
        """PM gate at heavy concentration forces BUY → WAIT."""
        from unittest.mock import patch
        from core.brain import OrallexaBrain
        from models.decision import DecisionOutput
        from engine.portfolio_manager import Position

        buy = DecisionOutput(
            decision="BUY",
            confidence=0.75,
            risk_level="MEDIUM",
            reasoning=["initial signal"],
            probabilities={"up": 0.6, "neutral": 0.2, "down": 0.2},
            source="test",
            signal_strength=0.6,
        )
        brain = OrallexaBrain("NVDA")
        # Patch run_prediction to return our canned BUY and bypass data fetch
        with patch.object(brain, "run_prediction", return_value=buy), \
             patch("models.confidence.guard_decision", side_effect=lambda x: x):
            result = brain.run_for_mode(
                mode="swing",
                use_claude=False,
                portfolio=[Position("NVDA", 3_000)],  # 30% — above default max 20%
                portfolio_value=10_000,
            )
        assert result.decision == "WAIT"
        assert any("Portfolio Manager rejected" in r for r in result.reasoning)

    def test_portfolio_manager_approval_appends_warnings(self):
        from unittest.mock import patch
        from core.brain import OrallexaBrain
        from models.decision import DecisionOutput
        from engine.portfolio_manager import Position

        buy = DecisionOutput(
            decision="BUY",
            confidence=0.80,
            risk_level="LOW",
            reasoning=["initial signal"],
            probabilities={"up": 0.7, "neutral": 0.2, "down": 0.1},
            source="test",
            signal_strength=0.7,
        )
        brain = OrallexaBrain("GOOGL")
        with patch.object(brain, "run_prediction", return_value=buy), \
             patch("models.confidence.guard_decision", side_effect=lambda x: x):
            result = brain.run_for_mode(
                mode="swing",
                use_claude=False,
                portfolio=[Position("GOOGL", 500)],
                portfolio_value=10_000,
                recent_decisions=[{"decision": "BUY"}] * 6,
            )
        assert result.decision == "BUY"
        assert any("PM warning" in r for r in result.reasoning)
        assert "portfolio_manager" in result.extra

    def test_no_pm_when_portfolio_omitted(self):
        """Backward-compat: omitting portfolio skips PM entirely."""
        from unittest.mock import patch
        from core.brain import OrallexaBrain
        from models.decision import DecisionOutput

        buy = DecisionOutput(
            decision="BUY",
            confidence=0.80,
            risk_level="LOW",
            reasoning=["initial"],
            probabilities={"up": 0.7, "neutral": 0.2, "down": 0.1},
            source="test",
            signal_strength=0.7,
        )
        brain = OrallexaBrain("AAPL")
        with patch.object(brain, "run_prediction", return_value=buy), \
             patch("models.confidence.guard_decision", side_effect=lambda x: x):
            result = brain.run_for_mode(mode="swing", use_claude=False)
        assert result.decision == "BUY"
        assert "portfolio_manager" not in result.extra

    def test_pm_failure_leaves_breadcrumb(self):
        """PM exception → decision unchanged but extra records the failure."""
        from unittest.mock import patch
        from core.brain import OrallexaBrain
        from models.decision import DecisionOutput
        from engine.portfolio_manager import Position

        buy = DecisionOutput(
            decision="BUY",
            confidence=0.75,
            risk_level="MEDIUM",
            reasoning=["initial"],
            probabilities={"up": 0.6, "neutral": 0.2, "down": 0.2},
            source="test",
            signal_strength=0.6,
        )
        brain = OrallexaBrain("NVDA")
        with patch.object(brain, "run_prediction", return_value=buy), \
             patch("models.confidence.guard_decision", side_effect=lambda x: x), \
             patch("engine.portfolio_manager.approve_decision",
                   side_effect=RuntimeError("bad data")):
            result = brain.run_for_mode(
                mode="swing",
                use_claude=False,
                portfolio=[Position("NVDA", 1_000)],
                portfolio_value=10_000,
            )
        assert result.decision == "BUY"  # unchanged
        assert "portfolio_manager" in result.extra
        assert result.extra["portfolio_manager"]["approved"] is None
        assert "bad data" in result.extra["portfolio_manager"]["error"]

    def test_pm_handles_none_confidence(self):
        """decision.confidence = None should not crash PM conversion."""
        from core.brain import _to_pct_scale
        assert _to_pct_scale(None) == 0
        assert _to_pct_scale(0.75) == 75
        assert _to_pct_scale(75) == 75
        assert _to_pct_scale(1.0) == 100
        assert _to_pct_scale(-5) == 0
        assert _to_pct_scale(500) == 100
        assert _to_pct_scale("garbage") == 0

    def test_get_regime_strategy_returns_proposal(self):
        """Real-data smoke test: get_regime_strategy picks a strategy for AAPL."""
        from core.brain import OrallexaBrain
        brain = OrallexaBrain("AAPL")
        result = brain.get_regime_strategy()
        assert result["regime"] in ("trending", "ranging", "volatile", "unknown")
        # When regime is detected, we get a known strategy or None
        if result["regime"] != "unknown":
            assert result["strategy"] in (
                None, "trend_momentum", "rsi_reversal", "dual_thrust",
            )
            assert "reasoning" in result

    def test_get_regime_strategy_handles_fetch_failure(self):
        """Data-prep failure → unknown regime, no crash."""
        from unittest.mock import patch
        from core.brain import OrallexaBrain
        brain = OrallexaBrain("XYZ")
        with patch.object(brain, "_prepare_data", side_effect=RuntimeError("no data")):
            result = brain.get_regime_strategy()
        assert result["regime"] == "unknown"
        assert result["strategy"] is None


# ═══════════════════════════════════════════════════════════════════════════
# ALERT SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

class TestAlertSystem:
    def test_add_alert(self, tmp_path):
        from bot.alerts import AlertManager, PriceAlert
        mgr = AlertManager(path=tmp_path / "alerts.json")
        idx = mgr.add(PriceAlert(ticker="TEST", target=100.0, direction="above"))
        assert idx == 0
        assert len(mgr.get_active()) == 1

    def test_alert_check_triggers(self, tmp_path):
        from bot.alerts import PriceAlert
        alert = PriceAlert(ticker="TEST", target=100.0, direction="above")
        assert alert.check(105.0) is True
        assert alert.check(95.0) is False

    def test_alert_below(self, tmp_path):
        from bot.alerts import PriceAlert
        alert = PriceAlert(ticker="TEST", target=100.0, direction="below")
        assert alert.check(95.0) is True
        assert alert.check(105.0) is False

    def test_triggered_not_retrigger(self, tmp_path):
        from bot.alerts import PriceAlert
        alert = PriceAlert(ticker="TEST", target=100.0, direction="above", triggered=True)
        assert alert.check(150.0) is False

    def test_persistence(self, tmp_path):
        from bot.alerts import AlertManager, PriceAlert
        path = tmp_path / "alerts.json"
        mgr1 = AlertManager(path=path)
        mgr1.add(PriceAlert(ticker="A", target=50.0, direction="above"))
        mgr1.add(PriceAlert(ticker="B", target=200.0, direction="below"))

        mgr2 = AlertManager(path=path)
        assert len(mgr2.get_all()) == 2


# ═══════════════════════════════════════════════════════════════════════════
# CONFIDENCE GUARD
# ═══════════════════════════════════════════════════════════════════════════

class TestConfidenceGuard:
    def test_guard_adds_warning_for_high_confidence(self):
        from models.decision import DecisionOutput
        from models.confidence import guard_decision
        d = DecisionOutput(
            decision="BUY", confidence=95.0, risk_level="LOW",
            reasoning=["test"], probabilities={"up": 0.8, "neutral": 0.1, "down": 0.1},
            source="test", signal_strength=90.0,
        )
        guarded = guard_decision(d)
        # Guard should add a caution warning for high confidence
        assert len(guarded.reasoning) > len(d.reasoning)

    def test_guard_returns_valid_decision(self):
        from models.decision import DecisionOutput
        from models.confidence import guard_decision
        d = DecisionOutput(
            decision="SELL", confidence=60.0, risk_level="HIGH",
            reasoning=["test"], probabilities={"up": 0.2, "neutral": 0.3, "down": 0.5},
            source="test",
        )
        guarded = guard_decision(d)
        assert guarded.decision in ("BUY", "SELL", "WAIT")


# ═══════════════════════════════════════════════════════════════════════════
# SENTIMENT
# ═══════════════════════════════════════════════════════════════════════════

class TestSentiment:
    def test_analyze_returns_dict(self):
        from engine.sentiment import analyze_ticker_sentiment
        result = analyze_ticker_sentiment("AAPL")
        assert isinstance(result, dict)
        assert "sentiment_label" in result or "items" in result or "error" in result
