"""
tests/test_chart_render.py
──────────────────────────────────────────────────────────────────
Unit tests for engine/chart_render.py — pure rendering, no network.

mplfinance is required for these tests; importorskip when it's not
available (mplfinance is in requirements.txt but a contributor running
a slim env may not have it).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

mpf = pytest.importorskip("mplfinance")


@pytest.fixture
def synthetic_ohlcv(n=40):
    """Deterministic OHLCV frame, mplfinance-shaped."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0.2, 1.0, n))
    return pd.DataFrame(
        {
            "Open":   close * (1 + rng.normal(0, 0.003, n)),
            "High":   close * (1 + abs(rng.normal(0, 0.01, n))),
            "Low":    close * (1 - abs(rng.normal(0, 0.01, n))),
            "Close":  close,
            "Volume": rng.integers(1_000_000, 5_000_000, n),
        },
        index=pd.bdate_range("2026-01-01", periods=n),
    )


# ── render_kline core ─────────────────────────────────────────────────────


class TestRenderKline:
    def test_returns_png_bytes(self, synthetic_ohlcv):
        from engine.chart_render import render_kline
        png = render_kline(synthetic_ohlcv, ticker="TEST")
        assert isinstance(png, bytes)
        # PNG signature: 89 50 4E 47 0D 0A 1A 0A
        assert png.startswith(b"\x89PNG\r\n\x1a\n")

    def test_size_is_reasonable(self, synthetic_ohlcv):
        """Vision API rejects >5MB images; we expect ~50-200KB."""
        from engine.chart_render import render_kline
        png = render_kline(synthetic_ohlcv, ticker="TEST")
        assert 10_000 < len(png) < 500_000

    def test_missing_columns_raises(self):
        import pandas as pd
        bad = pd.DataFrame({"Close": [1, 2, 3]})
        from engine.chart_render import render_kline
        with pytest.raises(ValueError, match="missing required OHLCV"):
            render_kline(bad)

    def test_empty_dataframe_raises(self):
        import pandas as pd
        empty = pd.DataFrame(
            columns=["Open", "High", "Low", "Close", "Volume"]
        )
        from engine.chart_render import render_kline
        with pytest.raises(ValueError, match="empty DataFrame"):
            render_kline(empty)

    def test_volume_off(self, synthetic_ohlcv):
        from engine.chart_render import render_kline
        # Just shouldn't crash with show_volume=False.
        png = render_kline(synthetic_ohlcv, show_volume=False)
        assert png.startswith(b"\x89PNG")

    def test_no_ma_overlay(self, synthetic_ohlcv):
        from engine.chart_render import render_kline
        png = render_kline(synthetic_ohlcv, mavs=())
        assert png.startswith(b"\x89PNG")

    def test_extra_columns_are_ignored(self, synthetic_ohlcv):
        # Cached frames often have indicator columns added (RSI, MACD, etc).
        # The renderer should silently drop them, not crash.
        df = synthetic_ohlcv.copy()
        df["RSI"] = 50.0
        df["MACD_Hist"] = 0.1
        from engine.chart_render import render_kline
        png = render_kline(df)
        assert png.startswith(b"\x89PNG")

    def test_deterministic_output(self, synthetic_ohlcv):
        """Same DataFrame → identical PNG bytes (matters for A/B testing)."""
        from engine.chart_render import render_kline
        a = render_kline(synthetic_ohlcv, ticker="X")
        b = render_kline(synthetic_ohlcv, ticker="X")
        assert a == b


# ── render_kline_for (cache + yfinance fallback) ──────────────────────────


class TestRenderKlineFor:
    def test_uses_cache_when_enabled(self, synthetic_ohlcv, monkeypatch):
        # Build a stub cache that returns our synthetic frame.
        import engine.historical_cache as hc
        fake_cache = MagicMock()
        fake_cache.get_prices_by_period.return_value = synthetic_ohlcv
        monkeypatch.setattr(hc, "_DEFAULT_INSTANCE", fake_cache)
        monkeypatch.setenv("ORALLEXA_USE_CACHE", "1")

        from engine.chart_render import render_kline_for
        with patch("yfinance.Ticker") as mock_yf:
            png = render_kline_for("NVDA", period="3mo")
            assert mock_yf.call_count == 0  # cache hit, no yfinance call
        assert png is not None and png.startswith(b"\x89PNG")

    def test_falls_through_to_yfinance(self, synthetic_ohlcv, monkeypatch):
        monkeypatch.delenv("ORALLEXA_USE_CACHE", raising=False)
        fake_ticker = MagicMock()
        fake_ticker.history.return_value = synthetic_ohlcv
        from engine.chart_render import render_kline_for
        with patch("yfinance.Ticker", return_value=fake_ticker):
            png = render_kline_for("NVDA", period="3mo")
        assert png is not None and png.startswith(b"\x89PNG")
        assert fake_ticker.history.called

    def test_returns_none_on_empty_data(self, monkeypatch):
        import pandas as pd
        monkeypatch.delenv("ORALLEXA_USE_CACHE", raising=False)
        fake_ticker = MagicMock()
        fake_ticker.history.return_value = pd.DataFrame()
        from engine.chart_render import render_kline_for
        with patch("yfinance.Ticker", return_value=fake_ticker):
            assert render_kline_for("XYZ") is None

    def test_returns_none_on_yfinance_exception(self, monkeypatch):
        monkeypatch.delenv("ORALLEXA_USE_CACHE", raising=False)
        from engine.chart_render import render_kline_for
        with patch("yfinance.Ticker", side_effect=RuntimeError("net")):
            assert render_kline_for("XYZ") is None

    def test_use_cache_kwarg_overrides_env(self, synthetic_ohlcv, monkeypatch):
        # use_cache=False should bypass cache even if env says on.
        monkeypatch.setenv("ORALLEXA_USE_CACHE", "1")
        import engine.historical_cache as hc
        fake_cache = MagicMock()
        fake_cache.get_prices_by_period.side_effect = AssertionError(
            "should not consult cache when use_cache=False"
        )
        monkeypatch.setattr(hc, "_DEFAULT_INSTANCE", fake_cache)

        fake_ticker = MagicMock()
        fake_ticker.history.return_value = synthetic_ohlcv
        from engine.chart_render import render_kline_for
        with patch("yfinance.Ticker", return_value=fake_ticker):
            png = render_kline_for("NVDA", period="3mo", use_cache=False)
        assert png is not None


# ── save_kline_to ─────────────────────────────────────────────────────────


class TestSaveKlineTo:
    def test_writes_png_file(self, tmp_path, synthetic_ohlcv, monkeypatch):
        monkeypatch.delenv("ORALLEXA_USE_CACHE", raising=False)
        fake_ticker = MagicMock()
        fake_ticker.history.return_value = synthetic_ohlcv
        target = tmp_path / "subdir" / "out.png"

        from engine.chart_render import save_kline_to
        with patch("yfinance.Ticker", return_value=fake_ticker):
            ok = save_kline_to(str(target), "NVDA", period="3mo")
        assert ok is True
        assert target.exists()
        assert target.read_bytes().startswith(b"\x89PNG")

    def test_returns_false_on_no_data(self, tmp_path, monkeypatch):
        import pandas as pd
        monkeypatch.delenv("ORALLEXA_USE_CACHE", raising=False)
        fake_ticker = MagicMock()
        fake_ticker.history.return_value = pd.DataFrame()
        from engine.chart_render import save_kline_to
        with patch("yfinance.Ticker", return_value=fake_ticker):
            ok = save_kline_to(str(tmp_path / "out.png"), "XYZ")
        assert ok is False
