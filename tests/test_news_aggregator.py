"""
tests/test_news_aggregator.py
──────────────────────────────────────────────────────────────────
Tests for engine/news_aggregator.py — RSS parsing + dedupe logic.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.news_aggregator import (
    fetch_aggregated_news,
    _parse_rss,
    _normalize_title,
    _provider_rank,
    _dedupe_and_rank,
    _parse_pub_date,
)


def _rss_bytes(items: list[dict]) -> bytes:
    """Build a minimal RSS 2.0 XML document for testing."""
    item_xml = ""
    for it in items:
        src = f"<source>{it['source']}</source>" if it.get("source") else ""
        pub = f"<pubDate>{it['pub']}</pubDate>" if it.get("pub") else ""
        item_xml += (
            f"<item><title>{it['title']}</title><link>{it['link']}</link>"
            f"{pub}{src}</item>"
        )
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        f"{item_xml}"
        "</channel></rss>"
    ).encode("utf-8")


def _mock_resp(body: bytes, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.content = body
    return r


# ── _normalize_title ───────────────────────────────────────────────────────


class TestNormalizeTitle:
    def test_lowercase_and_strip_punctuation(self):
        assert _normalize_title("NVDA Beats Earnings!") == "nvda beats earnings"

    def test_strips_publisher_tail(self):
        n = _normalize_title("NVDA beats on revenue - Reuters")
        assert "reuters" not in n

    def test_collapses_whitespace(self):
        assert _normalize_title("NVDA   beats   earnings") == "nvda beats earnings"


# ── _provider_rank ─────────────────────────────────────────────────────────


class TestProviderRank:
    def test_tier1(self):
        assert _provider_rank("Reuters") == 3
        assert _provider_rank("Bloomberg Terminal") == 3
        assert _provider_rank("The Wall Street Journal") == 3

    def test_tier2(self):
        assert _provider_rank("CNBC") == 2
        assert _provider_rank("MarketWatch") == 2

    def test_tier3(self):
        assert _provider_rank("Yahoo Finance") == 1
        assert _provider_rank("Benzinga") == 1

    def test_unknown(self):
        assert _provider_rank("Random Blog") == 0


# ── _parse_pub_date ────────────────────────────────────────────────────────


class TestParsePubDate:
    def test_rfc_2822(self):
        dt = _parse_pub_date("Thu, 24 Apr 2026 12:00:00 GMT")
        assert dt is not None
        assert dt.year == 2026 and dt.month == 4 and dt.day == 24

    def test_iso(self):
        dt = _parse_pub_date("2026-04-24T12:00:00Z")
        assert dt is not None

    def test_garbage_returns_none(self):
        assert _parse_pub_date("not a date") is None

    def test_empty_returns_none(self):
        assert _parse_pub_date("") is None


# ── _parse_rss ─────────────────────────────────────────────────────────────


class TestParseRss:
    def test_basic_items(self):
        xml = _rss_bytes([
            {"title": "NVDA beats earnings", "link": "https://reuters.com/a",
             "pub": "Thu, 24 Apr 2026 12:00:00 GMT", "source": "Reuters"},
        ])
        items = _parse_rss(xml, source="google_news")
        assert len(items) == 1
        assert items[0]["provider"] == "Reuters"
        assert items[0]["title"] == "NVDA beats earnings"

    def test_extracts_provider_from_title_tail(self):
        xml = _rss_bytes([
            {"title": "NVDA beats - Bloomberg", "link": "https://example.com/a"},
        ])
        items = _parse_rss(xml, source="google_news")
        assert items[0]["provider"] == "Bloomberg"

    def test_extracts_provider_from_url_fallback(self):
        xml = _rss_bytes([
            {"title": "Plain title no tail", "link": "https://www.cnbc.com/article"},
        ])
        items = _parse_rss(xml, source="google_news")
        assert items[0]["provider"] == "cnbc"

    def test_skips_items_missing_fields(self):
        xml = _rss_bytes([
            {"title": "", "link": "https://a.com"},
            {"title": "Valid", "link": ""},
        ])
        items = _parse_rss(xml, source="x")
        assert items == []

    def test_empty_on_parse_error(self):
        assert _parse_rss(b"<not xml", source="x") == []


# ── _dedupe_and_rank ───────────────────────────────────────────────────────


class TestDedupeAndRank:
    def _item(self, title: str, provider: str = "random",
             pub: str = "Thu, 24 Apr 2026 12:00:00 GMT",
             source: str = "google_news") -> dict:
        return {
            "title": title,
            "url": f"https://{provider.lower().replace(' ', '')}.com/1",
            "provider": provider,
            "published": pub,
            "source": source,
        }

    def test_keeps_distinct(self):
        items = [
            self._item("NVDA beats earnings"),
            self._item("AAPL launches new phone"),
        ]
        assert len(_dedupe_and_rank(items, limit=10)) == 2

    def test_dedupes_near_identical(self):
        items = [
            self._item("NVIDIA beats Q2 earnings on AI demand"),
            self._item("NVIDIA beats Q2 earnings on AI demand - Reuters",
                       provider="Reuters"),
        ]
        out = _dedupe_and_rank(items, limit=10)
        assert len(out) == 1
        assert out[0]["provider"] == "Reuters"  # higher rank wins

    def test_tier1_wins_collision(self):
        items = [
            self._item("NVDA beats earnings this quarter with strong guidance",
                       provider="Random Blog"),
            self._item("NVDA beats earnings this quarter with strong guidance",
                       provider="Bloomberg"),
        ]
        out = _dedupe_and_rank(items, limit=10)
        assert len(out) == 1
        assert out[0]["provider"] == "Bloomberg"

    def test_sorted_newest_first(self):
        items = [
            self._item("Old news item about NVDA semis",
                       pub="Thu, 01 Apr 2026 12:00:00 GMT"),
            self._item("New news item about NVDA chips",
                       pub="Thu, 24 Apr 2026 12:00:00 GMT"),
        ]
        out = _dedupe_and_rank(items, limit=10)
        assert out[0]["title"].startswith("New")

    def test_skips_too_short_titles(self):
        items = [self._item("Hi")]
        assert _dedupe_and_rank(items, limit=10) == []

    def test_respects_limit(self):
        items = [self._item(f"Distinct story number {i} about semis") for i in range(20)]
        assert len(_dedupe_and_rank(items, limit=5)) == 5


# ── fetch_aggregated_news (integration) ────────────────────────────────────


class TestFetchAggregatedNews:
    def test_combines_google_and_yahoo(self):
        google_xml = _rss_bytes([
            {"title": "NVDA surges on AI", "link": "https://reuters.com/a",
             "pub": "Thu, 24 Apr 2026 12:00:00 GMT", "source": "Reuters"},
        ])
        yahoo_xml = _rss_bytes([
            {"title": "Apple iPhone 17 launch", "link": "https://yahoo.com/b",
             "pub": "Thu, 24 Apr 2026 10:00:00 GMT"},
        ])

        def fake_get(url, **kwargs):
            if "google" in url:
                return _mock_resp(google_xml)
            if "yahoo" in url:
                return _mock_resp(yahoo_xml)
            return _mock_resp(b"", status=404)

        with patch("requests.get", side_effect=fake_get):
            result = fetch_aggregated_news("NVDA", limit=10)

        assert len(result) == 2
        sources = {r["source"] for r in result}
        assert sources == {"google_news", "yahoo_finance"}

    def test_empty_when_all_sources_fail(self):
        with patch("requests.get", return_value=_mock_resp(b"", status=500)):
            assert fetch_aggregated_news("NVDA") == []

    def test_empty_on_network_exception(self):
        with patch("requests.get", side_effect=RuntimeError("net")):
            assert fetch_aggregated_news("NVDA") == []
