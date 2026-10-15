"""News-analyst regressions: fake provider/backends, no downloads or API calls."""
from __future__ import annotations

import sys
import types
from unittest.mock import Mock

import pytest

from engine import sentiment
from engine.multi_agent_analysis import _run_news_analyst


def _article(title, **content):
    return {"content": {"title": title, **content}}


@pytest.fixture(autouse=True)
def offline_backends(monkeypatch):
    # Prevent the shared scorer from importing or downloading optional models.
    monkeypatch.setattr(sentiment, "_initialized", False)
    monkeypatch.setattr(sentiment, "_SCORER_TYPE", "none")
    monkeypatch.setattr(sentiment, "_SCORER", None)
    monkeypatch.setattr(sentiment, "_init_finbert", lambda: False)
    monkeypatch.setattr(sentiment, "_init_vader", lambda: False)
    monkeypatch.setattr(sentiment, "_init_textblob", lambda: False)


@pytest.fixture
def news_provider(monkeypatch):
    ticker = Mock()
    ticker.news = []
    provider = types.ModuleType("yfinance")
    provider.Ticker = Mock(return_value=ticker)
    monkeypatch.setitem(sys.modules, "yfinance", provider)
    return ticker


@pytest.mark.parametrize("title,expected,label", [
    ("Strong earnings beat expectations", 0.8, "bullish"),
    ("Weak earnings miss expectations", -0.8, "bearish"),
])
def test_calls_shared_finbert_instead_of_assuming_import_means_scored(
    monkeypatch, news_provider, title, expected, label,
):
    classifier = Mock(return_value=[
        {"label": "positive", "score": 0.9 if expected > 0 else 0.1},
        {"label": "negative", "score": 0.1 if expected > 0 else 0.9},
        {"label": "neutral", "score": 0.0},
    ])

    def initialize():
        monkeypatch.setattr(sentiment, "_SCORER", classifier)
        monkeypatch.setattr(sentiment, "_SCORER_TYPE", "finbert")
        return True

    monkeypatch.setattr(sentiment, "_init_finbert", initialize)
    news_provider.news = [_article(title)]
    report, items = _run_news_analyst("TEST")

    classifier.assert_called_once_with(title)
    assert items[0]["score"] == pytest.approx(expected)
    assert items[0]["sentiment"] == label
    assert items[0]["scorer"] == "finbert"
    assert f"**Overall Sentiment:** {label.title()}" in report


@pytest.mark.parametrize("title,label", [
    ("Earnings beat with record growth and upgrade", "bullish"),
    ("Earnings miss with bankruptcy lawsuit and downgrade", "bearish"),
    ("The company reported quarterly results today", "neutral"),
])
def test_missing_optional_backends_use_existing_keyword_fallback(news_provider, title, label):
    news_provider.news = [_article(title)]
    report, items = _run_news_analyst("TEST")
    assert items[0]["sentiment"] == label
    assert items[0]["score"] == sentiment._score_keywords(title)["compound"]
    assert items[0]["scorer"] == "keywords"
    assert "**Scoring backends:** keywords" in report


def test_runtime_finbert_fallback_reports_vader_after_scoring(monkeypatch, news_provider):
    broken_classifier = Mock(side_effect=RuntimeError("classifier unavailable"))
    monkeypatch.setattr(sentiment, "_initialized", True)
    monkeypatch.setattr(sentiment, "_SCORER_TYPE", "finbert")
    monkeypatch.setattr(sentiment, "_SCORER", broken_classifier)
    vader = Mock()
    vader.polarity_scores.return_value = {"compound": -0.7, "pos": 0.0, "neg": 0.7, "neu": 0.3}

    def initialize_vader():
        monkeypatch.setattr(sentiment, "_SCORER_TYPE", "vader")
        monkeypatch.setattr(sentiment, "_SCORER", vader)
        return True

    vader_module = types.ModuleType("vaderSentiment.vaderSentiment")
    vader_module.SentimentIntensityAnalyzer = Mock(return_value=vader)
    monkeypatch.setitem(sys.modules, "vaderSentiment.vaderSentiment", vader_module)
    monkeypatch.setattr(sentiment, "_init_vader", initialize_vader)
    news_provider.news = [_article("Company reports an earnings miss")]

    report, items = _run_news_analyst("TEST")
    assert items[0]["score"] == -0.7
    assert items[0]["sentiment"] == "bearish"
    assert items[0]["scorer"] == "vader"
    assert "**Scoring backends:** vader" in report


def test_runtime_finbert_failure_without_optional_fallbacks_uses_keywords(monkeypatch, news_provider):
    classifier = Mock(side_effect=RuntimeError("classifier unavailable"))
    monkeypatch.setattr(sentiment, "_initialized", True)
    monkeypatch.setattr(sentiment, "_SCORER_TYPE", "finbert")
    monkeypatch.setattr(sentiment, "_SCORER", classifier)
    news_provider.news = [_article("Company reports bankruptcy and earnings miss")]

    report, items = _run_news_analyst("TEST")

    classifier.assert_called_once()
    assert items[0]["score"] < 0
    assert items[0]["sentiment"] == "bearish"
    assert items[0]["scorer"] == "keywords"
    assert sentiment.get_scorer_type() == "none"
    assert sentiment._SCORER is None
    assert "**Scoring backends:** keywords" in report


def test_runtime_finbert_failure_can_fall_through_vader_to_textblob(monkeypatch, news_provider):
    classifier = Mock(side_effect=RuntimeError("classifier unavailable"))
    monkeypatch.setattr(sentiment, "_initialized", True)
    monkeypatch.setattr(sentiment, "_SCORER_TYPE", "finbert")
    monkeypatch.setattr(sentiment, "_SCORER", classifier)
    textblob = types.ModuleType("textblob")
    blob = Mock(return_value=types.SimpleNamespace(sentiment=types.SimpleNamespace(polarity=-0.6)))
    textblob.TextBlob = blob
    monkeypatch.setitem(sys.modules, "textblob", textblob)

    def initialize_textblob():
        monkeypatch.setattr(sentiment, "_SCORER_TYPE", "textblob")
        monkeypatch.setattr(sentiment, "_SCORER", blob)
        return True

    monkeypatch.setattr(sentiment, "_init_textblob", initialize_textblob)
    news_provider.news = [_article("Company publishes quarterly operating results")]

    report, items = _run_news_analyst("TEST")

    classifier.assert_called_once()
    blob.assert_called_once_with("Company publishes quarterly operating results")
    assert items[0]["score"] == -0.6
    assert items[0]["sentiment"] == "bearish"
    assert items[0]["scorer"] == "textblob"
    assert sentiment.get_scorer_type() == "textblob"
    assert "**Scoring backends:** textblob" in report


def test_unexpected_backend_error_uses_keywords_and_keeps_other_articles(monkeypatch, news_provider):
    original_score = sentiment.score_text

    def flaky_score(text):
        if "bankruptcy" in text:
            raise RuntimeError("backend failure")
        return original_score(text)

    monkeypatch.setattr(sentiment, "score_text", flaky_score)
    news_provider.news = [
        _article("Company bankruptcy and earnings miss"),
        _article("Company reports record profit growth"),
    ]
    _, items = _run_news_analyst("TEST")
    assert [item["sentiment"] for item in items] == ["bearish", "bullish"]
    assert all(item["scorer"] == "keywords" for item in items)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), 2.0, True, None])
def test_invalid_backend_scores_do_not_enter_signal_fusion(monkeypatch, news_provider, invalid):
    monkeypatch.setattr(sentiment, "score_text", lambda text: {"compound": invalid})
    news_provider.news = [_article("Company reports record earnings beat")]
    _, items = _run_news_analyst("TEST")
    assert items[0]["score"] == 1.0
    assert items[0]["scorer"] == "keywords"


def test_preserves_provided_url_publication_and_provider(news_provider):
    news_provider.news = [_article(
        "Company reports record earnings beat",
        provider={"displayName": "Example Wire"},
        canonicalUrl={"url": "https://example.test/news/earnings"},
        pubDate="2026-10-15T14:00:00Z",
    )]
    report, items = _run_news_analyst("TEST")
    assert items[0]["url"] == "https://example.test/news/earnings"
    assert items[0]["published"] == "2026-10-15T14:00:00Z"
    assert items[0]["provider"] == "Example Wire"
    assert "(Example Wire)" in report


def test_summary_is_scored_and_missing_source_is_not_invented(news_provider):
    news_provider.news = [_article(
        "Company reports quarterly results",
        summary="Bankruptcy lawsuit and earnings miss",
    )]
    _, items = _run_news_analyst("TEST")
    assert items[0]["sentiment"] == "bearish"
    assert items[0]["url"] == ""
    assert items[0]["published"] is None
    assert items[0]["provider"] == ""


@pytest.mark.parametrize("raw", [[], None, [None, {}, {"content": None}, {"content": []}, _article("short")]])
def test_empty_or_malformed_news_does_not_invent_neutral_articles(news_provider, raw):
    news_provider.news = raw
    report, items = _run_news_analyst("TEST")
    assert items == []
    assert report == "No recent news available for TEST."
    assert not sentiment._initialized


def test_provider_failure_keeps_existing_graceful_unavailable_contract(news_provider):
    type(news_provider).news = property(lambda self: (_ for _ in ()).throw(RuntimeError("offline")))
    report, items = _run_news_analyst("TEST")
    assert items == []
    assert report == "No recent news available for TEST."
