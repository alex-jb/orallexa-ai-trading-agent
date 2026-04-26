"""
tests/test_kronos_signal.py
──────────────────────────────────────────────────────────────────
Tests for engine/kronos_signal.py — lazy import + score conversion.

Kronos itself is NOT installed in CI (heavy DL deps). We inject a
fake `model` module to exercise the integration shape end-to-end.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.kronos_signal import KronosSignal


def _ohlcv(n: int = 100, drift: float = 0.0):
    """Synthetic OHLCV with optional drift in close."""
    rng = np.random.default_rng(42)
    close = 100.0 + np.cumsum(rng.normal(drift, 0.5, n))
    return pd.DataFrame({
        "open":  close + rng.normal(0, 0.1, n),
        "high":  close + np.abs(rng.normal(0.3, 0.1, n)),
        "low":   close - np.abs(rng.normal(0.3, 0.1, n)),
        "close": close,
        "volume": np.abs(rng.normal(1_000_000, 100_000, n)),
        "amount": np.abs(rng.normal(100_000_000, 10_000_000, n)),
    }, index=pd.date_range("2024-01-01", periods=n))


def _install_fake_kronos(forecast_df: pd.DataFrame):
    """
    Inject sys.modules['model'] with stand-ins for Kronos /
    KronosTokenizer / KronosPredictor. Returns the fake module.
    """
    import engine.kronos_signal as ks

    fake = types.ModuleType("model")

    class FakeTokenizer:
        @classmethod
        def from_pretrained(cls, name):
            return cls()
    fake.KronosTokenizer = FakeTokenizer

    class FakeModel:
        @classmethod
        def from_pretrained(cls, name):
            return cls()
    fake.Kronos = FakeModel

    class FakePredictor:
        def __init__(self, model, tokenizer, max_context=512):
            pass

        def predict(self, *, df, x_timestamp, y_timestamp, pred_len, T=1.0, top_p=0.9):
            return forecast_df.head(pred_len)

    fake.KronosPredictor = FakePredictor
    sys.modules["model"] = fake

    # Reset module-level cache so each test sees a clean state
    ks._cached_predictor = None
    ks._cached_size = None
    return fake


# ── Lazy import error ──────────────────────────────────────────────────────


class TestLazyImport:
    def test_missing_kronos_raises_clear_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "model", None)
        import engine.kronos_signal as ks
        ks._cached_predictor = None
        ks._cached_size = None
        sig = KronosSignal()
        with pytest.raises(RuntimeError, match="Kronos not installed"):
            from engine.kronos_signal import _ensure_kronos
            _ensure_kronos()


# ── Predict happy path ─────────────────────────────────────────────────────


class TestPredict:
    def test_returns_forecast_dataframe(self):
        forecast = pd.DataFrame({
            "open":  [105, 106, 107],
            "high":  [105.5, 106.5, 107.5],
            "low":   [104.5, 105.5, 106.5],
            "close": [105.2, 106.2, 107.2],
        })
        _install_fake_kronos(forecast)
        sig = KronosSignal(lookback=64)
        out = sig.predict(_ohlcv(100), pred_len=3)
        assert out is not None
        assert len(out) == 3
        assert out["close"].iloc[-1] == 107.2

    def test_short_history_returns_none(self):
        sig = KronosSignal(lookback=64)
        out = sig.predict(_ohlcv(20), pred_len=5)
        assert out is None

    def test_missing_close_column_returns_none(self):
        df = pd.DataFrame({"junk": [1, 2, 3]})
        _install_fake_kronos(pd.DataFrame())
        sig = KronosSignal(lookback=2)
        out = sig.predict(df, pred_len=1)
        assert out is None

    def test_predictor_exception_returns_none(self):
        _install_fake_kronos(pd.DataFrame())
        # Patch the cached predictor to throw
        import engine.kronos_signal as ks
        ks._cached_predictor = MagicMock()
        ks._cached_predictor.predict = MagicMock(side_effect=RuntimeError("model err"))
        ks._cached_size = "small"
        sig = KronosSignal(lookback=64)
        out = sig.predict(_ohlcv(100), pred_len=5)
        assert out is None


# ── score_for_fusion ───────────────────────────────────────────────────────


class TestScoreForFusion:
    def test_bullish_forecast_positive_score(self):
        # Forecast climbs strongly above current
        forecast = pd.DataFrame({
            "open":  [105, 106, 107, 108, 109],
            "high":  [106, 107, 108, 109, 110],
            "low":   [104, 105, 106, 107, 108],
            "close": [105, 106, 107, 108, 109],
        })
        _install_fake_kronos(forecast)
        sig = KronosSignal(lookback=64)
        df = _ohlcv(100)
        df["close"] = 100.0  # deterministic current
        out = sig.score_for_fusion(df, pred_len=5)
        assert out["available"] is True
        assert out["score"] > 0
        assert out["expected_return_pct"] > 0

    def test_bearish_forecast_negative_score(self):
        forecast = pd.DataFrame({
            "open":  [95, 94, 93, 92, 91],
            "high":  [96, 95, 94, 93, 92],
            "low":   [94, 93, 92, 91, 90],
            "close": [95, 94, 93, 92, 91],
        })
        _install_fake_kronos(forecast)
        sig = KronosSignal(lookback=64)
        df = _ohlcv(100)
        df["close"] = 100.0
        out = sig.score_for_fusion(df, pred_len=5)
        assert out["available"] is True
        assert out["score"] < 0

    def test_short_history_unavailable(self):
        sig = KronosSignal(lookback=64)
        out = sig.score_for_fusion(_ohlcv(20), pred_len=5)
        assert out["available"] is False
        assert out["score"] == 0
