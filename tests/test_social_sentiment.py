"""
tests/test_social_sentiment.py
──────────────────────────────────────────────────────────────────
Tests for skills/social_sentiment.py and its integration in
engine/signal_fusion.py (new 6th source).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from skills.social_sentiment import (
    fetch_reddit_posts,
    fetch_x_posts,
    analyze_social_sentiment,
    _aggregate,
)


# ── Mocks ──────────────────────────────────────────────────────────────────

def _reddit_response(posts: list[dict]) -> MagicMock:
    """Wrap a list of post-data dicts into a Reddit-API-shaped JSON response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": {"children": [{"data": p} for p in posts]}
    }
    return resp


def _reddit_post(
    title: str,
    text: str = "",
    score: int = 10,
    num_comments: int = 5,
    subreddit: str = "stocks",
) -> dict:
    return {
        "title": title,
        "selftext": text,
        "score": score,
        "num_comments": num_comments,
        "created_utc": 1_700_000_000.0,
        "url": f"https://reddit.com/r/{subreddit}",
    }


# ── fetch_reddit_posts ─────────────────────────────────────────────────────

class TestFetchRedditPosts:
    def test_returns_parsed_posts(self):
        posts = [_reddit_post("NVDA surges on earnings beat")]
        with patch("requests.get", return_value=_reddit_response(posts)):
            result = fetch_reddit_posts("NVDA", subreddits=("stocks",), limit=10)
        assert len(result) == 1
        assert result[0]["title"] == "NVDA surges on earnings beat"
        assert result[0]["score"] == 10
        assert result[0]["subreddit"] == "stocks"

    def test_empty_on_non_200(self):
        resp = MagicMock()
        resp.status_code = 403
        with patch("requests.get", return_value=resp):
            assert fetch_reddit_posts("NVDA") == []

    def test_empty_on_exception(self):
        with patch("requests.get", side_effect=RuntimeError("network")):
            assert fetch_reddit_posts("NVDA") == []

    def test_aggregates_across_subreddits(self):
        responses = [
            _reddit_response([_reddit_post("WSB NVDA YOLO", subreddit="wallstreetbets")]),
            _reddit_response([_reddit_post("NVDA analysis", subreddit="stocks")]),
            _reddit_response([_reddit_post("NVDA long-term", subreddit="investing")]),
        ]
        with patch("requests.get", side_effect=responses):
            result = fetch_reddit_posts(
                "NVDA",
                subreddits=("wallstreetbets", "stocks", "investing"),
                limit=30,
            )
        assert len(result) == 3
        subs = {p["subreddit"] for p in result}
        assert subs == {"wallstreetbets", "stocks", "investing"}

    def test_truncates_text(self):
        long_text = "x" * 2000
        with patch("requests.get", return_value=_reddit_response(
            [_reddit_post("title", text=long_text)]
        )):
            result = fetch_reddit_posts("NVDA", subreddits=("stocks",))
        assert len(result[0]["text"]) == 500


# ── fetch_x_posts ──────────────────────────────────────────────────────────

class TestFetchXPosts:
    def test_returns_empty_without_token(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TWITTER_BEARER_TOKEN", None)
            assert fetch_x_posts("NVDA") == []

    def test_uses_tweepy_when_token_set(self):
        tweet = MagicMock()
        tweet.id = 1234567
        tweet.text = "NVDA to the moon"
        tweet.public_metrics = {"like_count": 100, "retweet_count": 20, "reply_count": 5}
        tweet.created_at = None

        fake_resp = MagicMock()
        fake_resp.data = [tweet]
        fake_client = MagicMock()
        fake_client.search_recent_tweets.return_value = fake_resp

        with patch.dict(os.environ, {"TWITTER_BEARER_TOKEN": "t"}):
            with patch("tweepy.Client", return_value=fake_client):
                result = fetch_x_posts("NVDA", limit=10)

        assert len(result) == 1
        assert "NVDA" in result[0]["text"]
        assert result[0]["score"] == 120  # likes + retweets

    def test_empty_on_tweepy_error(self):
        with patch.dict(os.environ, {"TWITTER_BEARER_TOKEN": "t"}):
            with patch("tweepy.Client", side_effect=RuntimeError("api")):
                assert fetch_x_posts("NVDA") == []


# ── _aggregate ─────────────────────────────────────────────────────────────

class TestAggregate:
    def test_empty_posts(self):
        result = _aggregate([])
        assert result["available"] is False
        assert result["score"] == 0
        assert result["n_posts"] == 0

    def test_bullish_posts_positive_score(self):
        posts = [
            _reddit_post("NVDA beat earnings — huge rally surge", score=500, num_comments=100),
            _reddit_post("NVDA upgrade bullish growth strong", score=200, num_comments=50),
        ]
        result = _aggregate(posts)
        assert result["available"] is True
        assert result["n_posts"] == 2
        assert result["score"] > 0

    def test_bearish_posts_negative_score(self):
        posts = [
            _reddit_post("NVDA crash miss earnings lawsuit downgrade"),
            _reddit_post("NVDA bearish weakness decline"),
        ]
        result = _aggregate(posts)
        assert result["available"] is True
        assert result["score"] < 0

    def test_engagement_counted(self):
        posts = [_reddit_post("NVDA post", score=42, num_comments=17)]
        result = _aggregate(posts)
        assert result["engagement"] == 59


# ── analyze_social_sentiment (end-to-end) ─────────────────────────────────

class TestAnalyzeSocialSentiment:
    def test_integrates_reddit_and_x(self):
        reddit_posts = [_reddit_post("NVDA rally surge bullish")]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TWITTER_BEARER_TOKEN", None)
            with patch(
                "skills.social_sentiment.fetch_reddit_posts",
                return_value=reddit_posts,
            ):
                result = analyze_social_sentiment("NVDA")
        assert result["ticker"] == "NVDA"
        assert result["reddit"]["n"] == 1
        assert result["x"]["available"] is False
        assert result["available"] is True


# ── signal_fusion integration ──────────────────────────────────────────────

class TestSignalFusionIntegration:
    def test_social_source_added(self):
        from engine.signal_fusion import fuse_signals, DEFAULT_WEIGHTS
        assert "social_sentiment" in DEFAULT_WEIGHTS

        with patch("engine.signal_fusion._fetch_options_flow", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_institutional_signals", return_value={"available": False}), \
             patch(
                 "engine.signal_fusion._fetch_social_signal",
                 return_value={"available": True, "score": 40, "n_posts": 12,
                                "bullish": 8, "bearish": 2, "engagement": 300},
             ):
            result = fuse_signals(
                "NVDA",
                summary={"close": 100, "ma20": 95, "ma50": 90, "rsi": 55, "macd_hist": 0.05},
            )

        assert "social_sentiment" in result["sources"]
        assert result["sources"]["social_sentiment"]["available"] is True
        assert result["sources"]["social_sentiment"]["score"] == 40
        assert result["sources"]["social_sentiment"]["n_posts"] == 12

    def test_social_unavailable_weight_zero(self):
        from engine.signal_fusion import fuse_signals
        with patch("engine.signal_fusion._fetch_options_flow", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_institutional_signals", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_social_signal",
                   return_value={"available": False, "score": 0}):
            result = fuse_signals(
                "NVDA",
                summary={"close": 100, "ma20": 95, "ma50": 90, "rsi": 55},
            )
        assert result["sources"]["social_sentiment"]["weight"] == 0


# ── Earnings as 7th fusion source ──────────────────────────────────────────


class TestEarningsFusionSource:
    def test_earnings_source_registered(self):
        from engine.signal_fusion import DEFAULT_WEIGHTS
        assert "earnings" in DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["earnings"] > 0

    def test_earnings_inactive_when_far(self):
        from engine.signal_fusion import _fetch_earnings_signal
        with patch("engine.earnings.get_earnings_signal", return_value={
            "ticker": "NVDA",
            "next_date": "2026-08-01",
            "days_until": 60,
            "eps_estimate": 1.0,
            "pead": {"available": True, "avg_drift_5d": 2.0, "positive_rate": 0.7,
                     "surprise_drift_corr": 0.4, "n_events": 8},
            "narrative": "",
        }):
            sig = _fetch_earnings_signal("NVDA", proximity_days=30)
        assert sig["available"] is False
        assert sig["score"] == 0

    def test_earnings_bullish_drift_positive_score(self):
        from engine.signal_fusion import _fetch_earnings_signal
        with patch("engine.earnings.get_earnings_signal", return_value={
            "ticker": "NVDA",
            "next_date": "2026-05-01",
            "days_until": 5,
            "eps_estimate": 1.5,
            "pead": {"available": True, "avg_drift_5d": 3.0, "positive_rate": 0.8,
                     "surprise_drift_corr": 0.5, "n_events": 8},
            "narrative": "bullish drift",
        }):
            sig = _fetch_earnings_signal("NVDA")
        assert sig["available"] is True
        assert sig["score"] > 30
        assert sig["days_until"] == 5

    def test_earnings_bearish_drift_negative_score(self):
        from engine.signal_fusion import _fetch_earnings_signal
        with patch("engine.earnings.get_earnings_signal", return_value={
            "ticker": "NVDA",
            "next_date": "2026-05-01",
            "days_until": 2,
            "eps_estimate": 1.5,
            "pead": {"available": True, "avg_drift_5d": -2.5, "positive_rate": 0.3,
                     "surprise_drift_corr": -0.3, "n_events": 8},
            "narrative": "bearish drift",
        }):
            sig = _fetch_earnings_signal("NVDA")
        assert sig["available"] is True
        assert sig["score"] < -20

    def test_proximity_amplifies_score(self):
        from engine.signal_fusion import _fetch_earnings_signal

        def make_sig(days):
            return {
                "ticker": "NVDA", "next_date": "2026-05-01", "days_until": days,
                "eps_estimate": 1.5,
                "pead": {"available": True, "avg_drift_5d": 2.0, "positive_rate": 0.7,
                         "surprise_drift_corr": 0.0, "n_events": 8},
                "narrative": "",
            }

        with patch("engine.earnings.get_earnings_signal", return_value=make_sig(2)):
            close_sig = _fetch_earnings_signal("NVDA")
        with patch("engine.earnings.get_earnings_signal", return_value=make_sig(20)):
            far_sig = _fetch_earnings_signal("NVDA")

        assert abs(close_sig["score"]) > abs(far_sig["score"])

    def test_earnings_soon_but_no_pead(self):
        from engine.signal_fusion import _fetch_earnings_signal
        with patch("engine.earnings.get_earnings_signal", return_value={
            "ticker": "XYZ",
            "next_date": "2026-05-01",
            "days_until": 3,
            "eps_estimate": None,
            "pead": {"available": False, "n_events": 0},
            "narrative": "",
        }):
            sig = _fetch_earnings_signal("XYZ")
        assert sig["available"] is True
        assert sig["score"] == 0
        assert "no PEAD history" in sig.get("note", "")

    def test_fusion_integrates_earnings_source(self):
        from engine.signal_fusion import fuse_signals
        with patch("engine.signal_fusion._fetch_options_flow", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_institutional_signals", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_social_signal",
                   return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_earnings_signal", return_value={
                 "available": True, "score": 55, "days_until": 4,
                 "next_date": "2026-05-01", "avg_drift_5d": 2.3,
                 "positive_rate": 0.75, "narrative": "NVDA reports in 4 days",
             }):
            result = fuse_signals("NVDA", summary={"rsi": 55, "close": 100})
        assert "earnings" in result["sources"]
        assert result["sources"]["earnings"]["available"] is True
        assert result["sources"]["earnings"]["score"] == 55
        assert result["sources"]["earnings"]["days_until"] == 4
