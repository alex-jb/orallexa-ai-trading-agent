"""
tests/test_ml_rl_signals.py
────────────────────────────────────────────────────────────────────────────
Unit tests for the ML signal generator (engine/ml_signal.py)
and the RL trading agent (engine/rl_agent.py).

All tests use synthetic data — no yfinance or API calls.
Optional deps (stable_baselines3, gymnasium, xgboost) are skipped
gracefully via pytest.importorskip.
"""

import sys
import os

import numpy as np
import pandas as pd
import pytest

# Ensure project root is importable
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from engine.ml_signal import FEATURE_COLS, _make_features_labels, MLSignalGenerator
from engine.rl_agent import RL_FEATURES, RLTrader

# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def synthetic_df() -> pd.DataFrame:
    """200-row DataFrame with Close + all FEATURE_COLS, realistic ranges."""
    rng = np.random.RandomState(42)
    n = 200

    # Random-walk Close price starting at 100
    close = 100.0 + np.cumsum(rng.randn(n) * 0.5)

    data: dict = {"Close": close}

    # Moving averages — slight offsets from Close
    for ma in ("MA5", "MA10", "MA20", "MA50"):
        data[ma] = close + rng.randn(n) * 0.3

    # EMAs
    data["EMA12"] = close + rng.randn(n) * 0.2
    data["EMA26"] = close + rng.randn(n) * 0.3

    # MACD family
    data["MACD"] = rng.randn(n) * 0.5
    data["MACD_Signal"] = rng.randn(n) * 0.4
    data["MACD_Hist"] = data["MACD"] - data["MACD_Signal"]

    # Oscillators 0-100
    data["RSI"] = rng.uniform(20, 80, n)
    data["Stoch_K"] = rng.uniform(10, 90, n)
    data["Stoch_D"] = rng.uniform(10, 90, n)
    data["ROC"] = rng.randn(n) * 2

    # Bollinger
    data["BB_Pct"] = rng.uniform(-0.5, 1.5, n)
    data["BB_Width"] = rng.uniform(0.01, 0.1, n)

    # Volatility
    data["ATR_Pct"] = rng.uniform(0.005, 0.05, n)
    data["HV20"] = rng.uniform(0.1, 0.6, n)

    # Volume
    data["Volume_Ratio"] = rng.uniform(0.5, 3.0, n)
    data["OBV"] = np.cumsum(rng.randn(n) * 1e4)

    # ADX / DI
    data["ADX"] = rng.uniform(10, 60, n)
    data["Plus_DI"] = rng.uniform(5, 40, n)
    data["Minus_DI"] = rng.uniform(5, 40, n)

    # Binary flags
    data["Above_MA20"] = rng.choice([0, 1], n).astype(float)
    data["Above_MA50"] = rng.choice([0, 1], n).astype(float)
    data["MACD_Cross_Up"] = rng.choice([0, 1], n).astype(float)
    data["MACD_Cross_Down"] = rng.choice([0, 1], n).astype(float)
    data["RSI_Oversold"] = rng.choice([0, 1], n).astype(float)
    data["RSI_Overbought"] = rng.choice([0, 1], n).astype(float)

    df = pd.DataFrame(data, index=pd.date_range("2024-01-01", periods=n, freq="B"))
    return df


# ──────────────────────────────────────────────────────────────────────────
# ML Signal — _make_features_labels
# ──────────────────────────────────────────────────────────────────────────


class TestMakeFeaturesLabels:
    """Tests for _make_features_labels()."""

    def test_returns_tuple(self, synthetic_df: pd.DataFrame) -> None:
        result = _make_features_labels(synthetic_df, forward_days=5)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_types(self, synthetic_df: pd.DataFrame) -> None:
        X, y = _make_features_labels(synthetic_df, forward_days=5)
        assert isinstance(X, pd.DataFrame)
        assert isinstance(y, pd.Series)

    def test_shape_correct(self, synthetic_df: pd.DataFrame) -> None:
        forward_days = 5
        X, y = _make_features_labels(synthetic_df, forward_days=forward_days)

        # X rows <= len(df) - forward_days (NaN rows may also be dropped)
        assert len(X) <= len(synthetic_df) - forward_days
        assert len(X) == len(y)
        # X should have columns matching available FEATURE_COLS
        expected_cols = [c for c in FEATURE_COLS if c in synthetic_df.columns]
        assert list(X.columns) == expected_cols

    def test_y_binary(self, synthetic_df: pd.DataFrame) -> None:
        _, y = _make_features_labels(synthetic_df, forward_days=5)
        unique_vals = set(y.unique())
        assert unique_vals.issubset({0, 1}), f"y contains non-binary values: {unique_vals}"

    def test_no_nans_in_X(self, synthetic_df: pd.DataFrame) -> None:
        X, _ = _make_features_labels(synthetic_df, forward_days=5)
        assert not X.isna().any().any(), "X should have no NaN values after processing"

    def test_nan_rows_dropped(self) -> None:
        """Inject NaN in early rows and verify they are dropped."""
        rng = np.random.RandomState(99)
        n = 100
        close = 50.0 + np.cumsum(rng.randn(n) * 0.3)
        data = {"Close": close}
        # Only include a few feature cols
        for col in ("RSI", "MACD", "ADX"):
            vals = rng.randn(n)
            # First 10 rows are NaN
            vals[:10] = np.nan
            data[col] = vals

        df = pd.DataFrame(data, index=pd.date_range("2024-01-01", periods=n, freq="B"))
        X, y = _make_features_labels(df, forward_days=3)

        # The first 10 NaN rows should have been dropped
        assert len(X) <= n - 3 - 10 + 1  # at most this many rows remain
        assert not X.isna().any().any()

    def test_different_forward_days(self, synthetic_df: pd.DataFrame) -> None:
        for fd in (1, 3, 10):
            X, y = _make_features_labels(synthetic_df, forward_days=fd)
            assert len(X) <= len(synthetic_df) - fd
            assert len(X) == len(y)


# ──────────────────────────────────────────────────────────────────────────
# ML Signal — MLSignalGenerator init
# ──────────────────────────────────────────────────────────────────────────


class TestMLSignalGeneratorInit:
    """Tests for MLSignalGenerator construction."""

    def test_defaults(self, synthetic_df: pd.DataFrame) -> None:
        gen = MLSignalGenerator(
            train_df=synthetic_df.iloc[:150],
            test_df=synthetic_df.iloc[150:],
        )
        assert gen.forward_days == 5
        assert gen.tc == 0.002  # default transaction_cost + slippage
        assert gen.results == {}
        assert gen.models == {}

    def test_custom_params(self, synthetic_df: pd.DataFrame) -> None:
        gen = MLSignalGenerator(
            train_df=synthetic_df.iloc[:150],
            test_df=synthetic_df.iloc[150:],
            forward_days=3,
            transaction_cost=0.005,
            slippage=0.002,
            ticker="AAPL",
        )
        assert gen.forward_days == 3
        assert gen.tc == pytest.approx(0.007)
        assert gen._ticker == "AAPL"


# ──────────────────────────────────────────────────────────────────────────
# RL Agent — _build_env
# ──────────────────────────────────────────────────────────────────────────


class TestBuildEnv:
    """Tests for _build_env(). Requires gymnasium."""

    def test_returns_none_too_few_features(self) -> None:
        """If < 3 features are available, _build_env should return None."""
        gym = pytest.importorskip("gymnasium")
        from engine.rl_agent import _build_env

        # DataFrame with Close only — no RL feature columns
        df = pd.DataFrame({
            "Close": np.linspace(100, 110, 50),
        })
        result = _build_env(df, RL_FEATURES)
        assert result is None

    def test_returns_none_partial_features(self) -> None:
        """Two features available (< 3 threshold) returns None."""
        gym = pytest.importorskip("gymnasium")
        from engine.rl_agent import _build_env

        df = pd.DataFrame({
            "Close": np.linspace(100, 110, 50),
            "RSI": np.random.uniform(30, 70, 50),
            "MACD_Hist": np.random.randn(50),
        })
        result = _build_env(df, RL_FEATURES)
        assert result is None

    def test_returns_valid_env(self, synthetic_df: pd.DataFrame) -> None:
        """With enough features, env should be a valid gymnasium Env."""
        gym = pytest.importorskip("gymnasium")
        from engine.rl_agent import _build_env

        env = _build_env(synthetic_df, RL_FEATURES)
        assert env is not None
        assert hasattr(env, "observation_space")
        assert hasattr(env, "action_space")
        assert hasattr(env, "reset")
        assert hasattr(env, "step")

    def test_action_space(self, synthetic_df: pd.DataFrame) -> None:
        """Action space should be Discrete(3): hold, buy, sell."""
        gym = pytest.importorskip("gymnasium")
        from engine.rl_agent import _build_env

        env = _build_env(synthetic_df, RL_FEATURES)
        assert env is not None
        assert isinstance(env.action_space, gym.spaces.Discrete)
        assert env.action_space.n == 3

    def test_observation_space_shape(self, synthetic_df: pd.DataFrame) -> None:
        """Observation shape should be (window, n_available_features + 3)."""
        gym = pytest.importorskip("gymnasium")
        from engine.rl_agent import _build_env

        env = _build_env(synthetic_df, RL_FEATURES)
        assert env is not None

        available = [f for f in RL_FEATURES if f in synthetic_df.columns]
        expected_shape = (10, len(available) + 3)  # window=10, +3 for pos/pnl/dd
        assert env.observation_space.shape == expected_shape

    def test_reset_returns_obs(self, synthetic_df: pd.DataFrame) -> None:
        """reset() should return (obs, info) with correct shape."""
        gym = pytest.importorskip("gymnasium")
        from engine.rl_agent import _build_env

        env = _build_env(synthetic_df, RL_FEATURES)
        assert env is not None

        obs, info = env.reset()
        assert isinstance(obs, np.ndarray)
        assert obs.shape == env.observation_space.shape
        assert isinstance(info, dict)

    def test_step_returns_correct_tuple(self, synthetic_df: pd.DataFrame) -> None:
        """step() should return (obs, reward, done, truncated, info)."""
        gym = pytest.importorskip("gymnasium")
        from engine.rl_agent import _build_env

        env = _build_env(synthetic_df, RL_FEATURES)
        assert env is not None
        env.reset()

        obs, reward, done, truncated, info = env.step(0)  # hold
        assert isinstance(obs, np.ndarray)
        assert isinstance(reward, float)
        assert isinstance(done, bool)
        assert isinstance(truncated, bool)
        assert isinstance(info, dict)


# ──────────────────────────────────────────────────────────────────────────
# RL Agent — RLTrader
# ──────────────────────────────────────────────────────────────────────────


class TestRLTrader:
    """Tests for RLTrader class (no training — too slow for CI)."""

    def test_default_init(self) -> None:
        trader = RLTrader()
        assert trader.total_timesteps == 20000
        assert trader.model is None
        assert trader.features == RL_FEATURES
        assert trader.train_reward == 0.0

    def test_custom_timesteps(self) -> None:
        trader = RLTrader(total_timesteps=5000)
        assert trader.total_timesteps == 5000

    def test_predict_returns_none_untrained(self, synthetic_df: pd.DataFrame) -> None:
        """predict() should return None when model has not been trained."""
        trader = RLTrader()
        result = trader.predict(synthetic_df)
        assert result is None

    def test_model_none_before_training(self) -> None:
        trader = RLTrader(total_timesteps=10000)
        assert trader.model is None
