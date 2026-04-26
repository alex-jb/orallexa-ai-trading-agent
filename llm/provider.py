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
from typing import Any, Optional, Protocol, runtime_checkable

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


class OpenAIProvider:
    """
    Adapter wrapping the openai SDK. Lazy-imports `openai` only when
    .complete() is actually invoked, so the project doesn't take
    `openai` as a hard dependency. Install with `pip install openai`
    when you flip ORALEXXA_LLM_PROVIDER=openai.

    Translates the Anthropic-style messages list to OpenAI's chat
    completions format (compatible — both use [{role, content}]) and
    rebuilds the response shape into something call_logger can consume:
    `response.content[0].text`, `response.content[0].type == "text"`,
    `response.usage.{input_tokens, output_tokens}`. The returned record
    is an LLMCallRecord built directly so it flows through the same
    JSONL log + PostHog + Langfuse exporters as Anthropic calls.

    Effort note: OpenAI doesn't have a 1:1 'effort' equivalent. We map
    {low,medium,high,xhigh,max} → reasoning_effort {low,medium,high,
    high,high} on o-series models and ignore on standard chat models.
    """

    name = "openai"

    # Cents per 1M tokens — keep in sync with platform.openai.com/pricing
    _PRICING: dict[str, dict] = {
        "gpt-5":         {"input":  3.00 / 1_000_000, "output": 12.00 / 1_000_000},
        "gpt-5-mini":    {"input":  0.30 / 1_000_000, "output":  1.20 / 1_000_000},
        "gpt-4.1":       {"input":  2.00 / 1_000_000, "output":  8.00 / 1_000_000},
        "gpt-4.1-mini":  {"input":  0.40 / 1_000_000, "output":  1.60 / 1_000_000},
        "o3":            {"input":  2.00 / 1_000_000, "output":  8.00 / 1_000_000},
        "o4-mini":       {"input":  1.10 / 1_000_000, "output":  4.40 / 1_000_000},
    }

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise RuntimeError(
                    "openai package not installed. Run `pip install openai` "
                    "to enable OpenAIProvider."
                ) from e
            self._client = OpenAI()
        return self._client

    def _estimate_cost(self, model: str, in_tokens: int, out_tokens: int) -> float:
        rates = self._PRICING.get(
            model,
            {"input": 2.0 / 1_000_000, "output": 8.0 / 1_000_000},
        )
        return in_tokens * rates["input"] + out_tokens * rates["output"]

    def _wrap_response(self, raw, model: str):
        """Translate openai response → Anthropic-style content/usage shape."""
        text_blocks: list[Any] = []  # type: ignore[name-defined]
        for choice in raw.choices:
            msg = getattr(choice, "message", None)
            content = getattr(msg, "content", "") if msg else ""
            block = type("TextBlock", (), {})()
            block.type = "text"
            block.text = content or ""
            text_blocks.append(block)
        usage = type("Usage", (), {})()
        # OpenAI emits prompt_tokens / completion_tokens; map to anthropic names
        u = getattr(raw, "usage", None)
        usage.input_tokens = getattr(u, "prompt_tokens", 0) if u else 0
        usage.output_tokens = getattr(u, "completion_tokens", 0) if u else 0
        wrapped = type("OpenAIResponse", (), {})()
        wrapped.content = text_blocks
        wrapped.usage = usage
        return wrapped

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
        """Returns (response, LLMCallRecord) — same shape as AnthropicProvider."""
        import time
        from datetime import datetime, timezone
        from llm.call_logger import (
            LLMCallRecord, get_tier, _append_record,
            _send_to_posthog, _send_to_langfuse, current_run_id,
        )

        kwargs: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        # Map effort → reasoning_effort for o-series models that support it.
        # Other models silently drop the kwarg via TypeError fallback below.
        if effort:
            mapped = {"xhigh": "high", "max": "high"}.get(effort, effort)
            kwargs["reasoning_effort"] = mapped

        client = self._get_client()
        t0 = time.monotonic()
        error_msg = None
        in_tokens = 0
        out_tokens = 0

        try:
            try:
                raw = client.chat.completions.create(**kwargs)
            except TypeError as te:
                # SDK doesn't recognize reasoning_effort on this model
                if "reasoning_effort" in kwargs and "reasoning_effort" in str(te):
                    kwargs.pop("reasoning_effort", None)
                    raw = client.chat.completions.create(**kwargs)
                else:
                    raise
            response = self._wrap_response(raw, model)
            in_tokens = response.usage.input_tokens
            out_tokens = response.usage.output_tokens
        except Exception as e:
            error_msg = str(e)[:200]
            raise
        finally:
            latency_ms = int((time.monotonic() - t0) * 1000)
            record = LLMCallRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_type=request_type,
                model=model,
                tier=get_tier(model) if "haiku" in model.lower() else "OPENAI",
                latency_ms=latency_ms,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                estimated_cost_usd=round(
                    self._estimate_cost(model, in_tokens, out_tokens), 6
                ),
                retry_count=0,
                final_action=final_action,
                confidence_score=confidence_score,
                error=error_msg,
                ticker=ticker,
                run_id=current_run_id,
            )
            try:
                _append_record(record)
            except Exception:
                pass
            _send_to_posthog(record)
            _send_to_langfuse(record)

        return response, record


# Future placeholders — instantiating these raises NotImplementedError until
# someone actually needs the second provider. Registered so that
# get_provider("name") fails LOUD instead of silently returning Anthropic.

class _UnimplementedProvider:
    name = "unimplemented"

    def __init__(self, real_name: str):
        self.real_name = real_name

    def complete(self, **_):
        raise NotImplementedError(
            f"Provider '{self.real_name}' is registered but not yet implemented. "
            f"See llm/provider.py for the AnthropicProvider/OpenAIProvider templates."
        )


_REGISTRY: dict[str, "type | callable"] = {
    "anthropic": AnthropicProvider,
    "openai":    OpenAIProvider,
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
