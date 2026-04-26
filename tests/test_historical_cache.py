"""
tests/test_historical_cache.py
──────────────────────────────────────────────────────────────────
Tests for engine/historical_cache.py — file layout + metadata
ledger + load round-trips. No yfinance calls; we mock the network
and verify the cache machinery itself.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.historical_cache import HistoricalCache


@pytest.fixture
def cache(tmp_path):
    return HistoricalCache(base_dir=tmp_path)


# ── File layout ────────────────────────────────────────────────────────────


class TestPaths:
    def test_source_dir_created(self, cache, tmp_path):
        # Force creation by computing path
        d = cache._source_dir("prices")
        assert d.exists() and d.is_dir()
        assert d == tmp_path / "prices"

    def test_file_for_uppercases_ticker(self, cache):
        path = cache._file_for("prices", "nvda")
        assert path.name == "NVDA.parquet"

    def test_meta_path_at_root(self, cache, tmp_path):
        assert cache._meta_path() == tmp_path / "_meta.json"


# ── Metadata ledger ────────────────────────────────────────────────────────


class TestMetadata:
    def test_record_freshness_persists(self, cache):
        cache._record_freshness("prices", "NVDA", bars=500, start="2024-01-01")
        meta = cache._load_meta()
        assert "prices" in meta
        assert meta["prices"]["NVDA"]["bars"] == 500
        assert meta["prices"]["NVDA"]["start"] == "2024-01-01"
        assert "updated_at" in meta["prices"]["NVDA"]

    def test_status_returns_full_meta(self, cache):
        cache._record_freshness("prices", "NVDA", bars=100)
        cache._record_freshness("earnings", "NVDA", n_events=8)
        s = cache.status()
        assert "prices" in s and "earnings" in s
        assert s["earnings"]["NVDA"]["n_events"] == 8

    def test_has_returns_correctly(self, cache):
        cache._record_freshness("prices", "NVDA", bars=100)
        assert cache.has("prices", "NVDA") is True
        assert cache.has("prices", "AAPL") is False
        assert cache.has("earnings", "NVDA") is False


# ── populate_prices ────────────────────────────────────────────────────────


class TestPopulatePrices:
    def test_writes_parquet_and_records_freshness(self, cache):
        import pandas as pd
        fake_df = pd.DataFrame({
            "Open": [100, 101], "High": [102, 103],
            "Low": [99, 100], "Close": [101, 102], "Volume": [1000, 1100],
        }, index=pd.date_range("2024-01-01", periods=2))
        fake_ticker = MagicMock()
        fake_ticker.history.return_value = fake_df
        with patch("yfinance.Ticker", return_value=fake_ticker):
            n = cache.populate_prices("NVDA", start="2024-01-01", end="2024-01-03")
        assert n == 2
        meta = cache._load_meta()
        assert meta["prices"]["NVDA"]["bars"] == 2

    def test_empty_dataframe_returns_zero(self, cache):
        import pandas as pd
        fake_ticker = MagicMock()
        fake_ticker.history.return_value = pd.DataFrame()
        with patch("yfinance.Ticker", return_value=fake_ticker):
            n = cache.populate_prices("XYZ", start="2024-01-01")
        assert n == 0
        assert not cache.has("prices", "XYZ")

    def test_yfinance_exception_returns_zero(self, cache):
        with patch("yfinance.Ticker", side_effect=RuntimeError("api")):
            n = cache.populate_prices("NVDA", start="2024-01-01")
        assert n == 0


# ── load_prices round-trip ─────────────────────────────────────────────────


class TestLoadPrices:
    def test_round_trip_via_parquet(self, cache):
        import pandas as pd
        fake_df = pd.DataFrame({
            "Open": [100], "High": [102], "Low": [99], "Close": [101], "Volume": [1000],
        }, index=pd.date_range("2024-01-01", periods=1))
        fake_ticker = MagicMock()
        fake_ticker.history.return_value = fake_df
        with patch("yfinance.Ticker", return_value=fake_ticker):
            cache.populate_prices("NVDA", start="2024-01-01")
        loaded = cache.load_prices("NVDA")
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded["Close"].iloc[0] == 101

    def test_load_returns_none_when_missing(self, cache):
        assert cache.load_prices("NEVER") is None


# ── populate_earnings ──────────────────────────────────────────────────────


class TestPopulateEarnings:
    def test_writes_json_and_filters_nan(self, cache):
        import pandas as pd
        ed = pd.DataFrame({
            "EPS Estimate": [1.5, 2.0],
            "Reported EPS": [1.6, float("nan")],
            "Surprise(%)":  [6.7, float("nan")],
        }, index=pd.date_range("2024-01-01", periods=2))
        fake_ticker = MagicMock()
        fake_ticker.earnings_dates = ed
        with patch("yfinance.Ticker", return_value=fake_ticker):
            n = cache.populate_earnings("NVDA")
        assert n == 2
        loaded = cache.load_earnings("NVDA")
        assert len(loaded) == 2
        assert loaded[0]["eps_estimate"] == 1.5
        assert loaded[0]["reported_eps"] == 1.6
        # NaN handled
        assert loaded[1]["reported_eps"] is None
        assert loaded[1]["surprise_pct"] is None

    def test_no_earnings_data_returns_zero(self, cache):
        fake_ticker = MagicMock()
        fake_ticker.earnings_dates = None
        with patch("yfinance.Ticker", return_value=fake_ticker):
            n = cache.populate_earnings("XYZ")
        assert n == 0

    def test_load_empty_when_missing(self, cache):
        assert cache.load_earnings("NEVER") == []


# ── Options snapshot ───────────────────────────────────────────────────────


class TestOptionsSnapshot:
    def test_records_snapshot_note_in_meta(self, cache):
        import pandas as pd
        fake_chain = MagicMock()
        fake_chain.calls = pd.DataFrame({"strike": [100], "volume": [10]})
        fake_chain.puts = pd.DataFrame({"strike": [100], "volume": [5]})
        fake_ticker = MagicMock()
        fake_ticker.options = ("2026-05-30",)
        fake_ticker.option_chain = MagicMock(return_value=fake_chain)
        with patch("yfinance.Ticker", return_value=fake_ticker):
            ok = cache.populate_options_snapshot("NVDA")
        assert ok is True
        meta = cache._load_meta()
        assert "snapshot only" in meta["options_flow"]["NVDA"]["note"]

    def test_no_expirations_returns_false(self, cache):
        fake_ticker = MagicMock()
        fake_ticker.options = []
        with patch("yfinance.Ticker", return_value=fake_ticker):
            assert cache.populate_options_snapshot("XYZ") is False
