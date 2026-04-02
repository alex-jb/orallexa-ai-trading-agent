"""
bot/x_publisher.py
--------------------------------------------------------------------
X/Twitter API v2 publisher for Orallexa.

Posts tweets, threads, and daily intel to X using tweepy.
Requires OAuth 1.0a credentials (User Authentication) for posting.

Setup:
    1. Go to https://developer.x.com/en/portal/dashboard
    2. Create a project + app with Read and Write permissions
    3. Generate OAuth 1.0a keys (Consumer Keys + Access Token)
    4. Set env vars: X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

Usage:
    from bot.x_publisher import XPublisher
    pub = XPublisher()
    pub.post_tweet("Hello from Orallexa!")
    pub.post_thread(["Tweet 1", "Tweet 2", "Tweet 3"])
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import List, Optional

import tweepy

logger = logging.getLogger("bot.x_publisher")


@dataclass
class PostResult:
    success: bool
    tweet_ids: List[str]
    errors: List[str]


class XPublisher:
    """Publish tweets and threads to X/Twitter via API v2."""

    def __init__(self):
        self._client: Optional[tweepy.Client] = None

    def _get_client(self) -> tweepy.Client:
        """Lazy-init authenticated tweepy Client."""
        if self._client is not None:
            return self._client

        api_key = os.environ.get("X_API_KEY", "")
        api_secret = os.environ.get("X_API_SECRET", "")
        access_token = os.environ.get("X_ACCESS_TOKEN", "")
        access_secret = os.environ.get("X_ACCESS_TOKEN_SECRET", "")

        if not all([api_key, api_secret, access_token, access_secret]):
            missing = []
            if not api_key: missing.append("X_API_KEY")
            if not api_secret: missing.append("X_API_SECRET")
            if not access_token: missing.append("X_ACCESS_TOKEN")
            if not access_secret: missing.append("X_ACCESS_TOKEN_SECRET")
            raise ValueError(
                f"Missing X API credentials: {', '.join(missing)}. "
                "Set them in .env or as environment variables. "
                "Get keys at https://developer.x.com/en/portal/dashboard"
            )

        self._client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        return self._client

    def verify_credentials(self) -> dict:
        """Verify X API credentials and return account info."""
        client = self._get_client()
        me = client.get_me(user_fields=["username", "name", "public_metrics"])
        if me.data is None:
            raise ValueError("Could not verify X credentials. Check your API keys.")
        return {
            "id": me.data.id,
            "username": me.data.username,
            "name": me.data.name,
            "followers": me.data.public_metrics.get("followers_count", 0) if me.data.public_metrics else 0,
        }

    def post_tweet(self, text: str, reply_to: str | None = None) -> PostResult:
        """
        Post a single tweet.

        Args:
            text: Tweet text (max 280 chars).
            reply_to: Optional tweet ID to reply to (for threads).

        Returns:
            PostResult with tweet ID on success.
        """
        if len(text) > 280:
            logger.warning("Tweet exceeds 280 chars (%d), truncating", len(text))
            text = text[:277] + "..."

        try:
            client = self._get_client()
            kwargs = {"text": text}
            if reply_to:
                kwargs["in_reply_to_tweet_id"] = reply_to

            response = client.create_tweet(**kwargs)
            tweet_id = str(response.data["id"])
            logger.info("Posted tweet %s: %s", tweet_id, text[:50])
            return PostResult(success=True, tweet_ids=[tweet_id], errors=[])

        except tweepy.TweepyException as exc:
            logger.error("Failed to post tweet: %s", exc)
            return PostResult(success=False, tweet_ids=[], errors=[str(exc)])

    def post_thread(self, tweets: List[str], delay_seconds: float = 2.0) -> PostResult:
        """
        Post a thread (sequential tweets as replies).

        Args:
            tweets: List of tweet texts. Each should be <=280 chars.
            delay_seconds: Delay between posts to avoid rate limits.

        Returns:
            PostResult with all tweet IDs.
        """
        if not tweets:
            return PostResult(success=False, tweet_ids=[], errors=["Empty thread"])

        tweet_ids = []
        errors = []
        reply_to = None

        for i, text in enumerate(tweets):
            result = self.post_tweet(text, reply_to=reply_to)

            if result.success:
                tweet_ids.extend(result.tweet_ids)
                reply_to = result.tweet_ids[0]
            else:
                errors.extend(result.errors)
                logger.error("Thread stopped at tweet %d/%d: %s", i + 1, len(tweets), result.errors)
                break

            # Delay between posts (skip after last)
            if i < len(tweets) - 1:
                time.sleep(delay_seconds)

        return PostResult(
            success=len(tweet_ids) == len(tweets),
            tweet_ids=tweet_ids,
            errors=errors,
        )

    def post_daily_intel(self, intel_data: dict) -> PostResult:
        """
        Post daily intel social content to X.

        Expects intel_data with 'social_posts' dict containing:
            movers, sectors, picks, brief, volume

        Posts the morning brief as a standalone tweet.
        """
        social = intel_data.get("social_posts", {})
        if not social:
            return PostResult(success=False, tweet_ids=[], errors=["No social posts in intel data"])

        # Post morning brief as the main tweet
        brief = social.get("brief", "")
        if brief:
            return self.post_tweet(brief)

        return PostResult(success=False, tweet_ids=[], errors=["No brief post available"])

    def post_signal_alert(self, ticker: str, decision: str, confidence: float, reasoning: str = "") -> PostResult:
        """
        Post a trading signal alert.

        Args:
            ticker: Stock ticker (e.g., NVDA).
            decision: BUY/SELL/WAIT.
            confidence: Confidence percentage.
            reasoning: One-line reasoning.
        """
        emoji = {"BUY": "🟢", "SELL": "🔴", "WAIT": "🟡"}.get(decision, "⚪")
        text = f"{emoji} ${ticker} Signal: {decision} ({confidence:.0f}% confidence)"
        if reasoning:
            remaining = 280 - len(text) - 3  # 3 for "\n\n"
            if remaining > 20:
                text += f"\n\n{reasoning[:remaining]}"
        text += "\n\n@orallexatrading"
        return self.post_tweet(text)
