"""Read-only historical candles for charts, with no model or broker calls.

Daily candle keys are exchange-local session dates. Intraday keys and all
metadata instants are UTC. The final candle can still be an open bar.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from typing import Any

import pandas as pd


ALLOWED_WINDOWS = frozenset({
    ("1d", "5m"), ("5d", "15m"), ("1mo", "1h"),
    ("3mo", "1d"), ("1y", "1d"),
})
PROVIDER_TIMEOUT_SECONDS = 8
SOURCE = "Yahoo Finance via yfinance"
NOTICE = "Historical data may be delayed; the latest bar may still be open."
_SYMBOL = re.compile(r"[A-Za-z0-9^][A-Za-z0-9.^=\-]{0,19}")
_FIELDS = ("Open", "High", "Low", "Close", "Volume")


class MarketHistoryUnavailable(Exception):
    """The upstream provider could not supply a reliable response."""


def validate_history_request(ticker: str, period: str, interval: str) -> str:
    """Reject unsupported requests before making any provider request."""
    if not isinstance(ticker, str) or not _SYMBOL.fullmatch(ticker):
        raise ValueError("Invalid ticker symbol.")
    if (period, interval) not in ALLOWED_WINDOWS:
        raise ValueError("Unsupported period and interval combination.")
    return ticker.upper()


def _utc_iso(instant: datetime | pd.Timestamp) -> str:
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_history(ticker: str, period: str, interval: str) -> pd.DataFrame:
    # Explicit raw OHLC avoids mixing the optional adjusted daily cache with
    # unadjusted intraday data. Ticker.history preserves exchange-local dates.
    import yfinance as yf

    return yf.Ticker(ticker).history(
        period=period,
        interval=interval,
        auto_adjust=False,
        back_adjust=False,
        repair=False,
        actions=False,
        prepost=False,
        timeout=PROVIDER_TIMEOUT_SECONDS,
        raise_errors=True,
    )


def _normalize_history(
    frame: pd.DataFrame | None, interval: str, fetched_at: datetime,
) -> tuple[list[dict[str, Any]], str | None]:
    """Discard invalid rows; sort and keep the last valid duplicate bar.

    Provider timestamps must have a timezone. Guessing a naive timestamp's
    exchange timezone can shift an intraday candle or its trading day.
    No candle is interpolated and no price, volume, or time is invented.
    """
    if frame is None or frame.empty or not all(key in frame for key in _FIELDS):
        return [], None

    daily = interval == "1d"
    by_time: dict[str | int, tuple[pd.Timestamp, dict[str, Any]]] = {}
    for raw_time, row in frame.iterrows():
        try:
            if not isinstance(raw_time, (datetime, pd.Timestamp)):
                continue
            stamp = pd.Timestamp(raw_time)
            if pd.isna(stamp) or stamp.tzinfo is None:
                continue
            utc_stamp = stamp.tz_convert("UTC")
            # A future start cannot be an observed historical bar. An open
            # bar whose start is in the past is intentionally retained.
            if utc_stamp > fetched_at:
                continue
            values = [float(row[key]) for key in _FIELDS]
            if not all(math.isfinite(value) for value in values):
                continue
            opened, high, low, close, volume = values
            if min(opened, high, low, close) <= 0 or volume < 0:
                continue
            if not low <= min(opened, close) <= max(opened, close) <= high:
                continue
            candle_time: str | int = (
                stamp.strftime("%Y-%m-%d") if daily else int(utc_stamp.timestamp())
            )
            candle = dict(zip(
                ("time", "open", "high", "low", "close", "volume"),
                (candle_time, opened, high, low, close, volume),
            ))
            by_time[candle_time] = (utc_stamp, candle)
        except (ValueError, TypeError, OverflowError):
            continue

    ordered = sorted(by_time.values(), key=lambda item: item[0])
    return (
        [candle for _, candle in ordered],
        _utc_iso(ordered[-1][0]) if ordered else None,
    )


def get_market_history(
    ticker: str, period: str = "1mo", interval: str = "1h",
) -> dict[str, Any]:
    """Fetch actual provider candles or raise an opaque upstream failure.

    An empty provider result is a successful, empty response. Provider errors
    are distinct, and must never trigger a synthetic-data fallback.
    """
    ticker = validate_history_request(ticker, period, interval)
    try:
        frame = _load_history(ticker, period, interval)
        fetched_at = datetime.now(timezone.utc)
        candles, as_of = _normalize_history(frame, interval, fetched_at)
    except Exception:
        raise MarketHistoryUnavailable("Market history is temporarily unavailable.") from None

    return {
        "ticker": ticker,
        "period": period,
        "interval": interval,
        "source": SOURCE,
        "fetched_at": _utc_iso(fetched_at),
        "as_of": as_of,
        "as_of_kind": "bar_start",
        "timezone": "UTC",
        "candle_time_basis": "exchange_session_date" if interval == "1d" else "UTC",
        "adjusted": False,
        "notice": NOTICE,
        "candles": candles,
    }
