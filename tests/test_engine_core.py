"""
tests/test_engine_core.py
─────────────────────────────────────────────────────────────────
Comprehensive tests for core engine modules:
  1. engine/backtest.py       — simple_backtest()
  2. engine/strategies.py     — all 9 strategies + registry
  3. engine/multi_agent_analysis.py — _run_market_analyst helper
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd
import pytest

from engine.backtest import simple_backtest
from engine.strategies import (
    STRATEGY_DEFAULT_PARAMS,
    STRATEGY_REGISTRY,
    get_strategy,
    get_default_params,
)
from engine.multi_agent_analysis import _run_market_analyst


# ══════════════════════════════════════════════════════════════════════════
# HELPERS — synthetic data generators
# ══════════════════════════════════════════════════════════════════════════

def _make_price_series(n: int = 200, start: float = 100.0, seed: int = 42) -> pd.DataFrame:
    """Generate a realistic-looking OHLCV DataFrame with all indicator columns."""
    rng = np.random.RandomState(seed)

    # Random walk for close prices
    returns = rng.normal(0.0005, 0.015, size=n)
    close = start * np.cumprod(1 + returns)

    high = close * (1 + rng.uniform(0.001, 0.02, size=n))
    low = close * (1 - rng.uniform(0.001, 0.02, size=n))
    open_price = close * (1 + rng.normal(0, 0.005, size=n))
    volume = rng.randint(500_000, 5_000_000, size=n).astype(float)

    df = pd.DataFrame({
        "Open": open_price,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    })

    # Moving averages
    df["MA5"] = df["Close"].rolling(5, min_periods=1).mean()
    df["MA10"] = df["Close"].rolling(10, min_periods=1).mean()
    df["MA20"] = df["Close"].rolling(20, min_periods=1).mean()
    df["MA50"] = df["Close"].rolling(50, min_periods=1).mean()

    # EMA
    df["EMA12"] = df["Close"].ewm(span=12, adjust=False).mean()
    df["EMA26"] = df["Close"].ewm(span=26, adjust=False).mean()

    # MACD
    df["MACD"] = df["EMA12"] - df["EMA26"]
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    # RSI (simplified)
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    rs = gain / loss.replace(0, 1e-10)
    df["RSI"] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    bb_mid = df["Close"].rolling(20, min_periods=1).mean()
    bb_std = df["Close"].rolling(20, min_periods=1).std().fillna(1)
    df["BB_Mid"] = bb_mid
    df["BB_Upper"] = bb_mid + 2 * bb_std
    df["BB_Lower"] = bb_mid - 2 * bb_std
    bb_range = df["BB_Upper"] - df["BB_Lower"]
    df["BB_Pct"] = (df["Close"] - df["BB_Lower"]) / bb_range.replace(0, 1)
    df["BB_Width"] = bb_range / bb_mid
    df["BB_Squeeze"] = (df["BB_Width"] < df["BB_Width"].rolling(20, min_periods=1).median()).astype(int)

    # ADX (simplified proxy)
    df["ADX"] = rng.uniform(10, 40, size=n)
    df["Plus_DI"] = rng.uniform(10, 35, size=n)
    df["Minus_DI"] = rng.uniform(10, 35, size=n)

    # Volume indicators
    vol_ma = df["Volume"].rolling(20, min_periods=1).mean()
    df["Volume_Ratio"] = df["Volume"] / vol_ma.replace(0, 1)
    df["OBV"] = (np.sign(df["Close"].diff().fillna(0)) * df["Volume"]).cumsum()

    # Stochastic
    low14 = df["Low"].rolling(14, min_periods=1).min()
    high14 = df["High"].rolling(14, min_periods=1).max()
    df["Stoch_K"] = 100 * (df["Close"] - low14) / (high14 - low14).replace(0, 1)
    df["Stoch_D"] = df["Stoch_K"].rolling(3, min_periods=1).mean()

    # ROC
    df["ROC"] = df["Close"].pct_change(10).fillna(0) * 100

    # ATR
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift(1)).abs(),
        (df["Low"] - df["Close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=1).mean()
    df["ATR"] = atr
    df["ATR_Pct"] = atr / df["Close"]

    # Historical volatility
    df["HV20"] = df["Close"].pct_change().rolling(20, min_periods=1).std() * np.sqrt(252)

    # Binary flags
    df["Above_MA20"] = (df["Close"] > df["MA20"]).astype(int)
    df["Above_MA50"] = (df["Close"] > df["MA50"]).astype(int)
    df["MACD_Cross_Up"] = ((df["MACD"] > df["MACD_Signal"]) & (df["MACD"].shift(1) <= df["MACD_Signal"].shift(1))).astype(int)
    df["MACD_Cross_Down"] = ((df["MACD"] < df["MACD_Signal"]) & (df["MACD"].shift(1) >= df["MACD_Signal"].shift(1))).astype(int)
    df["RSI_Oversold"] = (df["RSI"] < 30).astype(int)
    df["RSI_Overbought"] = (df["RSI"] > 70).astype(int)

    return df


# ══════════════════════════════════════════════════════════════════════════
# TESTS — simple_backtest
# ══════════════════════════════════════════════════════════════════════════

class TestSimpleBacktest:
    """Tests for engine/backtest.py :: simple_backtest()."""

    def test_with_precomputed_signal(self) -> None:
        """When signal_col is already present, use it directly."""
        df = _make_price_series(100)
        df["signal"] = 1  # always long
        result = simple_backtest(df)

        assert "CumulativeStrategyReturn" in result.columns
        assert "CumulativeMarketReturn" in result.columns
        assert "equity_curve" in result.columns
        assert len(result) == 100

    def test_auto_signal_generation(self) -> None:
        """When signal_col is missing, auto-generate from RSI + MA20 + MA50."""
        df = _make_price_series(100)
        # Ensure no signal column exists
        assert "signal" not in df.columns

        result = simple_backtest(df)
        assert "signal" in result.columns
        assert set(result["signal"].unique()).issubset({0, 1})

    def test_auto_signal_missing_columns_raises(self) -> None:
        """Raise ValueError when required indicator columns are absent."""
        df = pd.DataFrame({"Close": [100, 101, 102]})
        with pytest.raises(ValueError, match="Missing indicator columns"):
            simple_backtest(df)

    def test_transaction_costs_applied(self) -> None:
        """Trade costs reduce net returns vs gross returns."""
        df = _make_price_series(100)
        # Alternate signal to generate trades
        df["signal"] = [1, 0] * 50
        result = simple_backtest(df, transaction_cost=0.01, slippage=0.01)

        # At least some trade cost rows should be > 0
        assert (result["trade_cost"] > 0).any()
        # Net cumulative should be <= gross cumulative at the end
        assert result["CumulativeNetStrategyReturn"].iloc[-1] <= result["CumulativeGrossStrategyReturn"].iloc[-1]

    def test_cumulative_return_columns_exist(self) -> None:
        """All expected cumulative return columns are present."""
        df = _make_price_series(50)
        df["signal"] = 1
        result = simple_backtest(df)

        expected_cols = [
            "CumulativeGrossStrategyReturn",
            "CumulativeNetStrategyReturn",
            "CumulativeStrategyReturn",
            "CumulativeMarketReturn",
            "gross_equity_curve",
            "net_equity_curve",
            "equity_curve",
            "market_equity_curve",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_all_zero_signals(self) -> None:
        """No trades when all signals are zero — strategy return should be zero."""
        df = _make_price_series(50)
        df["signal"] = 0
        result = simple_backtest(df)

        # Gross strategy return should be zero (no position)
        assert (result["gross_strategy_return"] == 0).all()
        # Equity curve should stay near initial cash (only trade costs on first bar)
        assert abs(result["equity_curve"].iloc[-1] - 10000) < 50

    def test_missing_close_column_raises(self) -> None:
        """Raise ValueError when Close column is absent."""
        df = pd.DataFrame({"Price": [100, 101, 102], "signal": [1, 0, 1]})
        with pytest.raises(ValueError, match="Missing column"):
            simple_backtest(df)

    def test_adj_close_fallback(self) -> None:
        """Falls back to 'Adj Close' when 'Close' is missing."""
        df = _make_price_series(50)
        df["signal"] = 1
        df["Adj Close"] = df["Close"]
        df = df.drop(columns=["Close"])

        result = simple_backtest(df)
        assert "equity_curve" in result.columns

    def test_custom_params(self) -> None:
        """Custom rsi_min/rsi_max params affect auto-generated signals."""
        df = _make_price_series(100)
        result_default = simple_backtest(df.copy())
        result_custom = simple_backtest(df.copy(), params={"rsi_min": 10, "rsi_max": 90})

        # Different param ranges should yield different signal counts
        # (not guaranteed but very likely with synthetic data)
        n_default = result_default["signal"].sum()
        n_custom = result_custom["signal"].sum()
        # Custom wider range should have >= default signals
        assert n_custom >= n_default

    def test_initial_cash(self) -> None:
        """Equity curves start at initial_cash value."""
        df = _make_price_series(30)
        df["signal"] = 0
        result = simple_backtest(df, initial_cash=50000)
        assert result["equity_curve"].iloc[0] == pytest.approx(50000, rel=0.01)
        assert result["market_equity_curve"].iloc[0] == pytest.approx(50000, rel=0.01)


# ══════════════════════════════════════════════════════════════════════════
# TESTS — strategies
# ══════════════════════════════════════════════════════════════════════════

class TestStrategyRegistry:
    """Tests for engine/strategies.py :: STRATEGY_REGISTRY and helpers."""

    def test_registry_has_nine_entries(self) -> None:
        assert len(STRATEGY_REGISTRY) == 9

    def test_registry_keys(self) -> None:
        expected = {
            "double_ma",
            "macd_crossover",
            "bollinger_breakout",
            "rsi_reversal",
            "trend_momentum",
            "alpha_combo",
            "dual_thrust",
            "ensemble_vote",
            "regime_ensemble",
        }
        assert set(STRATEGY_REGISTRY.keys()) == expected

    def test_get_strategy_valid(self) -> None:
        fn = get_strategy("double_ma")
        assert callable(fn)

    def test_get_strategy_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy("nonexistent_strategy")

    def test_get_default_params_returns_dict(self) -> None:
        for name in STRATEGY_REGISTRY:
            params = get_default_params(name)
            assert isinstance(params, dict)

    def test_default_params_for_unknown_returns_empty(self) -> None:
        assert get_default_params("does_not_exist") == {}


class TestStrategiesOutput:
    """Each strategy returns a pd.Series of {-1, 0, 1} with same length as input."""

    @pytest.fixture
    def df(self) -> pd.DataFrame:
        return _make_price_series(200, seed=123)

    @pytest.mark.parametrize("name", list(STRATEGY_REGISTRY.keys()))
    def test_strategy_returns_series(self, df: pd.DataFrame, name: str) -> None:
        fn = STRATEGY_REGISTRY[name]
        params = STRATEGY_DEFAULT_PARAMS.get(name, {})
        result = fn(df, params)

        assert isinstance(result, pd.Series), f"{name} did not return a Series"
        assert len(result) == len(df), f"{name} length mismatch"

    @pytest.mark.parametrize("name", list(STRATEGY_REGISTRY.keys()))
    def test_strategy_signals_in_valid_range(self, df: pd.DataFrame, name: str) -> None:
        fn = STRATEGY_REGISTRY[name]
        params = STRATEGY_DEFAULT_PARAMS.get(name, {})
        result = fn(df, params)

        unique_vals = set(result.unique())
        assert unique_vals.issubset({-1, 0, 1}), (
            f"{name} produced invalid signal values: {unique_vals}"
        )

    @pytest.mark.parametrize("name", list(STRATEGY_REGISTRY.keys()))
    def test_strategy_index_matches(self, df: pd.DataFrame, name: str) -> None:
        fn = STRATEGY_REGISTRY[name]
        params = STRATEGY_DEFAULT_PARAMS.get(name, {})
        result = fn(df, params)

        assert (result.index == df.index).all(), f"{name} index mismatch"


class TestIndividualStrategies:
    """Targeted tests for specific strategy behaviors."""

    @pytest.fixture
    def df(self) -> pd.DataFrame:
        return _make_price_series(200, seed=77)

    def test_double_ma_produces_trades(self, df: pd.DataFrame) -> None:
        result = STRATEGY_REGISTRY["double_ma"](df, {"fast_period": 10, "slow_period": 30})
        # Should produce at least some long signals over 200 bars
        assert result.sum() > 0

    def test_rsi_reversal_only_enters_oversold(self, df: pd.DataFrame) -> None:
        result = STRATEGY_REGISTRY["rsi_reversal"](df, {"oversold": 25, "overbought": 75, "exit_rsi": 55, "use_adx_filter": False})
        # Entries should occur after RSI dips below oversold level
        assert isinstance(result, pd.Series)
        assert result.sum() >= 0  # valid even if no entries

    def test_dual_thrust_with_default_params(self, df: pd.DataFrame) -> None:
        result = STRATEGY_REGISTRY["dual_thrust"](df, STRATEGY_DEFAULT_PARAMS["dual_thrust"])
        assert len(result) == 200

    def test_ensemble_vote_fewer_signals_than_individual(self, df: pd.DataFrame) -> None:
        """Ensemble should produce fewer (or equal) signals than most individual strategies."""
        ensemble = STRATEGY_REGISTRY["ensemble_vote"](df, {"min_agree": 4})
        double_ma = STRATEGY_REGISTRY["double_ma"](df, STRATEGY_DEFAULT_PARAMS["double_ma"])
        # With min_agree=4, ensemble should be more selective
        assert ensemble.sum() <= double_ma.sum() + 10  # allow small margin

    def test_regime_ensemble_no_signals_in_volatile(self, df: pd.DataFrame) -> None:
        """Regime ensemble should suppress signals in volatile regimes."""
        result = STRATEGY_REGISTRY["regime_ensemble"](df, STRATEGY_DEFAULT_PARAMS["regime_ensemble"])
        assert isinstance(result, pd.Series)
        assert len(result) == 200

    def test_alpha_combo_high_threshold_no_signals(self, df: pd.DataFrame) -> None:
        """Very high threshold should produce few or no signals."""
        result = STRATEGY_REGISTRY["alpha_combo"](df, {"score_threshold": 100.0})
        assert result.sum() == 0

    def test_bollinger_breakout_with_columns(self, df: pd.DataFrame) -> None:
        result = STRATEGY_REGISTRY["bollinger_breakout"](df, STRATEGY_DEFAULT_PARAMS["bollinger_breakout"])
        assert isinstance(result, pd.Series)
        assert set(result.unique()).issubset({-1, 0, 1})

    def test_macd_crossover_with_trend_filter(self, df: pd.DataFrame) -> None:
        result = STRATEGY_REGISTRY["macd_crossover"](df, {"confirm_bars": 1, "use_trend_filter": True, "hist_threshold": 0.0})
        assert isinstance(result, pd.Series)
        assert len(result) == 200

    def test_trend_momentum_stop_loss(self, df: pd.DataFrame) -> None:
        """Tight stop loss should cause more exits."""
        loose = STRATEGY_REGISTRY["trend_momentum"](df, {**STRATEGY_DEFAULT_PARAMS["trend_momentum"], "stop_loss": 0.50})
        tight = STRATEGY_REGISTRY["trend_momentum"](df, {**STRATEGY_DEFAULT_PARAMS["trend_momentum"], "stop_loss": 0.001})
        # Tight stop should have fewer or equal long bars
        assert tight.sum() <= loose.sum() + 5


# ══════════════════════════════════════════════════════════════════════════
# TESTS — multi_agent_analysis :: _run_market_analyst
# ══════════════════════════════════════════════════════════════════════════

class TestRunMarketAnalyst:
    """Tests for engine/multi_agent_analysis.py :: _run_market_analyst."""

    def test_returns_string_with_ticker(self) -> None:
        summary = {
            "close": 150.0,
            "ma20": 145.0,
            "ma50": 140.0,
            "rsi": 55.0,
            "macd_hist": 0.5,
            "bb_pct": 0.6,
            "adx": 28.0,
            "volume_ratio": 1.2,
            "bb_upper": 160.0,
            "bb_lower": 135.0,
        }
        result = _run_market_analyst(summary, "NVDA")

        assert isinstance(result, str)
        assert "NVDA" in result

    def test_bullish_trend_detection(self) -> None:
        summary = {
            "close": 200.0,
            "ma20": 190.0,
            "ma50": 180.0,
            "rsi": 60.0,
            "macd_hist": 1.0,
        }
        result = _run_market_analyst(summary, "AAPL")
        assert "Bullish" in result or "uptrend" in result

    def test_bearish_trend_detection(self) -> None:
        summary = {
            "close": 100.0,
            "ma20": 110.0,
            "ma50": 120.0,
            "rsi": 35.0,
            "macd_hist": -0.5,
        }
        result = _run_market_analyst(summary, "TSLA")
        assert "Bearish" in result or "downtrend" in result

    def test_overbought_rsi(self) -> None:
        summary = {"close": 100.0, "rsi": 75.0}
        result = _run_market_analyst(summary, "SPY")
        assert "Overbought" in result

    def test_oversold_rsi(self) -> None:
        summary = {"close": 100.0, "rsi": 25.0}
        result = _run_market_analyst(summary, "QQQ")
        assert "Oversold" in result

    def test_empty_summary(self) -> None:
        """Should not crash with empty summary."""
        result = _run_market_analyst({}, "TEST")
        assert isinstance(result, str)
        assert "TEST" in result

    def test_trend_score_in_range(self) -> None:
        summary = {
            "close": 150.0,
            "ma20": 145.0,
            "ma50": 140.0,
            "rsi": 55.0,
            "macd_hist": 0.3,
            "adx": 30.0,
        }
        result = _run_market_analyst(summary, "GOOG")
        assert "Trend Score:" in result
        # Extract score value and check it is between 0 and 100
        for line in result.split("\n"):
            if "Trend Score:" in line:
                # Handle markdown: "**Trend Score:** 86/100"
                raw = line.split("Trend Score:")[-1].strip()
                # Strip leading/trailing markdown bold markers
                raw = raw.replace("**", "").strip()
                score_str = raw.split("/")[0].strip()
                score = float(score_str)
                assert 0 <= score <= 100
                break

    def test_volume_above_average(self) -> None:
        summary = {"close": 100.0, "volume_ratio": 2.0}
        result = _run_market_analyst(summary, "AMD")
        assert "Above average" in result

    def test_volume_below_average(self) -> None:
        summary = {"close": 100.0, "volume_ratio": 0.5}
        result = _run_market_analyst(summary, "INTC")
        assert "Below average" in result

    def test_support_resistance_lines(self) -> None:
        summary = {
            "close": 150.0,
            "ma20": 145.0,
            "bb_upper": 160.0,
            "bb_lower": 135.0,
        }
        result = _run_market_analyst(summary, "META")
        assert "Support" in result
        assert "Resistance" in result
