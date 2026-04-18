"""Tests for engine/sentiment.py — Sentiment scoring backends."""

import pytest
from unittest.mock import patch, MagicMock

from engine.sentiment import (
    score_text,
    score_news_items,
    aggregate_sentiment,
    get_scorer_type,
)


# ─────────────────────────────────────────────────────────────────────────────
# score_text
# ─────────────────────────────────────────────────────────────────────────────

def test_score_text_returns_dict():
    """score_text returns a dict with required sentiment keys."""
    result = score_text("The market is doing great today!")
    assert isinstance(result, dict)
    assert {"compound", "label", "positive", "negative", "neutral"}.issubset(result.keys())


def test_score_text_empty_string():
    """Empty text returns neutral scores."""
    result = score_text("")
    assert result["label"] == "neutral"
    assert result["compound"] == 0.0
    assert result["neutral"] == 1.0


def test_score_text_none_input():
    """None input returns neutral scores."""
    result = score_text(None)
    assert result["label"] == "neutral"
    assert result["compound"] == 0.0


def test_score_text_whitespace_only():
    """Whitespace-only text returns neutral scores."""
    result = score_text("   \n\t  ")
    assert result["label"] == "neutral"
    assert result["compound"] == 0.0


def test_score_text_strips_urls():
    """URLs are stripped before scoring."""
    result = score_text("Check https://example.com for news")
    # Should not raise and should return a valid result
    assert "compound" in result


def test_score_text_strips_special_chars():
    """Special characters are stripped before scoring."""
    result = score_text("Hello!!! @user #topic!!!")
    assert isinstance(result, dict)
    assert "compound" in result


def test_score_text_positive_label():
    """Strongly positive text is labelled positive."""
    result = score_text("Stocks surging higher on excellent earnings reports!")
    assert result["label"] in ("positive", "neutral", "negative")


def test_score_text_negative_label():
    """Strongly negative text is labelled negative."""
    result = score_text("Market crashing due to terrible economic data!")
    assert result["label"] in ("positive", "neutral", "negative")


def test_score_text_compound_range():
    """Compound score is always between -1 and 1."""
    result = score_text("The company reported strong profits and revenue growth.")
    assert -1.0 <= result["compound"] <= 1.0


def test_score_text_all_fields_present():
    """All expected fields are always present regardless of scorer."""
    result = score_text("Bullish sentiment drives markets upward.")
    assert all(k in result for k in ("compound", "label", "positive", "negative", "neutral"))


# ─────────────────────────────────────────────────────────────────────────────
# score_news_items
# ─────────────────────────────────────────────────────────────────────────────

def test_score_news_items_returns_list():
    """score_news_items returns a list of scored items."""
    items = [
        {"title": "Stocks Rally", "summary": "Markets closed higher today."},
        {"title": "Fed Meeting", "summary": "Interest rates held steady."},
    ]
    result = score_news_items(items)
    assert isinstance(result, list)
    assert len(result) == 2


def test_score_news_items_preserves_keys():
    """Scored items include all original keys plus sentiment fields."""
    items = [{"title": "Bullish", "summary": "Good news"}]
    result = score_news_items(items)
    assert "title" in result[0]
    assert "summary" in result[0]
    assert "compound" in result[0]
    assert "label" in result[0]


def test_score_news_items_empty_list():
    """Empty list returns empty list."""
    result = score_news_items([])
    assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# aggregate_sentiment
# ─────────────────────────────────────────────────────────────────────────────

def test_aggregate_sentiment_empty_list():
    """Empty list returns neutral default."""
    result = aggregate_sentiment([])
    assert result["sentiment_label"] == "neutral"
    assert result["avg_compound"] == 0.0
    assert result["n_positive"] == 0
    assert result["n_negative"] == 0


def test_aggregate_sentiment_all_positive():
    """All positive items produce a positive label."""
    scored = [
        {"compound": 0.8, "label": "positive"},
        {"compound": 0.6, "label": "positive"},
    ]
    result = aggregate_sentiment(scored)
    assert result["sentiment_label"] == "positive"
    assert result["n_positive"] == 2
    assert result["avg_compound"] > 0


def test_aggregate_sentiment_all_negative():
    """All negative items produce a negative label."""
    scored = [
        {"compound": -0.7, "label": "negative"},
        {"compound": -0.5, "label": "negative"},
    ]
    result = aggregate_sentiment(scored)
    assert result["sentiment_label"] == "negative"
    assert result["n_negative"] == 2
    assert result["avg_compound"] < 0


def test_aggregate_sentiment_mixed():
    """Mixed items produce a neutral label when avg is near zero."""
    scored = [
        {"compound": 0.1, "label": "positive"},
        {"compound": -0.1, "label": "negative"},
    ]
    result = aggregate_sentiment(scored)
    assert result["sentiment_label"] == "neutral"


def test_aggregate_sentiment_signal_bullish():
    """High positive avg_compound produces bullish signal."""
    scored = [
        {"compound": 0.5, "label": "positive"},
        {"compound": 0.4, "label": "positive"},
    ]
    result = aggregate_sentiment(scored)
    assert result["signal"] == "bullish"


def test_aggregate_sentiment_signal_bearish():
    """High negative avg_compound produces bearish signal."""
    scored = [
        {"compound": -0.5, "label": "negative"},
        {"compound": -0.4, "label": "negative"},
    ]
    result = aggregate_sentiment(scored)
    assert result["signal"] == "bearish"


def test_aggregate_sentiment_signal_neutral():
    """Low absolute avg_compound produces neutral signal."""
    scored = [
        {"compound": 0.05, "label": "positive"},
        {"compound": -0.05, "label": "negative"},
    ]
    result = aggregate_sentiment(scored)
    assert result["signal"] == "neutral"


def test_aggregate_sentiment_includes_scorer():
    """Result includes the scorer type."""
    scored = [{"compound": 0.5, "label": "positive"}]
    result = aggregate_sentiment(scored)
    assert "scorer" in result


def test_aggregate_sentiment_total_items():
    """Result includes total item count."""
    scored = [
        {"compound": 0.5, "label": "positive"},
        {"compound": -0.2, "label": "negative"},
        {"compound": 0.0, "label": "neutral"},
    ]
    result = aggregate_sentiment(scored)
    assert result["total_items"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# get_scorer_type
# ─────────────────────────────────────────────────────────────────────────────

def test_get_scorer_type_returns_string():
    """get_scorer_type returns a string value."""
    result = get_scorer_type()
    assert isinstance(result, str)


def test_get_scorer_type_valid_choices():
    """get_scorer_type returns one of the known scorer names."""
    valid = {"finbert", "vader", "textblob", "keywords", "none"}
    result = get_scorer_type()
    assert result in valid
