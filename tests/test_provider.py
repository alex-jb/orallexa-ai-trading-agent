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
    OpenAIProvider,
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
        p = get_provider("gemini")  # gemini still a placeholder
        with pytest.raises(NotImplementedError):
            p.complete(model="x", max_tokens=1, messages=[])

    def test_env_var_picks_provider(self):
        with patch.dict(os.environ, {"ORALEXXA_LLM_PROVIDER": "gemini"}):
            p = get_provider()
        # Gemini still a placeholder
        assert p.name == "unimplemented"

    def test_openai_provider_resolves(self):
        p = get_provider("openai")
        assert isinstance(p, OpenAIProvider)
        assert p.name == "openai"

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


class TestOpenAIProvider:
    def _fake_openai_response(self, content="hello", in_tok=10, out_tok=20):
        choice = MagicMock()
        choice.message.content = content
        usage = MagicMock()
        usage.prompt_tokens = in_tok
        usage.completion_tokens = out_tok
        raw = MagicMock()
        raw.choices = [choice]
        raw.usage = usage
        return raw

    def test_complete_translates_response_shape(self):
        provider = OpenAIProvider()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = self._fake_openai_response(
            content="generated text", in_tok=42, out_tok=17
        )
        provider._client = fake_client
        response, record = provider.complete(
            model="gpt-5-mini",
            max_tokens=200,
            messages=[{"role": "user", "content": "hi"}],
            ticker="NVDA",
        )
        # Response surface matches Anthropic shape
        assert response.content[0].type == "text"
        assert response.content[0].text == "generated text"
        assert response.usage.input_tokens == 42
        assert response.usage.output_tokens == 17
        # Record has all the same fields as Anthropic LLMCallRecord
        assert record.model == "gpt-5-mini"
        assert record.input_tokens == 42
        assert record.output_tokens == 17
        assert record.ticker == "NVDA"
        # gpt-5-mini priced at $0.30/$1.20 per 1M
        # 42 * 0.3e-6 + 17 * 1.2e-6 = 1.26e-5 + 2.04e-5 = ~3.30e-5
        assert record.estimated_cost_usd == pytest.approx(3.30e-5, rel=0.05)

    def test_effort_mapped_to_reasoning_effort(self):
        provider = OpenAIProvider()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = self._fake_openai_response()
        provider._client = fake_client
        provider.complete(
            model="o4-mini",
            max_tokens=100,
            messages=[{"role": "user", "content": "hi"}],
            effort="xhigh",  # should map to "high"
        )
        kwargs = fake_client.chat.completions.create.call_args.kwargs
        assert kwargs.get("reasoning_effort") == "high"

    def test_falls_back_when_sdk_rejects_reasoning_effort(self):
        """Older SDKs / non-o-series models reject reasoning_effort — retry without."""
        provider = OpenAIProvider()
        fake_client = MagicMock()
        n = {"calls": 0}

        def fake_create(**kw):
            n["calls"] += 1
            if "reasoning_effort" in kw:
                raise TypeError(
                    "create() got an unexpected keyword argument 'reasoning_effort'"
                )
            return self._fake_openai_response()

        fake_client.chat.completions.create.side_effect = fake_create
        provider._client = fake_client
        provider.complete(
            model="gpt-4.1",
            max_tokens=100,
            messages=[{"role": "user", "content": "hi"}],
            effort="high",
        )
        assert n["calls"] == 2  # first failed, retry succeeded

    def test_lazy_import_error_message(self):
        provider = OpenAIProvider()
        # Force the lazy-import path to fail by patching openai → ImportError
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(RuntimeError, match="openai package not installed"):
                provider._get_client()

    def test_unknown_model_uses_fallback_pricing(self):
        provider = OpenAIProvider()
        # Default fallback rates are $2/$8 per 1M
        cost = provider._estimate_cost("gpt-future-model", 1_000_000, 1_000_000)
        assert cost == pytest.approx(10.0)
