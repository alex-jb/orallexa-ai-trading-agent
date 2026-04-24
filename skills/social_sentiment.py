"""
skills/social_sentiment.py
──────────────────────────────────────────────────────────────────
Social sentiment aggregator — Reddit (public JSON) + optional X/Twitter.

Reddit is always available (no auth). X/Twitter is used only when
TWITTER_BEARER_TOKEN is set, via tweepy.

Each post is scored using the existing FinBERT/VADER pipeline in
engine/sentiment.py, then aggregated into a conviction score.

Usage:
    from skills.social_sentiment import analyze_social_sentiment
    result = analyze_social_sentiment("NVDA", reddit_limit=25, x_limit=25)
    print(result["score"])          # -100..+100
    print(result["reddit"])         # per-source breakdown
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")
_REDDIT_UA = "oralexxa/1.0 (social sentiment aggregator)"


def fetch_reddit_posts(
    ticker: str,
    subreddits: tuple[str, ...] = DEFAULT_SUBREDDITS,
    limit: int = 25,
) -> list[dict]:
    """
    Fetch recent Reddit posts mentioning the ticker from the public JSON API.
    No authentication required. Returns [] on any failure.

    Each item: {title, text, score, num_comments, subreddit, created_utc, url}.
    """
    try:
        import requests
    except ImportError:
        return []

    posts: list[dict] = []
    per_sub = max(1, limit // len(subreddits))
    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/search.json"
            params = {
                "q": ticker,
                "sort": "new",
                "restrict_sr": "on",
                "limit": per_sub,
                "t": "week",
            }
            resp = requests.get(
                url, params=params,
                headers={"User-Agent": _REDDIT_UA},
                timeout=5.0,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for child in data.get("data", {}).get("children", []):
                d = child.get("data", {})
                posts.append({
                    "title": d.get("title", ""),
                    "text": d.get("selftext", "")[:500],
                    "score": int(d.get("score", 0)),
                    "num_comments": int(d.get("num_comments", 0)),
                    "subreddit": sub,
                    "created_utc": float(d.get("created_utc", 0)),
                    "url": d.get("url", ""),
                })
        except Exception as e:
            logger.debug("Reddit fetch failed for r/%s: %s", sub, e)
            continue
    return posts[:limit]


def fetch_x_posts(ticker: str, limit: int = 25) -> list[dict]:
    """
    Fetch recent X/Twitter posts mentioning $TICKER via tweepy.
    Requires TWITTER_BEARER_TOKEN. Returns [] if unavailable.
    """
    token = os.environ.get("TWITTER_BEARER_TOKEN")
    if not token:
        return []
    try:
        import tweepy
        client = tweepy.Client(bearer_token=token)
        query = f"${ticker} -is:retweet lang:en"
        resp = client.search_recent_tweets(
            query=query,
            max_results=min(max(limit, 10), 100),
            tweet_fields=["public_metrics", "created_at"],
        )
        tweets = resp.data or []
        out = []
        for t in tweets:
            metrics = t.public_metrics or {}
            out.append({
                "title": t.text[:120],
                "text": t.text,
                "score": metrics.get("like_count", 0) + metrics.get("retweet_count", 0),
                "num_comments": metrics.get("reply_count", 0),
                "subreddit": "x",
                "created_utc": t.created_at.timestamp() if t.created_at else 0.0,
                "url": f"https://x.com/i/status/{t.id}",
            })
        return out
    except Exception as e:
        logger.debug("X fetch failed for %s: %s", ticker, e)
        return []


def _aggregate(posts: list[dict]) -> dict:
    """Score each post with engine.sentiment and aggregate into conviction."""
    if not posts:
        return {
            "available": False,
            "score": 0,
            "n_posts": 0,
            "bullish": 0,
            "bearish": 0,
            "neutral": 0,
            "engagement": 0,
        }
    from engine.sentiment import score_news_items, aggregate_sentiment

    scored = score_news_items(posts)
    agg = aggregate_sentiment(scored)

    # engagement-weighted compound score: upweight posts with more votes/comments
    weighted_sum = 0.0
    weight_total = 0.0
    for item in scored:
        w = 1.0 + min(item.get("score", 0), 1000) / 100.0 + min(item.get("num_comments", 0), 500) / 100.0
        weighted_sum += item.get("compound", 0.0) * w
        weight_total += w
    w_avg = weighted_sum / weight_total if weight_total > 0 else 0.0

    score = int(max(-100, min(100, w_avg * 200)))
    engagement = int(sum(p.get("score", 0) + p.get("num_comments", 0) for p in posts))
    return {
        "available": True,
        "score": score,
        "avg_compound": agg.get("avg_compound", 0.0),
        "weighted_compound": round(w_avg, 4),
        "n_posts": len(scored),
        "bullish": agg.get("n_positive", 0),
        "bearish": agg.get("n_negative", 0),
        "neutral": agg.get("n_neutral", 0),
        "engagement": engagement,
        "scorer": agg.get("scorer", "unknown"),
    }


def analyze_social_sentiment(
    ticker: str,
    reddit_limit: int = 25,
    x_limit: int = 25,
    subreddits: Optional[tuple[str, ...]] = None,
) -> dict:
    """
    Fetch + aggregate Reddit and X posts. Returns a unified conviction dict
    compatible with signal_fusion.py (fields: available, score).
    """
    subs = subreddits or DEFAULT_SUBREDDITS
    reddit_posts = fetch_reddit_posts(ticker, subreddits=subs, limit=reddit_limit)
    x_posts = fetch_x_posts(ticker, limit=x_limit)

    all_posts = reddit_posts + x_posts
    agg = _aggregate(all_posts)

    agg["reddit"] = {
        "n": len(reddit_posts),
        "breakdown_by_subreddit": _count_by_sub(reddit_posts),
    }
    agg["x"] = {"n": len(x_posts), "available": bool(os.environ.get("TWITTER_BEARER_TOKEN"))}
    agg["ticker"] = ticker
    return agg


def _count_by_sub(posts: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for p in posts:
        sub = p.get("subreddit", "unknown")
        counts[sub] = counts.get(sub, 0) + 1
    return counts
