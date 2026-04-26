"""
tests/test_kalshi_markets.py
──────────────────────────────────────────────────────────────────
Tests for skills/prediction_markets — Kalshi adapter + multi-platform
aggregation in analyze_prediction_markets.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from skills.prediction_markets import (
    fetch_kalshi_markets,
    analyze_prediction_markets,
)


def _kalshi_resp(markets: list[dict], cursor: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"markets": markets, "cursor": cursor}
    return resp


def _kalshi_market(
    title: str,
    yes_bid: int = 40,
    yes_ask: int = 60,
    *,
    close_time: str = "2026-12-31T23:59:59Z",
    volume_24h: float = 5000.0,
    ticker: str = "",
) -> dict:
    return {
        "title": title,
        "subtitle": "",
        "ticker": ticker,
        "yes_sub_title": "",
        "no_sub_title": "",
        "rules_primary": "",
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "close_time": close_time,
        "volume_24h": volume_24h,
        "liquidity": 1000.0,
    }


# ── fetch_kalshi_markets ───────────────────────────────────────────────────


class TestFetchKalshi:
    def test_returns_matching_markets(self):
        markets = [
            _kalshi_market("Will NVDA beat earnings?", yes_bid=70, yes_ask=80),
            _kalshi_market("Will the Yankees win game 7?"),  # unrelated
        ]
        with patch("requests.get", return_value=_kalshi_resp(markets)):
            result = fetch_kalshi_markets("NVDA", limit=5)
        assert len(result) == 1
        assert "NVDA" in result[0]["question"]
        # yes_mid = (70+80)/200 = 0.75
        assert result[0]["yes_price"] == pytest.approx(0.75)
        assert result[0]["platform"] == "kalshi"

    def test_filters_closed_markets(self):
        markets = [_kalshi_market("Will NVDA hit $200?",
                                    close_time="2024-01-01T00:00:00Z")]
        with patch("requests.get", return_value=_kalshi_resp(markets)):
            assert fetch_kalshi_markets("NVDA") == []

    def test_skips_invalid_prices(self):
        markets = [_kalshi_market("Will NVDA rally?",
                                    yes_bid=-50, yes_ask=200)]
        with patch("requests.get", return_value=_kalshi_resp(markets)):
            assert fetch_kalshi_markets("NVDA") == []

    def test_empty_on_non_200(self):
        resp = MagicMock()
        resp.status_code = 500
        with patch("requests.get", return_value=resp):
            assert fetch_kalshi_markets("NVDA") == []

    def test_empty_on_exception(self):
        with patch("requests.get", side_effect=RuntimeError("net")):
            assert fetch_kalshi_markets("NVDA") == []

    def test_pagination_terminates_when_limit_reached(self):
        # Single page returning 200 matches — should still cap at limit
        many = [_kalshi_market(f"Will NVDA hit ${i}?") for i in range(100, 200)]
        with patch("requests.get", return_value=_kalshi_resp(many)):
            result = fetch_kalshi_markets("NVDA", limit=3)
        assert len(result) == 3


# ── analyze_prediction_markets — multi-platform ────────────────────────────


class TestAnalyzeMultiPlatform:
    def test_combines_polymarket_and_kalshi(self):
        # Mock Polymarket via the existing _yes_index path: stub
        # fetch_polymarket_markets to return one item; stub Kalshi too.
        poly_market = {
            "question": "Will NVDA beat earnings?", "yes_price": 0.7,
            "volume_24hr": 50_000, "liquidity": 5_000,
            "end_date": "2026-12-31", "sign": 1, "platform": "polymarket",
        }
        kalshi_market = {
            "question": "Will NVDA reach $200?", "yes_price": 0.6,
            "volume_24hr": 10_000, "liquidity": 1_000,
            "end_date": "2026-12-31", "sign": 1, "platform": "kalshi",
        }
        with patch("skills.prediction_markets.fetch_polymarket_markets",
                   return_value=[poly_market]), \
             patch("skills.prediction_markets.fetch_kalshi_markets",
                   return_value=[kalshi_market]):
            r = analyze_prediction_markets("NVDA")
        assert r["available"] is True
        assert r["n_markets"] == 2
        assert r["n_by_platform"]["polymarket"] == 1
        assert r["n_by_platform"]["kalshi"] == 1
        assert r["score"] > 0  # both bullish

    def test_kalshi_disabled(self):
        poly_market = {
            "question": "Will NVDA beat?", "yes_price": 0.7,
            "volume_24hr": 50_000, "liquidity": 5_000,
            "end_date": "2026-12-31", "sign": 1, "platform": "polymarket",
        }
        kalshi_called = {"n": 0}

        def fake_kalshi(*args, **kwargs):
            kalshi_called["n"] += 1
            return []

        with patch("skills.prediction_markets.fetch_polymarket_markets",
                   return_value=[poly_market]), \
             patch("skills.prediction_markets.fetch_kalshi_markets",
                   side_effect=fake_kalshi):
            r = analyze_prediction_markets("NVDA", include_kalshi=False)
        assert kalshi_called["n"] == 0
        assert "kalshi" not in r.get("n_by_platform", {})

    def test_kalshi_failure_doesnt_break_polymarket(self):
        poly_market = {
            "question": "Will NVDA rally?", "yes_price": 0.65,
            "volume_24hr": 25_000, "liquidity": 2_500,
            "end_date": "2026-12-31", "sign": 1, "platform": "polymarket",
        }
        with patch("skills.prediction_markets.fetch_polymarket_markets",
                   return_value=[poly_market]), \
             patch("skills.prediction_markets.fetch_kalshi_markets",
                   side_effect=RuntimeError("kalshi down")):
            r = analyze_prediction_markets("NVDA")
        assert r["available"] is True
        assert r["n_markets"] == 1
        assert r["n_by_platform"]["polymarket"] == 1
