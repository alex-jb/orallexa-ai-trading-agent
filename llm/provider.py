"""
llm/provider.py
──────────────────────────────────────────────────────────────────
Lightweight multi-provider abstraction over chat-completion clients.

Inspired by TradingAgents v0.2.0's provider matrix (OpenAI / Gemini /
Claude / Grok / Ollama). We don't actually need that flexibility today
— every code path uses Anthropic — but the abstraction is cheap to
add now and removes the rewrite tax later.

Design:
  - One `ChatProvider` Protocol declares the surface we use:
      .complete(*, model, max_tokens, messages, temperature?, effort?,
                ticker?) → (response, record)
    Where `response` has `.content[i].text`/`.type` and `record` has
    `input_tokens`, `output_tokens`, `estimated_cost_usd`.
  - `AnthropicProvider` is the concrete adapter wrapping the existing
    `llm.call_logger.logged_create` so behavior is identical to today.
  - `get_provider(name)` returns the right adapter; `current_provider()`
    reads the env var ORALEXXA_LLM_PROVIDER (default 'anthropic').

When we eventually add OpenAI/Gemini, write `OpenAIProvider` /
`GeminiProvider` here, register in `_REGISTRY`, set the env var, done —
no call-site rewrites needed.

Out of scope today (deliberately):
  - Tool use / function calling (Anthropic and OpenAI APIs differ)
  - Streaming responses
  - Vision / image inputs (we only have one chart_analysis path; defer)

Usage:
    from llm.provider import get_provider
    provider = get_provider()  # default = anthropic
    response, record = provider.complete(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": "Hi"}],
    )
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ChatProvider(Protocol):
    """The minimum surface every concrete provider must expose."""

    name: str

    def complete(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list,
        temperature: Optional[float] = None,
        effort: Optional[str] = None,
        ticker: Optional[str] = None,
        request_type: str = "complete",
        final_action: Optional[str] = None,
        confidence_score: Optional[float] = None,
    ): ...


class AnthropicProvider:
    """Adapter around llm.call_logger.logged_create (existing path)."""

    name = "anthropic"

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from llm.claude_client import get_client
            self._client = get_client()
        return self._client

    def complete(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list,
        temperature: Optional[float] = None,
        effort: Optional[str] = None,
        ticker: Optional[str] = None,
        request_type: str = "complete",
        final_action: Optional[str] = None,
        confidence_score: Optional[float] = None,
    ):
        from llm.call_logger import logged_create
        return logged_create(
            self._get_client(),
            request_type=request_type,
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            ticker=ticker,
            temperature=temperature,
            final_action=final_action,
            confidence_score=confidence_score,
            effort=effort,
        )


# Future placeholders — instantiating these raises NotImplementedError until
# someone actually needs the second provider. Registered so that
# get_provider("openai") fails LOUD instead of silently returning Anthropic.

class _UnimplementedProvider:
    name = "unimplemented"

    def __init__(self, real_name: str):
        self.real_name = real_name

    def complete(self, **_):
        raise NotImplementedError(
            f"Provider '{self.real_name}' is registered but not yet implemented. "
            f"See llm/provider.py for the AnthropicProvider template."
        )


_REGISTRY: dict[str, "type | callable"] = {
    "anthropic": AnthropicProvider,
    "openai":    lambda: _UnimplementedProvider("openai"),
    "gemini":    lambda: _UnimplementedProvider("gemini"),
    "ollama":    lambda: _UnimplementedProvider("ollama"),
    "grok":      lambda: _UnimplementedProvider("grok"),
}


def get_provider(name: Optional[str] = None) -> ChatProvider:
    """
    Return a provider by name. Defaults to ORALEXXA_LLM_PROVIDER env var,
    or 'anthropic' if unset. Unknown names raise KeyError.
    """
    name = name or os.environ.get("ORALEXXA_LLM_PROVIDER", "anthropic")
    name = name.lower().strip()
    factory = _REGISTRY.get(name)
    if factory is None:
        raise KeyError(
            f"Unknown LLM provider '{name}'. "
            f"Registered: {sorted(_REGISTRY.keys())}"
        )
    instance = factory()
    return instance


def current_provider_name() -> str:
    return os.environ.get("ORALEXXA_LLM_PROVIDER", "anthropic").lower()


def is_anthropic() -> bool:
    return current_provider_name() == "anthropic"
