"""Freeze one complete, private 90-pair input cohort from Alpaca historical data.

This module only calls the market-data GET endpoint. It cannot submit orders.
Alpaca's ordinary market-data terms prohibit redistribution of the raw bars.
Never commit the generated CSVs or publish numerical claims based on them
without separately acquiring rights to share all the underlying data.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
from io import StringIO
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TICKERS = ("NVDA", "AAPL", "TSLA", "GOOG", "META", "INTC", "QQQ", "MSFT", "AMZN", "SPY")
START = "2021-01-01"
END_INCLUSIVE = "2026-09-28"
# Alpaca daily bars are timestamped at midnight New York (04:00/05:00 UTC).
# Request the following UTC midnight, then validate the last intended session.
REQUEST_END_UTC = "2026-09-29T00:00:00Z"
PROTOCOL_IDS = {
    "iex": "alpaca-iex-alternative-v2-declared-2026-09-30",
    "sip": "alpaca-sip-alternative-v2-declared-2026-09-30",
}
API_URL = "https://data.alpaca.markets/v2/stocks/bars"
PageFetcher = Callable[[str, str | None], dict]


def _private_target(out: Path) -> Path:
    """Refuse a tracked-repo output path; absolute paths outside the repo work."""
    target = out.resolve()
    repo = Path(__file__).resolve().parents[1]
    if target.is_relative_to(repo) and not target.is_relative_to(repo / "eval/private_snapshots"):
        raise ValueError("Alpaca CSVs inside this repo must be under ignored eval/private_snapshots/")
    if target.exists():
        raise FileExistsError(f"Snapshot already exists: {target}; choose a new directory")
    return target


def _as_date(timestamp: str) -> date:
    if not isinstance(timestamp, str):
        raise ValueError("Bar timestamp missing")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Bar timestamp must carry a timezone")
        return parsed.astimezone(ZoneInfo("America/New_York")).date()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid bar timestamp: {timestamp!r}") from exc


def _rows_for_ticker(
    ticker: str, fetch_page: PageFetcher, *, start: str, end: str, min_bars: int
) -> list[tuple]:
    rows: list[tuple] = []
    page_token: str | None = None
    seen_tokens: set[str] = set()
    seen_dates: set[date] = set()
    for _ in range(20):
        response = fetch_page(ticker, page_token)
        if not isinstance(response, dict) or not isinstance(response.get("bars"), dict):
            raise ValueError(f"Malformed Alpaca bars response for {ticker}")
        bars = response["bars"]
        if set(bars) - {ticker} or not isinstance(bars.get(ticker, []), list):
            raise ValueError(f"Unexpected symbols or bars format for {ticker}")
        for bar in bars.get(ticker, []):
            if not isinstance(bar, dict):
                raise ValueError(f"Invalid bar for {ticker}")
            day = _as_date(bar.get("t"))
            if not (date.fromisoformat(start) <= day <= date.fromisoformat(end)):
                raise ValueError(f"Out-of-range bar for {ticker}: {day}")
            if day in seen_dates:
                raise ValueError(f"Duplicate daily bar for {ticker}: {day}")
            seen_dates.add(day)
            try:
                values = tuple(float(bar[field]) for field in ("o", "h", "l", "c"))
                volume = bar["v"]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Missing OHLCV value for {ticker}/{day}") from exc
            if (not all(math.isfinite(value) and value > 0 for value in values)
                    or not isinstance(volume, int) or isinstance(volume, bool) or volume < 0
                    or values[1] < max(values[0], values[2], values[3])
                    or values[2] > min(values[0], values[1], values[3])):
                raise ValueError(f"Invalid OHLCV value for {ticker}/{day}")
            rows.append((day, *values, volume))
        token = response.get("next_page_token")
        if not token:
            break
        if not isinstance(token, str) or token in seen_tokens:
            raise ValueError(f"Repeated/invalid pagination token for {ticker}")
        seen_tokens.add(token)
        page_token = token
    else:
        raise ValueError(f"Too many pages for {ticker}")

    rows.sort(key=lambda row: row[0])
    if (len(rows) < min_bars or not rows
            or rows[0][0] > date.fromisoformat(start) + timedelta(days=7)
            or rows[-1][0] != date.fromisoformat(end)):
        raise ValueError(f"Incomplete historical coverage for {ticker}: {len(rows)} bars")
    return rows


def _csv_bytes(rows: list[tuple]) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("Date", "Open", "High", "Low", "Close", "Volume"))
    for day, opn, high, low, close, volume in rows:
        writer.writerow((day.isoformat(), *(repr(v) for v in (opn, high, low, close)), volume))
    return output.getvalue().encode("utf-8")


def freeze_alpaca_data(
    fetch_page: PageFetcher,
    out: Path,
    *,
    tickers: tuple[str, ...] = TICKERS,
    start: str = START,
    end: str = END_INCLUSIVE,
    min_bars: int = 504,
    feed: str = "iex",
) -> dict:
    """Validate the full cohort before atomically creating an ignored snapshot."""
    if feed not in PROTOCOL_IDS:
        raise ValueError("Feed must be iex or sip")
    target = _private_target(Path(out))
    data: dict[str, bytes] = {}
    counts: dict[str, int] = {}
    first_dates: tuple[date, ...] | None = None
    for ticker in tickers:
        rows = _rows_for_ticker(ticker, fetch_page, start=start, end=end, min_bars=min_bars)
        dates = tuple(row[0] for row in rows)
        if first_dates is not None and dates != first_dates:
            raise ValueError(f"Trading dates differ across tickers: {ticker}")
        first_dates = dates
        data[ticker] = _csv_bytes(rows)
        counts[ticker] = len(rows)

    manifest = {
        "protocol_id": PROTOCOL_IDS[feed],
        "source": "Alpaca Historical Stock Bars GET API",
        "endpoint": API_URL,
        "parameters": {"timeframe": "1Day", "feed": feed, "adjustment": "split,dividend",
                       "asof": end, "start": start,
                       "requested_end_utc": REQUEST_END_UTC, "last_session_required": end,
                       "sort": "asc",
                       "limit": 10000},
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "tickers": list(tickers),
        "rows_per_ticker": counts,
        "sha256": {ticker: hashlib.sha256(raw).hexdigest() for ticker, raw in data.items()},
        "license": "Private/internal use; do not redistribute Alpaca market-data CSVs",
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".alpaca-freeze-", dir=target.parent))
    try:
        for ticker, raw in data.items():
            (staging / f"{ticker}.csv").write_bytes(raw)
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if target.exists():
            raise FileExistsError(f"Snapshot already exists: {target}")
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return manifest


def make_http_fetcher(api_key: str, secret_key: str, *, feed: str = "iex", timeout: float = 20) -> PageFetcher:
    """Create a GET-only Alpaca market-data client; no trading SDK is imported."""
    if not api_key or not secret_key:
        raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
    if feed not in PROTOCOL_IDS:
        raise ValueError("Feed must be iex or sip")

    def get_page(ticker: str, page_token: str | None) -> dict:
        params = {"symbols": ticker, "timeframe": "1Day", "start": START,
                  "end": REQUEST_END_UTC, "limit": 10000, "adjustment": "split,dividend",
                  "feed": feed, "asof": END_INCLUSIVE, "sort": "asc"}
        if page_token:
            params["page_token"] = page_token
        request = Request(
            API_URL + "?" + urlencode(params),
            headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key},
            method="GET",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise PermissionError(f"Alpaca {feed} data feed is not authorized for these credentials") from exc
            raise

    return get_page


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", choices=tuple(PROTOCOL_IDS), default="iex",
                        help="IEX is the paper-only entitlement; SIP requires separate authorization")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out = args.out or Path(f"eval/private_snapshots/alpaca-{args.feed}-2026-09-28")
    _private_target(out)  # Fail before any API call if the path is unsafe.
    from dotenv import load_dotenv

    load_dotenv()
    fetch_page = make_http_fetcher(os.getenv("ALPACA_API_KEY", ""), os.getenv("ALPACA_SECRET_KEY", ""), feed=args.feed)
    manifest = freeze_alpaca_data(fetch_page, out, feed=args.feed)
    print(f"Private {args.feed} snapshot of {len(manifest['tickers'])} symbols saved to {out}")
    print("Do not commit raw CSVs or publish numerical performance claims from these licensed inputs.")


if __name__ == "__main__":
    main()
