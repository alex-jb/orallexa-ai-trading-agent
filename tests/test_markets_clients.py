"""tests/test_markets_clients.py
─────────────────────────────────────────────────────────────
Parser tests for Kalshi + Polymarket read-only clients.

No network. Each test feeds a hand-built fixture matching the actual
JSON shape returned by the respective API and asserts the BinaryMarket
fields it parses out. If the parser silently drops a field these
tests catch it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from markets.market import BinaryMarket
from markets.kalshi_client import (
    parse_market as parse_kalshi_market,
    parse_history as parse_kalshi_history,
    _category_from_event_ticker,
)
from markets.polymarket_client import (
    parse_market as parse_poly_market,
    parse_history as parse_poly_history,
)


# ════════════════════════════════════════════════════════════════════════
# KALSHI
# ════════════════════════════════════════════════════════════════════════


def _kalshi_fixture_open() -> dict:
    return {
        "ticker": "POTUS-2028-DEM",
        "event_ticker": "POTUS-2028",
        "title": "Will a Democrat win the 2028 US Presidential Election?",
        "subtitle": "Resolves YES if a Democratic nominee wins.",
        "status": "active",
        "open_time": "2026-01-15T00:00:00Z",
        "close_time": "2028-11-07T23:59:59Z",
        "expiration_time": "2028-12-01T00:00:00Z",
        "last_price": 47,          # cents
        "yes_bid": 46,
        "yes_ask": 48,
        "volume": 12345,
        "open_interest": 4321,
        "result": "",              # unresolved
        "rules_primary": "Resolves based on the 2028 EC outcome.",
    }


def _kalshi_fixture_settled_yes() -> dict:
    return {
        "ticker": "KXFED-26MAR-50",
        "event_ticker": "KXFED",
        "title": "Will the Fed hold rates at the March 2026 FOMC?",
        "status": "settled",
        "settled_time": "2026-03-19T18:30:00Z",
        "last_price": 100,
        "result": "yes",
    }


def _kalshi_fixture_settled_no() -> dict:
    f = _kalshi_fixture_settled_yes()
    f["result"] = "no"
    f["last_price"] = 0
    return f


def test_kalshi_parse_open_market():
    m = parse_kalshi_market(_kalshi_fixture_open())
    assert m.platform == "kalshi"
    assert m.market_id == "POTUS-2028-DEM"
    assert m.ticker == "POTUS-2028-DEM"
    assert m.category == "politics"
    assert m.status == "open"
    assert m.yes_price == 0.47          # 47 cents → 0.47
    assert m.yes_bid == 0.46
    assert m.yes_ask == 0.48
    assert m.volume == 12345
    assert m.open_interest == 4321
    assert m.outcome is None
    assert m.is_closed is False
    assert m.is_resolved is False


def test_kalshi_parse_settled_yes():
    m = parse_kalshi_market(_kalshi_fixture_settled_yes())
    assert m.status == "settled"
    assert m.outcome == 1
    assert m.is_closed is True
    assert m.is_resolved is True


def test_kalshi_parse_settled_no():
    m = parse_kalshi_market(_kalshi_fixture_settled_no())
    assert m.outcome == 0
    assert m.is_resolved is True


def test_kalshi_category_buckets():
    cases = {
        "POTUS-2028": "politics",
        "SENATE-NY": "politics",
        "KXFED-MAY": "economics",
        "CPI-2026Q3": "economics",
        "NBA-LAL-WIN": "sports",
        "BTC-200K": "crypto",
        "HIGH-NYC-MAY12": "weather",
        "ZZZ-UNKNOWN": "other",
    }
    for et, expected in cases.items():
        assert _category_from_event_ticker(et) == expected, et


def test_kalshi_parse_history():
    fixture = {
        "history": [
            {"ts": 1700000000, "yes_price": 35},
            {"ts": 1700003600, "yes_price": 42},
            {"ts": 1700007200, "yes_price": None},   # skipped
            {"ts": None, "yes_price": 50},            # skipped
        ]
    }
    ticks = parse_kalshi_history(fixture)
    assert len(ticks) == 2
    assert ticks[0].t == 1700000000
    assert ticks[0].yes == 0.35
    assert ticks[1].yes == 0.42


def test_kalshi_parse_handles_missing_optional_fields():
    minimal = {"ticker": "X-1", "event_ticker": "X", "status": "active"}
    m = parse_kalshi_market(minimal)
    assert m.market_id == "X-1"
    assert m.question == "X-1"      # falls back to ticker
    assert m.yes_price is None
    assert m.volume == 0.0


# ════════════════════════════════════════════════════════════════════════
# POLYMARKET
# ════════════════════════════════════════════════════════════════════════


def _poly_fixture_open() -> dict:
    return {
        "conditionId": "0xabc123",
        "slug": "iran-deal-by-july-2026",
        "question": "Will the US and Iran reach a deal by July 1, 2026?",
        "category": "Geopolitics",
        "active": True,
        "closed": False,
        "archived": False,
        "startDate": "2026-04-01T00:00:00Z",
        "endDate": "2026-07-01T23:59:59Z",
        "umaResolutionDate": "2026-07-02T00:00:00Z",
        "lastTradePrice": 0.42,
        "bestBid": 0.41,
        "bestAsk": 0.43,
        "volumeNum": 1_234_567.89,
        "liquidity": 50_000,
        "outcomePrices": '["0.42", "0.58"]',     # JSON-string, not list
        "description": "Resolves YES if a formal deal is signed by July 1.",
    }


def _poly_fixture_settled_yes() -> dict:
    return {
        "conditionId": "0xdef456",
        "slug": "tx-bill-passes",
        "question": "Will Bill X pass by end of session?",
        "category": "Politics",
        "active": False,
        "closed": True,
        "archived": False,
        "endDate": "2026-04-15T23:59:59Z",
        "resolvedDate": "2026-04-16T03:12:00Z",
        "outcomePrices": '["1", "0"]',
        "description": "Resolves YES if the bill passes.",
    }


def _poly_fixture_settled_no() -> dict:
    f = _poly_fixture_settled_yes()
    f["conditionId"] = "0x000999"
    f["outcomePrices"] = '["0", "1"]'
    return f


def test_polymarket_parse_open_market():
    m = parse_poly_market(_poly_fixture_open())
    assert m.platform == "polymarket"
    assert m.market_id == "0xabc123"
    assert m.ticker == "iran-deal-by-july-2026"
    assert m.category == "geopolitics"
    assert m.status == "open"
    assert m.yes_price == 0.42
    assert m.yes_bid == 0.41
    assert m.yes_ask == 0.43
    assert m.volume == 1_234_567.89
    assert m.open_interest == 50_000
    assert m.outcome is None
    assert m.is_resolved is False


def test_polymarket_parse_settled_yes():
    m = parse_poly_market(_poly_fixture_settled_yes())
    assert m.status == "settled"
    assert m.outcome == 1
    assert m.is_resolved is True


def test_polymarket_parse_settled_no():
    m = parse_poly_market(_poly_fixture_settled_no())
    assert m.outcome == 0


def test_polymarket_parse_outcome_handles_list_and_string():
    # Gamma sometimes returns outcomePrices as a real list, not a JSON-string.
    f = _poly_fixture_settled_yes()
    f["outcomePrices"] = ["1", "0"]
    assert parse_poly_market(f).outcome == 1


def test_polymarket_parse_ambiguous_outcome_returns_none():
    f = _poly_fixture_settled_yes()
    f["outcomePrices"] = '["0.5", "0.5"]'   # weird; treat as unresolved
    assert parse_poly_market(f).outcome is None


def test_polymarket_parse_history():
    fixture = {
        "history": [
            {"t": 1700000000, "p": 0.30},
            {"t": 1700003600, "p": 0.41},
            {"t": 1700007200, "p": None},     # skipped
        ]
    }
    ticks = parse_poly_history(fixture)
    assert len(ticks) == 2
    assert ticks[0].t == 1700000000
    assert ticks[0].yes == 0.30
    assert ticks[1].yes == 0.41


def test_polymarket_parse_handles_missing_optional_fields():
    minimal = {
        "conditionId": "0x000",
        "slug": "minimal",
        "active": True,
        "closed": False,
    }
    m = parse_poly_market(minimal)
    assert m.market_id == "0x000"
    assert m.question == "minimal"
    assert m.yes_price is None
    assert m.volume == 0.0


# ════════════════════════════════════════════════════════════════════════
# CROSS-PLATFORM SANITY
# ════════════════════════════════════════════════════════════════════════


def test_both_platforms_produce_same_dataclass():
    k = parse_kalshi_market(_kalshi_fixture_open())
    p = parse_poly_market(_poly_fixture_open())
    assert isinstance(k, BinaryMarket)
    assert isinstance(p, BinaryMarket)
    # Same downstream interface so debate/queue/sizing don't branch on platform
    assert k.to_dict().keys() == p.to_dict().keys()
