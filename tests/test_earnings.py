"""
tests/test_earnings.py
──────────────────────────────────────────────────────────────────
Tests for engine/earnings.py — calendar, PEAD stats, combined signal.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.earnings import (
    fetch_earnings_calendar,
    compute_pead_stats,
    get_earnings_signal,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

def _make_earnings_df(rows):
    """rows: [(datetime, eps_est, reported_eps, surprise_pct), ...] — newest first."""
    idx = pd.DatetimeIndex([r[0] for r in rows], tz="US/Eastern")
    df = pd.DataFrame({
        "EPS Estimate": [r[1] for r in rows],
        "Reported EPS": [r[2] for r in rows],
        "Surprise(%)":   [r[3] for r in rows],
    }, index=idx)
    return df


def _make_price_history(start: datetime, days: int = 500) -> pd.DataFrame:
    """Deterministic rising price series for drift calc."""
    dates = pd.date_range(start=start, periods=days, freq="B")
    closes = 100.0 + np.arange(days) * 0.1
    return pd.DataFrame({
        "Open": closes, "High": closes * 1.01, "Low": closes * 0.99,
        "Close": closes, "Volume": 1_000_000,
    }, index=dates)


def _mock_ticker(earnings_df=None, price_df=None):
    """Build a MagicMock yfinance Ticker with given data."""
    tk = MagicMock()
    tk.earnings_dates = earnings_df
    tk.history.return_value = price_df if price_df is not None else pd.DataFrame()
    return tk


# ── fetch_earnings_calendar ────────────────────────────────────────────────

class TestFetchEarningsCalendar:
    def test_returns_future_events_sorted(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rows = [
            (now + timedelta(days=90), 2.0, None, None),   # beyond window
            (now + timedelta(days=30), 1.5, None, None),   # in window
            (now + timedelta(days=5),  1.2, None, None),   # in window, soonest
            (now - timedelta(days=30), 1.0, 1.1, 10.0),    # past, filtered
        ]
        df = _make_earnings_df(rows)
        with patch("yfinance.Ticker", return_value=_mock_ticker(df)):
            result = fetch_earnings_calendar("NVDA", days_ahead=60)
        assert len(result) == 2
        assert result[0]["days_until"] == 5
        assert result[0]["eps_estimate"] == 1.2
        assert result[1]["days_until"] == 30

    def test_empty_when_none(self):
        with patch("yfinance.Ticker", return_value=_mock_ticker(None)):
            assert fetch_earnings_calendar("XYZ") == []

    def test_empty_on_exception(self):
        with patch("yfinance.Ticker", side_effect=RuntimeError("api down")):
            assert fetch_earnings_calendar("NVDA") == []

    def test_handles_nan_eps(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rows = [(now + timedelta(days=10), float("nan"), None, None)]
        df = _make_earnings_df(rows)
        with patch("yfinance.Ticker", return_value=_mock_ticker(df)):
            result = fetch_earnings_calendar("NVDA")
        assert result[0]["eps_estimate"] is None


# ── compute_pead_stats ─────────────────────────────────────────────────────

class TestComputePeadStats:
    def test_returns_drift_and_positive_rate(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        earnings_rows = [
            (now - timedelta(days=100), 1.0, 1.1, 10.0),
            (now - timedelta(days=200), 1.0, 0.95, -5.0),
            (now - timedelta(days=300), 1.0, 1.05, 5.0),
        ]
        edf = _make_earnings_df(earnings_rows)
        price_start = now - timedelta(days=400)
        pdf = _make_price_history(price_start, days=400)

        with patch("yfinance.Ticker", return_value=_mock_ticker(edf, pdf)):
            result = compute_pead_stats("NVDA", lookback_years=2)

        assert result["available"] is True
        assert result["n_events"] == 3
        # Rising price series — all drifts positive
        assert result["positive_rate"] == 1.0
        assert result["avg_drift_5d"] > 0

    def test_unavailable_when_no_past_events(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        edf = _make_earnings_df([(now + timedelta(days=5), 1.0, None, None)])
        with patch("yfinance.Ticker", return_value=_mock_ticker(edf)):
            result = compute_pead_stats("NVDA")
        assert result["available"] is False

    def test_unavailable_when_no_price_history(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        edf = _make_earnings_df([
            (now - timedelta(days=100), 1.0, 1.1, 10.0),
            (now - timedelta(days=200), 1.0, 0.95, -5.0),
        ])
        with patch("yfinance.Ticker", return_value=_mock_ticker(edf, pd.DataFrame())):
            result = compute_pead_stats("NVDA")
        assert result["available"] is False

    def test_surprise_drift_correlation(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # With a monotonically rising price series, all drifts are positive —
        # but newer events have slightly different drift; surprise varies.
        # We test that corr key is present and in [-1, 1].
        earnings_rows = [
            (now - timedelta(days=80),  1.0, 1.2,  20.0),
            (now - timedelta(days=180), 1.0, 0.9, -10.0),
            (now - timedelta(days=280), 1.0, 1.1,  10.0),
            (now - timedelta(days=380), 1.0, 1.05,  5.0),
        ]
        edf = _make_earnings_df(earnings_rows)
        pdf = _make_price_history(now - timedelta(days=500), days=500)
        with patch("yfinance.Ticker", return_value=_mock_ticker(edf, pdf)):
            result = compute_pead_stats("NVDA", lookback_years=2)
        assert "surprise_drift_corr" in result
        assert -1.0 <= result["surprise_drift_corr"] <= 1.0


# ── get_earnings_signal ────────────────────────────────────────────────────

class TestGetEarningsSignal:
    def test_combines_calendar_and_pead(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        edf = _make_earnings_df([
            (now + timedelta(days=7), 1.5, None, None),
            (now - timedelta(days=90), 1.0, 1.1, 10.0),
            (now - timedelta(days=180), 1.0, 1.05, 5.0),
        ])
        pdf = _make_price_history(now - timedelta(days=300), days=300)

        with patch("yfinance.Ticker", return_value=_mock_ticker(edf, pdf)):
            sig = get_earnings_signal("NVDA")

        assert sig["ticker"] == "NVDA"
        assert sig["days_until"] == 7
        assert sig["eps_estimate"] == 1.5
        assert sig["pead"]["available"] is True
        assert "NVDA reports in 7 days" in sig["narrative"]
        assert "PEAD history" in sig["narrative"]

    def test_narrative_no_upcoming(self):
        with patch("yfinance.Ticker", return_value=_mock_ticker(None)):
            sig = get_earnings_signal("XYZ")
        assert sig["next_date"] is None
        assert "no earnings scheduled" in sig["narrative"]
