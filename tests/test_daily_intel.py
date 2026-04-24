"""Tests for engine/daily_intel.py — constants and _fetch_price_with_volume."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.daily_intel import (
    CACHE_PATH,
    SCAN_TICKERS,
    SECTOR_ETFS,
    _fetch_price_with_volume,
    _generate_earnings_watchlist,
)


# ── Constants ────────────────────────────────────────────────────────────────


class TestConstants:
    def test_scan_tickers_is_non_empty_list_of_strings(self) -> None:
        assert isinstance(SCAN_TICKERS, list)
        assert len(SCAN_TICKERS) > 0
        for ticker in SCAN_TICKERS:
            assert isinstance(ticker, str)

    def test_sector_etfs_is_list_of_tuples(self) -> None:
        assert isinstance(SECTOR_ETFS, list)
        assert len(SECTOR_ETFS) > 0
        for item in SECTOR_ETFS:
            assert isinstance(item, tuple)
            assert len(item) == 2
            name, etf = item
            assert isinstance(name, str)
            assert isinstance(etf, str)

    def test_cache_path_points_to_daily_intel_json(self) -> None:
        assert CACHE_PATH.name == "daily_intel.json"
        assert "memory_data" in CACHE_PATH.parts


# ── _fetch_price_with_volume ─────────────────────────────────────────────────


def _make_mock_ticker(
    price: float = 150.0,
    prev_close: float = 145.0,
    volume: int = 5_000_000,
    hist_volumes: list[int] | None = None,
) -> MagicMock:
    """Build a mock yfinance.Ticker with .fast_info and .history()."""
    mock_tk = MagicMock()

    info = MagicMock()
    info.last_price = price
    info.previous_close = prev_close
    info.last_volume = volume
    mock_tk.fast_info = info

    if hist_volumes is None:
        hist_volumes = [2_000_000] * 20
    hist_df = pd.DataFrame({"Volume": hist_volumes})
    mock_tk.history.return_value = hist_df

    return mock_tk


class TestFetchPriceWithVolume:
    @patch("yfinance.Ticker")
    def test_returns_expected_keys(self, mock_ticker_cls: MagicMock) -> None:
        mock_ticker_cls.return_value = _make_mock_ticker()

        result = _fetch_price_with_volume("AAPL")

        assert result is not None
        expected_keys = {
            "ticker",
            "price",
            "change_pct",
            "volume",
            "avg_volume",
            "volume_ratio",
            "volume_spike",
        }
        assert set(result.keys()) == expected_keys

    @patch("yfinance.Ticker")
    def test_ticker_value_matches_input(self, mock_ticker_cls: MagicMock) -> None:
        mock_ticker_cls.return_value = _make_mock_ticker()

        result = _fetch_price_with_volume("NVDA")

        assert result is not None
        assert result["ticker"] == "NVDA"

    @patch("yfinance.Ticker")
    def test_change_pct_calculation(self, mock_ticker_cls: MagicMock) -> None:
        mock_ticker_cls.return_value = _make_mock_ticker(price=110.0, prev_close=100.0)

        result = _fetch_price_with_volume("TEST")

        assert result is not None
        assert result["change_pct"] == 10.0

    @patch("yfinance.Ticker")
    def test_volume_spike_detected(self, mock_ticker_cls: MagicMock) -> None:
        # volume = 10M, avg = 2M -> ratio = 5.0, spike = True
        mock_ticker_cls.return_value = _make_mock_ticker(
            volume=10_000_000, hist_volumes=[2_000_000] * 20
        )

        result = _fetch_price_with_volume("SPIKE")

        assert result is not None
        assert result["volume_spike"] is True
        assert result["volume_ratio"] >= 2.0

    @patch("yfinance.Ticker")
    def test_no_volume_spike(self, mock_ticker_cls: MagicMock) -> None:
        # volume = 2M, avg = 2M -> ratio = 1.0, no spike
        mock_ticker_cls.return_value = _make_mock_ticker(
            volume=2_000_000, hist_volumes=[2_000_000] * 20
        )

        result = _fetch_price_with_volume("CALM")

        assert result is not None
        assert result["volume_spike"] is False

    @patch("yfinance.Ticker")
    def test_returns_none_when_price_is_zero(self, mock_ticker_cls: MagicMock) -> None:
        mock_ticker_cls.return_value = _make_mock_ticker(price=0)

        result = _fetch_price_with_volume("BAD")

        assert result is None

    @patch("yfinance.Ticker")
    def test_returns_none_on_exception(self, mock_ticker_cls: MagicMock) -> None:
        mock_ticker_cls.side_effect = Exception("network error")

        result = _fetch_price_with_volume("ERR")

        assert result is None


# ── Earnings watchlist ───────────────────────────────────────────────────────


class TestGenerateEarningsWatchlist:
    def test_filters_by_days_ahead(self):
        def fake_signal(ticker):
            return {
                "AAPL": {"next_date": "2026-05-01", "days_until": 3,
                         "eps_estimate": 1.5,
                         "pead": {"available": True, "avg_drift_5d": 1.2, "positive_rate": 0.6},
                         "narrative": "AAPL reports in 3 days"},
                "MSFT": {"next_date": "2026-06-01", "days_until": 35,
                         "eps_estimate": 2.0,
                         "pead": {"available": False}, "narrative": ""},
                "NVDA": {"next_date": None, "days_until": None,
                         "eps_estimate": None, "pead": {"available": False},
                         "narrative": ""},
            }[ticker]

        gainers = [{"ticker": "AAPL"}, {"ticker": "MSFT"}, {"ticker": "NVDA"}]
        with patch("engine.earnings.get_earnings_signal", side_effect=fake_signal):
            result = _generate_earnings_watchlist(gainers, [], [], days_ahead=7)

        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["days_until"] == 3
        assert result[0]["pead_drift"] == 1.2

    def test_empty_when_no_upcoming(self):
        with patch("engine.earnings.get_earnings_signal",
                   return_value={"next_date": None, "days_until": None,
                                 "eps_estimate": None, "pead": {"available": False},
                                 "narrative": ""}):
            result = _generate_earnings_watchlist(
                [{"ticker": "AAPL"}], [], [],
            )
        assert result == []

    def test_deduplicates_tickers(self):
        call_count = {"n": 0}

        def fake_signal(ticker):
            call_count["n"] += 1
            return {"next_date": None, "days_until": None, "eps_estimate": None,
                    "pead": {"available": False}, "narrative": ""}

        with patch("engine.earnings.get_earnings_signal", side_effect=fake_signal):
            _generate_earnings_watchlist(
                [{"ticker": "AAPL"}],
                [{"ticker": "AAPL"}],
                [{"ticker": "AAPL"}],
            )
        assert call_count["n"] == 1

    def test_sorted_by_days_until(self):
        def fake_signal(ticker):
            return {
                "A": {"next_date": "2026-05-10", "days_until": 10, "eps_estimate": None,
                      "pead": {"available": False}, "narrative": ""},
                "B": {"next_date": "2026-05-03", "days_until": 3, "eps_estimate": None,
                      "pead": {"available": False}, "narrative": ""},
                "C": {"next_date": "2026-05-07", "days_until": 7, "eps_estimate": None,
                      "pead": {"available": False}, "narrative": ""},
            }[ticker]

        with patch("engine.earnings.get_earnings_signal", side_effect=fake_signal):
            result = _generate_earnings_watchlist(
                [{"ticker": "A"}, {"ticker": "B"}, {"ticker": "C"}], [], [],
                days_ahead=30,
            )
        assert [r["days_until"] for r in result] == [3, 7, 10]
