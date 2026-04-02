"""Tests for bot/x_publisher.py — X/Twitter API publisher."""
import pytest
from unittest.mock import patch, MagicMock

from bot.x_publisher import XPublisher, PostResult


class TestXPublisherInit:
    def test_missing_credentials_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            pub = XPublisher()
            with pytest.raises(ValueError, match="Missing X API credentials"):
                pub._get_client()

    def test_partial_credentials_lists_missing(self):
        env = {"X_API_KEY": "key", "X_API_SECRET": "secret"}
        with patch.dict("os.environ", env, clear=True):
            pub = XPublisher()
            with pytest.raises(ValueError, match="X_ACCESS_TOKEN"):
                pub._get_client()


class TestPostTweet:
    @patch("bot.x_publisher.tweepy.Client")
    def test_successful_post(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.create_tweet.return_value = MagicMock(data={"id": "123456"})
        mock_client_cls.return_value = mock_client

        env = {
            "X_API_KEY": "k", "X_API_SECRET": "s",
            "X_ACCESS_TOKEN": "t", "X_ACCESS_TOKEN_SECRET": "ts",
        }
        with patch.dict("os.environ", env):
            pub = XPublisher()
            result = pub.post_tweet("Hello world")

        assert result.success is True
        assert result.tweet_ids == ["123456"]
        mock_client.create_tweet.assert_called_once_with(text="Hello world")

    @patch("bot.x_publisher.tweepy.Client")
    def test_truncates_long_tweet(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.create_tweet.return_value = MagicMock(data={"id": "789"})
        mock_client_cls.return_value = mock_client

        env = {
            "X_API_KEY": "k", "X_API_SECRET": "s",
            "X_ACCESS_TOKEN": "t", "X_ACCESS_TOKEN_SECRET": "ts",
        }
        with patch.dict("os.environ", env):
            pub = XPublisher()
            long_text = "x" * 300
            result = pub.post_tweet(long_text)

        assert result.success is True
        call_args = mock_client.create_tweet.call_args
        assert len(call_args.kwargs["text"]) <= 280

    @patch("bot.x_publisher.tweepy.Client")
    def test_reply_to_passes_id(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.create_tweet.return_value = MagicMock(data={"id": "456"})
        mock_client_cls.return_value = mock_client

        env = {
            "X_API_KEY": "k", "X_API_SECRET": "s",
            "X_ACCESS_TOKEN": "t", "X_ACCESS_TOKEN_SECRET": "ts",
        }
        with patch.dict("os.environ", env):
            pub = XPublisher()
            pub.post_tweet("Reply", reply_to="123")

        mock_client.create_tweet.assert_called_once_with(
            text="Reply", in_reply_to_tweet_id="123",
        )


class TestPostThread:
    @patch("bot.x_publisher.tweepy.Client")
    def test_empty_thread_fails(self, mock_client_cls):
        env = {
            "X_API_KEY": "k", "X_API_SECRET": "s",
            "X_ACCESS_TOKEN": "t", "X_ACCESS_TOKEN_SECRET": "ts",
        }
        with patch.dict("os.environ", env):
            pub = XPublisher()
            result = pub.post_thread([])

        assert result.success is False
        assert "Empty thread" in result.errors

    @patch("bot.x_publisher.tweepy.Client")
    @patch("bot.x_publisher.time.sleep")
    def test_thread_chains_replies(self, mock_sleep, mock_client_cls):
        mock_client = MagicMock()
        call_count = [0]
        def make_tweet(**kwargs):
            call_count[0] += 1
            return MagicMock(data={"id": str(call_count[0])})
        mock_client.create_tweet.side_effect = make_tweet
        mock_client_cls.return_value = mock_client

        env = {
            "X_API_KEY": "k", "X_API_SECRET": "s",
            "X_ACCESS_TOKEN": "t", "X_ACCESS_TOKEN_SECRET": "ts",
        }
        with patch.dict("os.environ", env):
            pub = XPublisher()
            result = pub.post_thread(["Tweet 1", "Tweet 2", "Tweet 3"], delay_seconds=0)

        assert result.success is True
        assert len(result.tweet_ids) == 3
        # Second call should reply to first
        calls = mock_client.create_tweet.call_args_list
        assert calls[1].kwargs.get("in_reply_to_tweet_id") == "1"
        assert calls[2].kwargs.get("in_reply_to_tweet_id") == "2"


class TestPostSignalAlert:
    @patch("bot.x_publisher.tweepy.Client")
    def test_formats_signal_correctly(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.create_tweet.return_value = MagicMock(data={"id": "999"})
        mock_client_cls.return_value = mock_client

        env = {
            "X_API_KEY": "k", "X_API_SECRET": "s",
            "X_ACCESS_TOKEN": "t", "X_ACCESS_TOKEN_SECRET": "ts",
        }
        with patch.dict("os.environ", env):
            pub = XPublisher()
            result = pub.post_signal_alert("NVDA", "BUY", 75.0, "Strong momentum")

        assert result.success is True
        text = mock_client.create_tweet.call_args.kwargs["text"]
        assert "$NVDA" in text
        assert "BUY" in text
        assert "75%" in text
