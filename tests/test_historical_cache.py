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


# ── Cache-aware get_prices ─────────────────────────────────────────────────


class TestGetPrices:
    def _fake_ticker(self, df):
        ticker = MagicMock()
        ticker.history.return_value = df
        return ticker

    def test_serves_cache_when_fresh_and_covers_range(self, cache):
        import pandas as pd
        df = pd.DataFrame(
            {"Open": [1], "High": [1], "Low": [1], "Close": [1], "Volume": [1]},
            index=pd.date_range("2024-01-01", periods=1),
        )
        with patch("yfinance.Ticker", return_value=self._fake_ticker(df)) as mock_yf:
            cache.populate_prices("NVDA", start="2024-01-01", end="2024-12-31")
            assert mock_yf.call_count == 1
            # Second call within cached range and 24h freshness → no refetch.
            out = cache.get_prices("NVDA", start="2024-06-01", end="2024-09-30",
                                    max_age_hours=24)
            assert mock_yf.call_count == 1
        assert out is not None
        assert len(out) == 1

    def test_refetches_when_stale(self, cache):
        import pandas as pd
        df = pd.DataFrame(
            {"Open": [1], "High": [1], "Low": [1], "Close": [1], "Volume": [1]},
            index=pd.date_range("2024-01-01", periods=1),
        )
        with patch("yfinance.Ticker", return_value=self._fake_ticker(df)) as mock_yf:
            cache.populate_prices("NVDA", start="2024-01-01", end="2024-12-31")
            # max_age_hours=0 → cache is always stale → refetch.
            cache.get_prices("NVDA", start="2024-06-01", end="2024-09-30",
                              max_age_hours=0)
            assert mock_yf.call_count == 2

    def test_refetches_when_range_extends_past_cache(self, cache):
        import pandas as pd
        df = pd.DataFrame(
            {"Open": [1], "High": [1], "Low": [1], "Close": [1], "Volume": [1]},
            index=pd.date_range("2024-01-01", periods=1),
        )
        with patch("yfinance.Ticker", return_value=self._fake_ticker(df)) as mock_yf:
            cache.populate_prices("NVDA", start="2024-06-01", end="2024-09-30")
            # Range start before cached start → refetch.
            cache.get_prices("NVDA", start="2024-01-01", end="2024-09-30",
                              max_age_hours=24)
            assert mock_yf.call_count == 2

    def test_returns_none_when_yfinance_returns_empty(self, cache):
        import pandas as pd
        with patch("yfinance.Ticker", return_value=self._fake_ticker(pd.DataFrame())):
            out = cache.get_prices("XYZ", start="2024-01-01", end="2024-12-31")
        assert out is None


# ── Cache-aware get_earnings_dates ─────────────────────────────────────────


class TestGetEarningsDates:
    def _fake_ticker_with_earnings(self, df):
        ticker = MagicMock()
        ticker.earnings_dates = df
        return ticker

    def test_serves_cache_when_fresh(self, cache):
        import pandas as pd
        ed = pd.DataFrame(
            {"EPS Estimate": [1.5], "Reported EPS": [1.6], "Surprise(%)": [6.7]},
            index=pd.date_range("2024-01-15", periods=1),
        )
        with patch("yfinance.Ticker", return_value=self._fake_ticker_with_earnings(ed)) as mock_yf:
            cache.populate_earnings_dates_raw("NVDA")
            assert mock_yf.call_count == 1
            out = cache.get_earnings_dates("NVDA", max_age_hours=24)
            # No second yfinance call — served from cache.
            assert mock_yf.call_count == 1
        assert out is not None
        assert "Surprise(%)" in out.columns

    def test_refetches_when_stale(self, cache):
        import pandas as pd
        ed = pd.DataFrame(
            {"EPS Estimate": [1.5], "Reported EPS": [1.6], "Surprise(%)": [6.7]},
            index=pd.date_range("2024-01-15", periods=1),
        )
        with patch("yfinance.Ticker", return_value=self._fake_ticker_with_earnings(ed)) as mock_yf:
            cache.populate_earnings_dates_raw("NVDA")
            cache.get_earnings_dates("NVDA", max_age_hours=0)
            assert mock_yf.call_count == 2

    def test_returns_none_on_no_data(self, cache):
        ticker = MagicMock()
        ticker.earnings_dates = None
        with patch("yfinance.Ticker", return_value=ticker):
            assert cache.get_earnings_dates("XYZ") is None


# ── get_prices_by_period (relative-period helper) ─────────────────────────


class TestGetPricesByPeriod:
    def _fake_ticker(self, df):
        ticker = MagicMock()
        ticker.history.return_value = df
        return ticker

    def test_translates_period_to_dates_and_caches(self, cache):
        import pandas as pd
        df = pd.DataFrame(
            {"Open": [1, 2], "High": [2, 3], "Low": [1, 2], "Close": [2, 3], "Volume": [100, 200]},
            index=pd.date_range("2026-04-01", periods=2),
        )
        with patch("yfinance.Ticker", return_value=self._fake_ticker(df)) as mock_yf:
            out1 = cache.get_prices_by_period("NVDA", period="1mo")
            out2 = cache.get_prices_by_period("NVDA", period="1mo")
            # Second call within 24h freshness → no second yfinance hit.
            assert mock_yf.call_count == 1
        assert out1 is not None and out2 is not None
        assert len(out1) == 2

    def test_unsupported_period_returns_none(self, cache):
        # No yfinance call should be triggered for unknown period strings.
        with patch("yfinance.Ticker") as mock_yf:
            assert cache.get_prices_by_period("NVDA", period="4w") is None
            assert mock_yf.call_count == 0

    def test_supports_common_periods(self, cache):
        from engine.historical_cache import HistoricalCache
        assert {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y"}.issubset(
            HistoricalCache._PERIOD_DAYS.keys()
        )


# ── Wiring: engine/daily_intel.py routes through cache when enabled ──────


class TestDailyIntelWiring:
    """The 20-day-volume and SPY-6mo lookups are the highest-frequency
    yfinance hits in production. Both should serve from cache when on."""

    def test_volume_history_uses_cache_when_env_set(self, monkeypatch, cache):
        import pandas as pd
        # Pre-populate via get_prices_by_period itself so the cached range
        # exactly matches what the wired call will request later.
        df = pd.DataFrame(
            {"Open": [1] * 25, "High": [1] * 25, "Low": [1] * 25,
             "Close": [1] * 25, "Volume": list(range(1_000_000, 1_000_000 + 25 * 1000, 1000))},
            index=pd.date_range("2026-04-01", periods=25),
        )
        with patch("yfinance.Ticker") as mock_seed:
            mock_seed.return_value.history.return_value = df
            cache.get_prices_by_period("NVDA", period="1mo")

        import engine.historical_cache as hc
        monkeypatch.setattr(hc, "_DEFAULT_INSTANCE", cache)
        monkeypatch.setenv("ORALLEXA_USE_CACHE", "1")

        # Now drive _fetch_price_with_volume — fast_info needs to be mocked,
        # the history call should NOT hit yfinance because the cache covers it.
        from engine import daily_intel
        fast = MagicMock()
        fast.last_price = 100.0
        fast.previous_close = 99.0
        fast.last_volume = 50_000
        fake_ticker = MagicMock()
        fake_ticker.fast_info = fast
        # If the wiring works, history() on this ticker is never called.
        fake_ticker.history.side_effect = AssertionError("should not hit yfinance.history")

        with patch("yfinance.Ticker", return_value=fake_ticker):
            out = daily_intel._fetch_price_with_volume("NVDA")

        assert out is not None
        assert out["ticker"] == "NVDA"
        # avg_volume was derived from the cached 25 bars (last 20 mean).
        assert out["avg_volume"] > 0

    def test_volume_history_falls_through_when_env_unset(self, monkeypatch):
        import pandas as pd
        monkeypatch.delenv("ORALLEXA_USE_CACHE", raising=False)
        df = pd.DataFrame(
            {"Open": [1] * 5, "High": [1] * 5, "Low": [1] * 5,
             "Close": [1] * 5, "Volume": [1_000_000] * 5},
            index=pd.date_range("2026-04-22", periods=5),
        )
        fast = MagicMock(last_price=100.0, previous_close=99.0, last_volume=50_000)
        fake_ticker = MagicMock()
        fake_ticker.fast_info = fast
        fake_ticker.history.return_value = df

        from engine import daily_intel
        with patch("yfinance.Ticker", return_value=fake_ticker):
            out = daily_intel._fetch_price_with_volume("NVDA")

        assert out is not None
        # history() must be called when cache is off — backward compatible.
        assert fake_ticker.history.called


# ── Wiring: skills/market_data.py and engine/gnn_signal.py ────────────────


class TestMarketDataSkillWiring:
    """MarketDataSkill is the canonical OHLCV fetch entry point — wiring
    here saves round-trips wherever it's used."""

    def test_daily_interval_uses_cache_when_env_set(self, monkeypatch, cache):
        import pandas as pd
        df = pd.DataFrame(
            {"Open": [1] * 25, "High": [1] * 25, "Low": [1] * 25,
             "Close": [1] * 25, "Volume": [100_000] * 25},
            index=pd.date_range("2026-04-01", periods=25),
        )
        # Pre-populate via the period helper so the cache exactly covers
        # what MarketDataSkill will request.
        with patch("yfinance.Ticker") as mock_seed:
            mock_seed.return_value.history.return_value = df
            cache.get_prices_by_period("NVDA", period="1mo")

        import engine.historical_cache as hc
        monkeypatch.setattr(hc, "_DEFAULT_INSTANCE", cache)
        monkeypatch.setenv("ORALLEXA_USE_CACHE", "1")

        from skills.market_data import MarketDataSkill
        with patch("yfinance.download") as mock_dl:
            out = MarketDataSkill("NVDA").execute(period="1mo", interval="1d")
            # Cache hit → yf.download is never called.
            assert mock_dl.call_count == 0
        assert out is not None and len(out) == 25

    def test_intraday_interval_always_hits_yfinance(self, monkeypatch):
        # Even with cache enabled, 5m bars must skip the cache (they're not
        # cacheable at 24h freshness).
        import pandas as pd
        monkeypatch.setenv("ORALLEXA_USE_CACHE", "1")
        df = pd.DataFrame(
            {"Open": [1], "High": [1], "Low": [1], "Close": [1], "Volume": [1]},
            index=pd.date_range("2026-04-27 09:30", periods=1, freq="5min"),
        )
        with patch("yfinance.download", return_value=df) as mock_dl:
            from skills.market_data import MarketDataSkill
            MarketDataSkill("NVDA").execute(period="5d", interval="5m")
            assert mock_dl.call_count == 1

    def test_falls_through_when_env_unset(self, monkeypatch):
        import pandas as pd
        monkeypatch.delenv("ORALLEXA_USE_CACHE", raising=False)
        df = pd.DataFrame(
            {"Open": [1], "High": [1], "Low": [1], "Close": [1], "Volume": [1]},
            index=pd.date_range("2026-04-01", periods=1),
        )
        with patch("yfinance.download", return_value=df) as mock_dl:
            from skills.market_data import MarketDataSkill
            MarketDataSkill("NVDA").execute(period="1mo", interval="1d")
            assert mock_dl.call_count == 1


class TestGnnSignalWiring:
    """GNN signal scans many tickers per call — caching this is the biggest
    single round-trip saving in the codebase. Skips when torch isn't
    installed; CI doesn't ship torch (too heavy)."""

    @pytest.fixture(autouse=True)
    def _require_torch(self):
        pytest.importorskip("torch")

    def test_cache_serves_all_tickers_when_pre_populated(self, monkeypatch, cache):
        import pandas as pd
        # Synthesize a long enough series so add_indicators() doesn't drop the row.
        df = pd.DataFrame(
            {"Open": list(range(100, 140)), "High": list(range(101, 141)),
             "Low": list(range(99, 139)), "Close": list(range(100, 140)),
             "Volume": [1_000_000] * 40},
            index=pd.date_range("2026-03-01", periods=40),
        )
        # Seed the cache for two tickers via the period helper.
        with patch("yfinance.Ticker") as mock_seed:
            mock_seed.return_value.history.return_value = df
            cache.get_prices_by_period("NVDA", period="6mo")
            cache.get_prices_by_period("AAPL", period="6mo")

        import engine.historical_cache as hc
        monkeypatch.setattr(hc, "_DEFAULT_INSTANCE", cache)
        monkeypatch.setenv("ORALLEXA_USE_CACHE", "1")

        # Now the GNN fetch should NOT hit yfinance for these tickers.
        with patch("yfinance.Ticker") as mock_yf:
            mock_yf.return_value.history.side_effect = AssertionError(
                "should not hit yfinance.history"
            )
            from engine.gnn_signal import _fetch_features
            features = _fetch_features(["NVDA", "AAPL"], period="6mo")

        assert "NVDA" in features and "AAPL" in features

    def test_falls_through_per_ticker_on_cache_miss(self, monkeypatch, cache):
        import pandas as pd
        # Cache empty → every ticker must hit yfinance.
        df = pd.DataFrame(
            {"Open": list(range(100, 140)), "High": list(range(101, 141)),
             "Low": list(range(99, 139)), "Close": list(range(100, 140)),
             "Volume": [1_000_000] * 40},
            index=pd.date_range("2026-03-01", periods=40),
        )
        import engine.historical_cache as hc
        monkeypatch.setattr(hc, "_DEFAULT_INSTANCE", cache)
        monkeypatch.setenv("ORALLEXA_USE_CACHE", "1")

        fake_ticker = MagicMock()
        fake_ticker.history.return_value = df
        with patch("yfinance.Ticker", return_value=fake_ticker):
            from engine.gnn_signal import _fetch_features
            features = _fetch_features(["NVDA"], period="6mo")
        assert "NVDA" in features


# ── Module-level helpers ───────────────────────────────────────────────────


class TestModuleHelpers:
    def test_default_cache_is_singleton(self):
        from engine.historical_cache import get_default_cache
        a = get_default_cache()
        b = get_default_cache()
        assert a is b

    def test_cache_enabled_reads_env(self, monkeypatch):
        from engine.historical_cache import cache_enabled
        monkeypatch.delenv("ORALLEXA_USE_CACHE", raising=False)
        assert cache_enabled() is False
        monkeypatch.setenv("ORALLEXA_USE_CACHE", "0")
        assert cache_enabled() is False
        monkeypatch.setenv("ORALLEXA_USE_CACHE", "1")
        assert cache_enabled() is True
        monkeypatch.setenv("ORALLEXA_USE_CACHE", "true")
        assert cache_enabled() is True


# ── Wiring: engine/earnings.py routes through the cache when enabled ──────


class TestEarningsModuleWiring:
    """The integration point that actually saves yfinance round-trips."""

    def test_uses_cache_when_env_set(self, monkeypatch, cache):
        import pandas as pd
        ed = pd.DataFrame(
            {"EPS Estimate": [1.5], "Reported EPS": [1.6], "Surprise(%)": [6.7]},
            index=pd.date_range((pd.Timestamp.utcnow().tz_localize(None) +
                                  pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
                                 periods=1),
        )
        # Pre-populate the cache instance so the wiring serves from it.
        ticker = MagicMock()
        ticker.earnings_dates = ed
        with patch("yfinance.Ticker", return_value=ticker):
            cache.populate_earnings_dates_raw("NVDA")

        # Force engine.earnings to use this cache instance + flip the env flag.
        import engine.historical_cache as hc
        monkeypatch.setattr(hc, "_DEFAULT_INSTANCE", cache)
        monkeypatch.setenv("ORALLEXA_USE_CACHE", "1")

        # No yfinance.Ticker call expected — entirely from cache.
        with patch("yfinance.Ticker") as mock_yf:
            from engine.earnings import fetch_earnings_calendar
            out = fetch_earnings_calendar("NVDA", days_ahead=60)
            assert mock_yf.call_count == 0
        assert isinstance(out, list)

    def test_falls_through_to_yfinance_when_env_unset(self, monkeypatch):
        import pandas as pd
        monkeypatch.delenv("ORALLEXA_USE_CACHE", raising=False)
        ed = pd.DataFrame(
            {"EPS Estimate": [1.5]},
            index=pd.date_range((pd.Timestamp.utcnow().tz_localize(None) +
                                  pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
                                 periods=1),
        )
        ticker = MagicMock()
        ticker.earnings_dates = ed
        with patch("yfinance.Ticker", return_value=ticker) as mock_yf:
            from engine.earnings import fetch_earnings_calendar
            fetch_earnings_calendar("NVDA")
            # Direct yfinance call when cache is off — backward compatible.
            assert mock_yf.call_count >= 1
