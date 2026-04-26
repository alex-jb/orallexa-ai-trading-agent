"""
tests/test_provider.py
──────────────────────────────────────────────────────────────────
Tests for llm/provider.py — provider registry + routing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from llm.provider import (
    AnthropicProvider,
    ChatProvider,
    get_provider,
    current_provider_name,
    is_anthropic,
)


class TestRegistry:
    def test_default_is_anthropic(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORALEXXA_LLM_PROVIDER", None)
            p = get_provider()
        assert isinstance(p, AnthropicProvider)
        assert p.name == "anthropic"

    def test_explicit_anthropic(self):
        p = get_provider("anthropic")
        assert p.name == "anthropic"

    def test_unknown_provider_raises(self):
        with pytest.raises(KeyError):
            get_provider("nonexistent")

    def test_unimplemented_provider_complete_raises(self):
        p = get_provider("openai")
        with pytest.raises(NotImplementedError):
            p.complete(model="x", max_tokens=1, messages=[])

    def test_env_var_picks_provider(self):
        with patch.dict(os.environ, {"ORALEXXA_LLM_PROVIDER": "openai"}):
            p = get_provider()
        # OpenAI provider isn't implemented, but get_provider should still
        # resolve to its sentinel (calling complete is what raises)
        assert p.name == "unimplemented"

    def test_protocol_compliance(self):
        p = get_provider("anthropic")
        assert isinstance(p, ChatProvider)

    def test_current_provider_name(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORALEXXA_LLM_PROVIDER", None)
            assert current_provider_name() == "anthropic"
            assert is_anthropic() is True
        with patch.dict(os.environ, {"ORALEXXA_LLM_PROVIDER": "openai"}):
            assert is_anthropic() is False


class TestAnthropicProviderComplete:
    def test_delegates_to_logged_create(self):
        provider = AnthropicProvider()
        fake_client = MagicMock()
        with patch("llm.claude_client.get_client", return_value=fake_client), \
             patch("llm.call_logger.logged_create",
                   return_value=("response", "record")) as mock_lc:
            response, record = provider.complete(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": "hi"}],
                effort="xhigh",
                ticker="NVDA",
            )
        assert response == "response"
        assert record == "record"
        kw = mock_lc.call_args.kwargs
        assert kw["model"] == "claude-haiku-4-5-20251001"
        assert kw["effort"] == "xhigh"
        assert kw["ticker"] == "NVDA"

    def test_request_type_default(self):
        provider = AnthropicProvider()
        fake_client = MagicMock()
        with patch("llm.claude_client.get_client", return_value=fake_client), \
             patch("llm.call_logger.logged_create",
                   return_value=("response", "record")) as mock_lc:
            provider.complete(
                model="claude-sonnet-4-6", max_tokens=50,
                messages=[{"role": "user", "content": "hi"}],
            )
        assert mock_lc.call_args.kwargs["request_type"] == "complete"
