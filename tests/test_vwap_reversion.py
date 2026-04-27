"""Tests for the vwap_reversion strategy in engine/strategies.py."""
import numpy as np
import pandas as pd
import pytest

from engine.strategies import (
    STRATEGY_DEFAULT_PARAMS,
    STRATEGY_DESCRIPTIONS,
    STRATEGY_REGISTRY,
    vwap_reversion,
)


def _make_ohlcv(n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0.1, 1.0, n))
    return pd.DataFrame(
        {
            "Open": close * (1 + rng.normal(0, 0.003, n)),
            "High": close * (1 + abs(rng.normal(0, 0.01, n))),
            "Low": close * (1 - abs(rng.normal(0, 0.01, n))),
            "Close": close,
            "Volume": rng.integers(1_000_000, 5_000_000, n),
        },
        index=pd.bdate_range("2024-01-01", periods=n),
    )


class TestVwapReversionRegistry:
    def test_registered(self):
        assert "vwap_reversion" in STRATEGY_REGISTRY
        assert STRATEGY_REGISTRY["vwap_reversion"] is vwap_reversion

    def test_has_defaults(self):
        defaults = STRATEGY_DEFAULT_PARAMS["vwap_reversion"]
        assert defaults["threshold"] == 0.01
        assert defaults["rsi_oversold"] == 35
        assert defaults["rsi_overbought"] == 65

    def test_has_description(self):
        assert "vwap_reversion" in STRATEGY_DESCRIPTIONS


class TestVwapReversionShape:
    def test_returns_series_of_correct_length(self):
        df = _make_ohlcv()
        result = vwap_reversion(df, STRATEGY_DEFAULT_PARAMS["vwap_reversion"])
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)

    def test_signals_are_in_set(self):
        df = _make_ohlcv()
        result = vwap_reversion(df, STRATEGY_DEFAULT_PARAMS["vwap_reversion"])
        assert set(result.unique()).issubset({-1, 0, 1})

    def test_default_no_rsi_emits_no_signals(self):
        # Without an RSI column the strategy assumes RSI=50, which sits inside
        # both gates → no BUY/SELL. This guards against false fires when the
        # indicator pipeline hasn't run yet.
        df = _make_ohlcv()
        result = vwap_reversion(df, STRATEGY_DEFAULT_PARAMS["vwap_reversion"])
        assert (result == 0).all()


class TestVwapReversionSignals:
    def _df_with_rsi(self, close, rsi, volume=1_000_000):
        n = len(close)
        df = pd.DataFrame(
            {
                "Open": close,
                "High": [c * 1.001 for c in close],
                "Low": [c * 0.999 for c in close],
                "Close": close,
                "Volume": [volume] * n,
                "RSI": rsi,
            },
            index=pd.bdate_range("2024-01-01", periods=n),
        )
        return df

    def test_buy_signal_when_below_vwap_and_rsi_oversold(self):
        # Stable prices around 100 → VWAP ~100. Drop close to 98 with RSI 25
        # on the last bar → expect +1.
        close = [100.0] * 20 + [98.0]
        rsi = [50.0] * 20 + [25.0]
        df = self._df_with_rsi(close, rsi)
        result = vwap_reversion(df, {"threshold": 0.01, "rsi_oversold": 35, "rsi_overbought": 65})
        assert result.iloc[-1] == 1

    def test_sell_signal_when_above_vwap_and_rsi_overbought(self):
        close = [100.0] * 20 + [102.0]
        rsi = [50.0] * 20 + [75.0]
        df = self._df_with_rsi(close, rsi)
        result = vwap_reversion(df, {"threshold": 0.01, "rsi_oversold": 35, "rsi_overbought": 65})
        assert result.iloc[-1] == -1

    def test_no_signal_when_rsi_neutral_even_if_far_from_vwap(self):
        close = [100.0] * 20 + [98.0]
        rsi = [50.0] * 21  # neutral RSI, no fire
        df = self._df_with_rsi(close, rsi)
        result = vwap_reversion(df, {"threshold": 0.01, "rsi_oversold": 35, "rsi_overbought": 65})
        assert result.iloc[-1] == 0

    def test_no_signal_inside_threshold_band(self):
        close = [100.0] * 20 + [99.95]  # 0.05% below VWAP, inside 1% band
        rsi = [50.0] * 20 + [20.0]      # RSI extreme, but band gate blocks
        df = self._df_with_rsi(close, rsi)
        result = vwap_reversion(df, {"threshold": 0.01, "rsi_oversold": 35, "rsi_overbought": 65})
        assert result.iloc[-1] == 0


class TestVwapReversionEdgeCases:
    def test_uses_existing_vwap_column_when_present(self):
        # Force a SELL by pinning VWAP below close and RSI overbought.
        n = 5
        df = pd.DataFrame(
            {
                "Open": [100.0] * n,
                "High": [101.0] * n,
                "Low": [99.0] * n,
                "Close": [105.0] * n,
                "Volume": [1_000_000] * n,
                "VWAP": [100.0] * n,
                "RSI": [80.0] * n,
            },
            index=pd.bdate_range("2024-01-01", periods=n),
        )
        result = vwap_reversion(df, STRATEGY_DEFAULT_PARAMS["vwap_reversion"])
        assert (result == -1).all()

    def test_zero_volume_does_not_crash(self):
        n = 10
        df = pd.DataFrame(
            {
                "Open": [100.0] * n,
                "High": [101.0] * n,
                "Low": [99.0] * n,
                "Close": [100.0] * n,
                "Volume": [0] * n,
                "RSI": [50.0] * n,
            },
            index=pd.bdate_range("2024-01-01", periods=n),
        )
        result = vwap_reversion(df, STRATEGY_DEFAULT_PARAMS["vwap_reversion"])
        # Zero volume → VWAP is NaN → strategy must clamp to 0, not raise.
        assert (result == 0).all()

    def test_missing_required_column_raises(self):
        df = pd.DataFrame({"Close": [100.0, 101.0]})
        with pytest.raises(ValueError, match="vwap_reversion"):
            vwap_reversion(df, STRATEGY_DEFAULT_PARAMS["vwap_reversion"])
