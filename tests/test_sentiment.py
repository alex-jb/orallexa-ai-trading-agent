"""Unit tests for engine/sentiment.py.

All tests use mocked inputs — no network, no model downloads. The active
backend (FinBERT / VADER / TextBlob / keyword fallback) is whichever is
installed locally; the contract is the same shape regardless.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from engine import sentiment


SHAPE_KEYS = {"compound", "label", "positive", "negative", "neutral"}
LABELS = {"positive", "neutral", "negative"}


class TestScoreText:
    def test_returns_full_shape(self):
        out = sentiment.score_text("Strong earnings beat expectations.")
        assert SHAPE_KEYS.issubset(out.keys())
        assert out["label"] in LABELS
        assert -1.0 <= out["compound"] <= 1.0

    def test_empty_input_returns_neutral(self):
        out = sentiment.score_text("")
        assert out["compound"] == 0.0
        assert out["label"] == "neutral"

    def test_whitespace_only_returns_neutral(self):
        out = sentiment.score_text("    \n  \t ")
        assert out["compound"] == 0.0
        assert out["label"] == "neutral"

    def test_strips_url_only_input_to_neutral(self):
        # After URL + punctuation stripping nothing meaningful remains.
        out = sentiment.score_text("https://example.com")
        assert out["compound"] == 0.0
        assert out["label"] == "neutral"


class TestKeywordFallback:
    """The keyword scorer is deterministic and covered without external deps."""

    def test_positive_keywords(self):
        out = sentiment._score_keywords("Earnings beat with record growth and upgrade")
        assert out["compound"] > 0
        assert out["label"] == "positive"

    def test_negative_keywords(self):
        out = sentiment._score_keywords("Earnings miss with bankruptcy lawsuit and downgrade")
        assert out["compound"] < 0
        assert out["label"] == "negative"

    def test_neutral_when_no_keywords(self):
        out = sentiment._score_keywords("the company reported quarterly results today")
        assert out["label"] == "neutral"


class TestAggregateSentiment:
    def test_empty_list_returns_neutral_envelope(self):
        agg = sentiment.aggregate_sentiment([])
        assert agg["avg_compound"] == 0.0
        assert agg["sentiment_label"] == "neutral"
        assert agg["n_positive"] == agg["n_negative"] == agg["n_neutral"] == 0
        assert agg["signal"] == "neutral"

    def test_aggregates_counts(self):
        items = [
            {"compound": 0.6, "label": "positive"},
            {"compound": 0.4, "label": "positive"},
            {"compound": -0.3, "label": "negative"},
            {"compound": 0.0, "label": "neutral"},
        ]
        agg = sentiment.aggregate_sentiment(items)
        assert agg["n_positive"] == 2
        assert agg["n_negative"] == 1
        assert agg["n_neutral"] == 1
        assert agg["total_items"] == 4
        assert -1.0 <= agg["avg_compound"] <= 1.0

    def test_strong_positive_emits_bullish_signal(self):
        items = [{"compound": 0.5, "label": "positive"} for _ in range(3)]
        agg = sentiment.aggregate_sentiment(items)
        assert agg["signal"] == "bullish"
        assert agg["sentiment_label"] == "positive"

    def test_strong_negative_emits_bearish_signal(self):
        items = [{"compound": -0.5, "label": "negative"} for _ in range(3)]
        agg = sentiment.aggregate_sentiment(items)
        assert agg["signal"] == "bearish"
        assert agg["sentiment_label"] == "negative"


class TestScoreNewsItems:
    def test_enriches_each_item_with_sentiment_fields(self):
        items = [
            {"title": "Beat earnings", "summary": "Record growth"},
            {"title": "Lawsuit risk", "summary": "Investigation announced"},
        ]
        scored = sentiment.score_news_items(items)
        assert len(scored) == 2
        for entry in scored:
            assert SHAPE_KEYS.issubset(entry.keys())
            # original keys preserved
            assert "title" in entry and "summary" in entry

    def test_empty_input_returns_empty_list(self):
        assert sentiment.score_news_items([]) == []

    def test_handles_missing_title_or_summary(self):
        scored = sentiment.score_news_items([{"title": "headline only"}, {"summary": "body only"}])
        assert len(scored) == 2
        assert all("compound" in s for s in scored)


class TestAnalyzeTickerSentiment:
    def test_no_news_returns_graceful_fallback(self):
        # No rag_store, no news_skill → should not crash, returns neutral envelope.
        out = sentiment.analyze_ticker_sentiment("NVDA")
        assert out["ticker"] == "NVDA"
        assert out["error"] == "No news found"
        assert out["avg_compound"] == 0.0
        assert out["sentiment_label"] == "neutral"
        assert out["signal"] == "neutral"
        assert out["scored_items"] == []

    def test_uses_rag_store_when_provided(self):
        rag = MagicMock()
        rag.list_documents.return_value = [
            {"title": "NVDA earnings beat", "text": "Record growth and upgrade"},
            {"title": "NVDA price target raised", "text": "Strong outlook bullish"},
        ]
        out = sentiment.analyze_ticker_sentiment("NVDA", rag_store=rag)
        assert out["ticker"] == "NVDA"
        assert out["error"] is None
        assert len(out["scored_items"]) == 2
        assert out["sentiment_label"] in LABELS

    def test_falls_back_to_news_skill_when_rag_empty(self):
        rag = MagicMock()
        rag.list_documents.return_value = []
        news = MagicMock()
        news.fetch_news.return_value = [
            {"title": "Earnings miss", "summary": "Bankruptcy concerns and downgrade"},
        ]
        out = sentiment.analyze_ticker_sentiment("XYZ", rag_store=rag, news_skill=news)
        assert out["error"] is None
        assert len(out["scored_items"]) == 1
        news.fetch_news.assert_called_once()

    def test_swallows_rag_exception_and_continues(self):
        rag = MagicMock()
        rag.list_documents.side_effect = RuntimeError("rag store offline")
        news = MagicMock()
        news.fetch_news.return_value = [{"title": "Beat", "summary": "Record growth"}]
        out = sentiment.analyze_ticker_sentiment("XYZ", rag_store=rag, news_skill=news)
        # rag failure must not crash; news_skill takes over.
        assert out["error"] is None
        assert len(out["scored_items"]) == 1

    def test_swallows_news_skill_exception_and_falls_back(self):
        news = MagicMock()
        news.fetch_news.side_effect = RuntimeError("news api 500")
        out = sentiment.analyze_ticker_sentiment("XYZ", news_skill=news)
        assert out["error"] == "No news found"
        assert out["signal"] == "neutral"

    def test_respects_limit(self):
        rag = MagicMock()
        rag.list_documents.return_value = [
            {"title": f"item {i}", "text": f"summary {i}"} for i in range(20)
        ]
        out = sentiment.analyze_ticker_sentiment("NVDA", rag_store=rag, limit=5)
        assert len(out["scored_items"]) == 5


class TestScorerType:
    def test_get_scorer_type_returns_string(self):
        # Trigger initialization by scoring something.
        sentiment.score_text("hello")
        assert isinstance(sentiment.get_scorer_type(), str)
        assert sentiment.get_scorer_type() in {"finbert", "vader", "textblob", "none"}
