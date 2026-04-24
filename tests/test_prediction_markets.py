"""
tests/test_prediction_markets.py
──────────────────────────────────────────────────────────────────
Tests for skills/prediction_markets.py and its integration in
engine/signal_fusion.py (new 8th source).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from skills.prediction_markets import (
    fetch_polymarket_markets,
    analyze_prediction_markets,
    _bullish_sign,
    _yes_index,
)


# ── Mock helpers ───────────────────────────────────────────────────────────


def _future_iso(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _past_iso(days: int = 10) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _market(
    question: str,
    yes_price: float = 0.5,
    *,
    volume_24hr: float = 10_000.0,
    end_date: str | None = None,
    closed: bool = False,
    archived: bool = False,
    active: bool = True,
    outcomes: list[str] | None = None,
) -> dict:
    outcomes = outcomes or ["Yes", "No"]
    return {
        "question": question,
        "outcomes": json.dumps(outcomes),
        "outcomePrices": json.dumps([str(yes_price), str(round(1 - yes_price, 4))]),
        "volume24hr": volume_24hr,
        "liquidity": 5000.0,
        "endDate": end_date or _future_iso(30),
        "endDateIso": (end_date or _future_iso(30))[:10],
        "active": active,
        "closed": closed,
        "archived": archived,
    }


def _search_response(markets: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"events": [{"markets": markets}]}
    return resp


# ── _bullish_sign ──────────────────────────────────────────────────────────


class TestBullishSign:
    def test_bullish_keywords(self):
        assert _bullish_sign("Will NVDA beat earnings?") == 1
        assert _bullish_sign("Will NVDA reach $200?") == 1
        assert _bullish_sign("Will stocks rally?") == 1

    def test_bearish_keywords(self):
        assert _bullish_sign("Will NVDA miss earnings?") == -1
        assert _bullish_sign("Will NVDA crash below $100?") == -1
        assert _bullish_sign("Will market decline?") == -1

    def test_ambiguous(self):
        assert _bullish_sign("Who becomes CEO?") == 0
        assert _bullish_sign("") == 0


# ── _yes_index ─────────────────────────────────────────────────────────────


class TestYesIndex:
    def test_explicit_yes(self):
        assert _yes_index(["Yes", "No"]) == 0
        assert _yes_index(["No", "Yes"]) == 1

    def test_binary_fallback(self):
        assert _yes_index(["Google", "NVIDIA"]) == 0

    def test_unknown(self):
        assert _yes_index(["A", "B", "C"]) is None


# ── fetch_polymarket_markets ───────────────────────────────────────────────


class TestFetchPolymarketMarkets:
    def test_parses_active_market(self):
        markets = [_market("Will NVDA beat earnings?", yes_price=0.72)]
        with patch("requests.get", return_value=_search_response(markets)):
            result = fetch_polymarket_markets("NVDA", limit=5)
        assert len(result) == 1
        assert result[0]["yes_price"] == 0.72
        assert result[0]["sign"] == 1
        assert result[0]["volume_24hr"] == 10_000.0

    def test_skips_closed_and_archived(self):
        markets = [
            _market("Will NVDA beat earnings?", closed=True),
            _market("Will NVDA miss earnings?", archived=True),
            _market("Will NVDA reach $200?", active=False),
        ]
        with patch("requests.get", return_value=_search_response(markets)):
            assert fetch_polymarket_markets("NVDA") == []

    def test_skips_past_end_date(self):
        markets = [_market("Will NVDA beat?", end_date=_past_iso(10))]
        with patch("requests.get", return_value=_search_response(markets)):
            assert fetch_polymarket_markets("NVDA") == []

    def test_empty_on_non_200(self):
        resp = MagicMock()
        resp.status_code = 500
        with patch("requests.get", return_value=resp):
            assert fetch_polymarket_markets("NVDA") == []

    def test_empty_on_exception(self):
        with patch("requests.get", side_effect=RuntimeError("net")):
            assert fetch_polymarket_markets("NVDA") == []

    def test_rejects_malformed_prices(self):
        bad = _market("Will NVDA beat?")
        bad["outcomePrices"] = '["abc", "def"]'
        with patch("requests.get", return_value=_search_response([bad])):
            assert fetch_polymarket_markets("NVDA") == []

    def test_limit_enforced(self):
        markets = [_market(f"Will NVDA hit ${n}?") for n in range(20)]
        with patch("requests.get", return_value=_search_response(markets)):
            result = fetch_polymarket_markets("NVDA", limit=3)
        assert len(result) == 3


# ── analyze_prediction_markets ─────────────────────────────────────────────


class TestAnalyzePredictionMarkets:
    def test_unavailable_when_no_markets(self):
        with patch("requests.get", return_value=_search_response([])):
            r = analyze_prediction_markets("XYZ")
        assert r["available"] is False
        assert r["score"] == 0
        assert r["n_markets"] == 0

    def test_bullish_consensus_positive_score(self):
        markets = [
            _market("Will NVDA beat earnings?", yes_price=0.75, volume_24hr=50_000),
            _market("Will NVDA reach new highs?", yes_price=0.70, volume_24hr=30_000),
        ]
        with patch("requests.get", return_value=_search_response(markets)):
            r = analyze_prediction_markets("NVDA")
        assert r["available"] is True
        assert r["score"] > 30
        assert r["n_directional"] == 2

    def test_bearish_consensus_negative_score(self):
        markets = [
            _market("Will NVDA miss earnings?", yes_price=0.70, volume_24hr=40_000),
            _market("Will NVDA crash below $100?", yes_price=0.60, volume_24hr=20_000),
        ]
        with patch("requests.get", return_value=_search_response(markets)):
            r = analyze_prediction_markets("NVDA")
        assert r["available"] is True
        assert r["score"] < -20

    def test_ambiguous_markets_no_score_but_available(self):
        markets = [_market("Who becomes NVDA next CEO?", yes_price=0.55)]
        with patch("requests.get", return_value=_search_response(markets)):
            r = analyze_prediction_markets("NVDA")
        assert r["available"] is True
        assert r["score"] == 0
        assert r["n_directional"] == 0
        assert "unclear" in r.get("note", "")

    def test_volume_weighting(self):
        # Two bullish markets, high-volume one more bullish
        markets = [
            _market("Will NVDA beat earnings?", yes_price=0.90, volume_24hr=1_000_000),
            _market("Will NVDA rise?", yes_price=0.55, volume_24hr=100),
        ]
        with patch("requests.get", return_value=_search_response(markets)):
            r = analyze_prediction_markets("NVDA")
        # Score should be pulled heavily toward the high-volume market
        assert r["score"] > 50


# ── signal_fusion integration ──────────────────────────────────────────────


class TestSignalFusionIntegration:
    def test_prediction_markets_source_added(self):
        from engine.signal_fusion import DEFAULT_WEIGHTS
        assert "prediction_markets" in DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["prediction_markets"] > 0

    def test_fusion_integrates_prediction_markets(self):
        from engine.signal_fusion import fuse_signals
        with patch("engine.signal_fusion._fetch_options_flow", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_institutional_signals", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_social_signal", return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_earnings_signal", return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_prediction_markets_signal", return_value={
                 "available": True, "score": 48, "n_markets": 4, "n_directional": 3,
                 "total_volume_24hr": 125_000,
                 "markets": [
                     {"question": "Will NVDA beat Q2?", "yes_price": 0.78,
                      "volume_24hr": 50_000, "end_date": "2026-05-28", "sign": 1},
                 ],
             }):
            result = fuse_signals("NVDA", summary={"rsi": 55, "close": 100})
        assert "prediction_markets" in result["sources"]
        assert result["sources"]["prediction_markets"]["available"] is True
        assert result["sources"]["prediction_markets"]["score"] == 48
        assert result["sources"]["prediction_markets"]["n_markets"] == 4

    def test_weight_zero_when_unavailable(self):
        from engine.signal_fusion import fuse_signals
        with patch("engine.signal_fusion._fetch_options_flow", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_institutional_signals", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_social_signal", return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_earnings_signal", return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_prediction_markets_signal",
                   return_value={"available": False, "score": 0}):
            result = fuse_signals("NVDA", summary={"rsi": 55, "close": 100})
        assert result["sources"]["prediction_markets"]["weight"] == 0
