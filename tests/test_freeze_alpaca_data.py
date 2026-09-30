"""Synthetic-only checks for the GET-only Alpaca historical snapshot path."""

from io import BytesIO
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from eval import freeze_alpaca_data as freezer


START, END = "2021-01-01", "2026-09-28"


def bar(day, price=100.0):
    return {"t": day, "o": price, "h": price + 2, "l": price - 2,
            "c": price + 1, "v": 123456}


FIRST = bar("2021-01-04T05:00:00Z")
LAST = bar("2026-09-28T04:00:00Z", 120)


def paged(ticker, token):
    if token is None:
        return {"bars": {ticker: [FIRST]}, "next_page_token": "second"}
    assert token == "second"
    return {"bars": {ticker: [LAST]}, "next_page_token": None}


def test_paginates_and_freezes_complete_cohort_with_auditable_hashes(tmp_path):
    out = tmp_path / "alpaca-private"
    manifest = freezer.freeze_alpaca_data(
        paged, out, tickers=("NVDA", "META"), start=START, end=END, min_bars=2
    )
    assert sorted(p.name for p in out.iterdir()) == ["META.csv", "NVDA.csv", "manifest.json"]
    assert manifest["protocol_id"] == freezer.PROTOCOL_IDS["iex"]
    assert manifest["parameters"]["adjustment"] == "split,dividend"
    assert manifest["parameters"]["feed"] == "iex"
    assert manifest["parameters"]["asof"] == END
    assert manifest["parameters"]["requested_end_utc"] == "2026-09-29T00:00:00Z"
    assert manifest["parameters"]["last_session_required"] == END
    assert manifest["sha256"]["META"] == hashlib.sha256((out / "META.csv").read_bytes()).hexdigest()
    assert "2021-01-04" in (out / "META.csv").read_text()
    assert "2026-09-28" in (out / "META.csv").read_text()
    assert json.loads((out / "manifest.json").read_text())["rows_per_ticker"] == {"NVDA": 2, "META": 2}


def test_default_cohort_requires_all_ten_symbols_before_output(tmp_path):
    out = tmp_path / "ten"
    manifest = freezer.freeze_alpaca_data(paged, out, min_bars=2)
    assert manifest["tickers"] == list(freezer.TICKERS)
    assert len(manifest["sha256"]) == 10
    assert len(list(out.glob("*.csv"))) == 10


@pytest.mark.parametrize("broken", [
    lambda t, token: {"bars": {t: [FIRST]}, "next_page_token": "again"},
    lambda t, token: {"bars": {t: [FIRST, FIRST, LAST]}},
    lambda t, token: {"bars": {t: [FIRST]}},
    lambda t, token: {"bars": {t: [FIRST, {**LAST, "c": float("nan")}]}},
    lambda t, token: {"bars": {"unexpected": [FIRST, LAST]}},
])
def test_invalid_or_incomplete_response_leaves_no_snapshot(tmp_path, broken):
    out = tmp_path / "private"
    with pytest.raises((ValueError, AssertionError)):
        freezer.freeze_alpaca_data(broken, out, tickers=("NVDA",), min_bars=2)
    assert not out.exists()
    assert not list(tmp_path.glob(".alpaca-freeze-*"))


def test_second_ticker_failure_never_writes_partial_data(tmp_path):
    out = tmp_path / "private"

    def failing_second(ticker, token):
        if ticker == "META":
            raise RuntimeError("synthetic feed failure")
        return paged(ticker, token)

    with pytest.raises(RuntimeError, match="synthetic"):
        freezer.freeze_alpaca_data(failing_second, out, tickers=("NVDA", "META"), min_bars=2)
    assert not out.exists()


def test_existing_target_is_never_overwritten_or_fetched(tmp_path):
    out = tmp_path / "private"
    out.mkdir()
    (out / "sentinel").write_text("keep")
    with pytest.raises(FileExistsError):
        freezer.freeze_alpaca_data(lambda *_: pytest.fail("should not fetch"), out)
    assert (out / "sentinel").read_text() == "keep"


def test_inside_repo_only_ignored_private_path_is_allowed():
    repo = Path(freezer.__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="ignored"):
        freezer._private_target(repo / "eval/snapshots/public-alpaca")
    assert freezer._private_target(repo / "eval/private_snapshots/alpaca-example")


def test_http_client_sends_read_only_get_with_fixed_market_data_parameters(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return BytesIO(json.dumps({"bars": {"META": []}, "next_page_token": None}).encode())

    monkeypatch.setattr(freezer, "urlopen", fake_urlopen)
    result = freezer.make_http_fetcher("synthetic-paper-key", "synthetic-secret")("META", "next")
    assert result["bars"] == {"META": []}
    request, timeout = calls[0]
    assert request.get_method() == "GET"
    assert urlsplit(request.full_url).netloc == "data.alpaca.markets"
    assert urlsplit(request.full_url).path == "/v2/stocks/bars"
    query = parse_qs(urlsplit(request.full_url).query)
    assert {k: v[0] for k, v in query.items()} == {
        "symbols": "META", "timeframe": "1Day", "start": START,
        "end": "2026-09-29T00:00:00Z", "limit": "10000", "adjustment": "split,dividend",
        "feed": "iex", "asof": END, "sort": "asc", "page_token": "next",
    }
    assert timeout == 20
    assert request.get_header("Apca-api-key-id") == "synthetic-paper-key"
    assert request.get_header("Apca-api-secret-key") == "synthetic-secret"


def test_missing_credentials_fail_before_network():
    with pytest.raises(ValueError, match="ALPACA_API_KEY"):
        freezer.make_http_fetcher("", "")


def test_sip_is_separate_protocol_and_unauthorized_feed_fails_closed(monkeypatch, tmp_path):
    manifest = freezer.freeze_alpaca_data(paged, tmp_path / "sip", tickers=("META",), min_bars=2, feed="sip")
    assert manifest["protocol_id"] == freezer.PROTOCOL_IDS["sip"]
    assert manifest["parameters"]["feed"] == "sip"

    def forbidden(*args, **kwargs):
        raise HTTPError("https://data.alpaca.markets/v2/stocks/bars", 403, "Forbidden", {}, None)

    monkeypatch.setattr(freezer, "urlopen", forbidden)
    with pytest.raises(PermissionError, match="sip data feed is not authorized"):
        freezer.make_http_fetcher("synthetic-key", "synthetic-secret", feed="sip")("META", None)
