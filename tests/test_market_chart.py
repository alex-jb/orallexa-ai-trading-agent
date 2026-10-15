"""Offline regression checks for the chart's real-data boundary."""
from datetime import datetime, timezone
import json
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from engine import market_chart


def _frame(index, rows=None):
    if rows is None:
        rows = [[100, 103, 99, 102, 400]] * len(index)
    return pd.DataFrame(rows, index=index, columns=["Open", "High", "Low", "Close", "Volume"])


_REAL_LOAD_HISTORY = market_chart._load_history


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A chart regression test tried to contact a provider")
    monkeypatch.setattr(market_chart, "_load_history", forbidden)


def test_intraday_keeps_full_utc_times_and_json_numbers(monkeypatch):
    index = pd.DatetimeIndex(["2026-01-12 09:30", "2026-01-12 09:35"], tz="America/New_York")
    monkeypatch.setattr(market_chart, "_load_history", lambda *args: _frame(index))
    result = market_chart.get_market_history("nvda", "1d", "5m")
    assert result["ticker"] == "NVDA"
    assert result["source"] == "Yahoo Finance via yfinance"
    assert result["adjusted"] is False
    assert result["timezone"] == result["candle_time_basis"] == "UTC"
    assert result["as_of_kind"] == "bar_start"
    assert result["as_of"] == "2026-01-12T14:35:00Z"
    candles = result["candles"]
    assert [c["time"] for c in candles] == [1768228200, 1768228500]
    assert candles[0]["time"] != candles[1]["time"]
    assert all(type(c["time"]) is int for c in candles)
    assert "may still be open" in result["notice"]
    assert result["fetched_at"].endswith("Z")
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.mark.parametrize("period", ["3mo", "1y"])
def test_daily_preserves_asian_session_date_instead_of_utc_date(monkeypatch, period):
    index = pd.DatetimeIndex(["2026-01-14 00:00"], tz="Asia/Tokyo")
    monkeypatch.setattr(market_chart, "_load_history", lambda *args: _frame(index))
    result = market_chart.get_market_history("7203.T", period, "1d")
    assert result["candles"][0]["time"] == "2026-01-14"
    assert result["as_of"] == "2026-01-13T15:00:00Z"
    assert result["candle_time_basis"] == "exchange_session_date"


def test_dst_offset_uses_timestamp_not_fixed_exchange_offset(monkeypatch):
    index = pd.DatetimeIndex(["2025-10-31 09:30", "2025-11-03 09:30"], tz="America/New_York")
    monkeypatch.setattr(market_chart, "_load_history", lambda *args: _frame(index))
    result = market_chart.get_market_history("AAPL")
    assert [datetime.fromtimestamp(c["time"], timezone.utc).hour for c in result["candles"]] == [13, 14]


def test_invalid_rows_deduplication_sorting_and_future_filter(monkeypatch):
    stamps = [
        "2026-01-12 15:00", "2026-01-12 14:00", "2026-01-12 14:00",
        "2026-01-12 16:00", "2026-01-12 17:00", "2026-01-12 18:00",
        "2026-01-12 19:00", "2026-01-12 20:00", "2099-01-12 14:00",
    ]
    rows = [
        [100, 103, 99, 102, 400], [100, 103, 99, 101, 400],
        [100, 104, 99, 103, 450], [100, 103, 99, float("nan"), 400],
        [100, float("inf"), 99, 102, 400], [100, 101, 99, 102, 400],
        [0, 103, 0, 102, 400], [100, 103, 99, 102, -1],
        [100, 103, 99, 102, 400],
    ]
    monkeypatch.setattr(market_chart, "_load_history", lambda *args: _frame(pd.DatetimeIndex(stamps, tz="UTC"), rows))
    result = market_chart.get_market_history("AAPL")
    assert [c["time"] for c in result["candles"]] == [1768226400, 1768230000]
    assert result["candles"][0]["close"] == 103
    assert result["as_of"] == "2026-01-12T15:00:00Z"


@pytest.mark.parametrize("frame", [
    None, pd.DataFrame(),
    pd.DataFrame({"Close": [100]}, index=pd.DatetimeIndex(["2026-01-12"], tz="UTC")),
    _frame(pd.DatetimeIndex(["2026-01-12 14:00"])),
    _frame(pd.DatetimeIndex(["2026-01-12 14:00"], tz="UTC"), [[100, 103, 99, 102, float("inf")]]),
])
def test_no_data_or_all_invalid_never_fabricates_a_bar(monkeypatch, frame):
    monkeypatch.setattr(market_chart, "_load_history", lambda *args: frame)
    result = market_chart.get_market_history("AAPL")
    assert result["candles"] == []
    assert result["as_of"] is None
    json.dumps(result, allow_nan=False)


def test_upstream_error_is_opaque(monkeypatch):
    def fail(*args):
        raise RuntimeError("secret-upstream-token-and-internal-url")
    monkeypatch.setattr(market_chart, "_load_history", fail)
    with pytest.raises(market_chart.MarketHistoryUnavailable) as caught:
        market_chart.get_market_history("AAPL")
    assert str(caught.value) == "Market history is temporarily unavailable."
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("ticker", ["AAPL", "brk-b", "^GSPC", "EURUSD=X", "7203.T"])
def test_supported_symbol_forms(ticker):
    assert market_chart.validate_history_request(ticker, "1mo", "1h") == ticker.upper()


@pytest.mark.parametrize("ticker", ["", "AAPL MSFT", "AAPL,MSFT", "../AAPL", "=AAPL", "*AAPL", "A" * 21, "AAPL?x=1", "ＡＡＰＬ"])
def test_rejects_symbol_injection_and_lists_before_provider(ticker):
    with pytest.raises(ValueError, match="ticker"):
        market_chart.get_market_history(ticker)


@pytest.mark.parametrize("window", [("max", "1m"), ("1y", "5m"), ("1mo", "1d"), ("1d", "1h")])
def test_unsupported_window_rejected_before_provider(window):
    with pytest.raises(ValueError, match="combination"):
        market_chart.get_market_history("AAPL", *window)


def test_provider_uses_raw_prices_bounded_timeout_and_no_adjusted_cache(monkeypatch):
    calls = []
    frame = _frame(pd.DatetimeIndex(["2026-01-12"], tz="America/New_York"))
    def history(**kwargs):
        calls.append(kwargs)
        return frame
    def ticker(symbol):
        assert symbol == "AAPL"
        return SimpleNamespace(history=history)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=ticker))
    result = _REAL_LOAD_HISTORY("AAPL", "3mo", "1d")
    assert result is frame
    assert calls == [{
        "period": "3mo", "interval": "1d", "auto_adjust": False,
        "back_adjust": False, "repair": False, "actions": False,
        "prepost": False, "timeout": 8, "raise_errors": True,
    }]


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    import api_server
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    return TestClient(api_server.app)


def test_http_daily_and_intraday_contract(client, monkeypatch):
    index = pd.DatetimeIndex(["2026-01-14 00:00"], tz="Asia/Tokyo")
    monkeypatch.setattr(market_chart, "_load_history", lambda *args: _frame(index))
    daily = client.get("/api/market-history/7203.T?period=3mo&interval=1d")
    assert daily.status_code == 200
    assert daily.json()["candles"][0]["time"] == "2026-01-14"
    assert daily.json()["as_of"] == "2026-01-13T15:00:00Z"
    intraday = client.get("/api/market-history/7203.T")
    assert intraday.status_code == 200
    assert intraday.json()["candles"][0]["time"] == 1768316400


@pytest.mark.parametrize("path", [
    "/api/market-history/AAPL,MSFT", "/api/market-history/" + "A" * 21,
    "/api/market-history/AAPL?period=1y&interval=5m",
])
def test_http_invalid_request_no_provider_calls(client, path):
    assert client.get(path).status_code == 422


def test_http_empty_response_is_distinct_from_provider_failure(client, monkeypatch):
    monkeypatch.setattr(market_chart, "_load_history", lambda *args: pd.DataFrame())
    empty = client.get("/api/market-history/AAPL")
    assert empty.status_code == 200
    assert empty.json()["candles"] == []
    def fail(*args):
        raise RuntimeError("private-provider-details")
    monkeypatch.setattr(market_chart, "_load_history", fail)
    failure = client.get("/api/market-history/AAPL")
    assert failure.status_code == 503
    assert failure.json() == {"detail": "Market history is temporarily unavailable."}
    assert "private-provider" not in failure.text


def test_http_demo_mode_never_calls_provider_or_returns_synthetic_prices(client, monkeypatch):
    import api_server
    monkeypatch.setattr(api_server, "DEMO_MODE", True)
    response = client.get("/api/market-history/AAPL")
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Market history is unavailable in demo mode; no synthetic candles are served.",
    }


def test_http_outer_deadline_returns_opaque_unavailable(client, monkeypatch):
    import asyncio
    async def timeout(coroutine, *, timeout):
        coroutine.close()
        raise TimeoutError("private-request-details")
    monkeypatch.setattr(asyncio, "wait_for", timeout)
    response = client.get("/api/market-history/AAPL")
    assert response.status_code == 503
    assert response.json() == {"detail": "Market history is temporarily unavailable."}


def test_chart_request_does_not_load_models_or_trading_engine(client, monkeypatch):
    import builtins
    original_import = builtins.__import__
    def read_only_import(name, *args, **kwargs):
        if name.startswith(("core.brain", "llm.", "engine.paper_trading", "brokers")):
            pytest.fail("Chart history must not initialize a model or trading engine")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", read_only_import)
    monkeypatch.setattr(market_chart, "_load_history", lambda *args: pd.DataFrame())
    response = client.get("/api/market-history/AAPL")
    assert response.status_code == 200
    assert response.json()["candles"] == []
