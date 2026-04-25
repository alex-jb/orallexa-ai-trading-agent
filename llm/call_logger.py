"""
llm/call_logger.py
──────────────────────────────────────────────────────────────────
Centralized LLM call logging. Wraps every Anthropic API call to
capture latency, tokens, cost, and decision metadata.

Logs are stored in logs/llm_calls.jsonl (append-only, one JSON per line).

Usage:
    from llm.call_logger import logged_create
    response, record = logged_create(
        client, request_type="real_llm_analysis",
        model=FAST_MODEL, max_tokens=400, messages=[...],
    )
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _ROOT / "logs"
_LOG_PATH = _LOG_DIR / "llm_calls.jsonl"
_lock = threading.Lock()

# Module-level run_id — set by experiment harness to isolate log entries
current_run_id: Optional[str] = None

# ── Pricing (USD per token) ──────────────────────────────────────────────
# Note on Opus 4.7: API price is unchanged from 4.6 ($5/$25 per 1M tokens),
# but the new tokenizer uses ~35% more tokens for the same fixed text.
# Effective cost is therefore higher — track via estimated_cost_usd × 1.35
# for budget projections.
PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.80 / 1_000_000, "output":  4.00 / 1_000_000},
    "claude-sonnet-4-5":         {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-sonnet-4-6":         {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-opus-4-7":           {"input": 5.00 / 1_000_000, "output": 25.00 / 1_000_000},
    "claude-opus-4-6":           {"input": 5.00 / 1_000_000, "output": 25.00 / 1_000_000},
}

# Models that use the new (Opus 4.7+) tokenizer. Approximate inflation
# vs the previous tokenizer is +35% per Anthropic release notes.
NEW_TOKENIZER_MODELS = frozenset({"claude-opus-4-7"})
NEW_TOKENIZER_INFLATION = 1.35


def get_tier(model: str) -> str:
    name = model.lower()
    if "haiku" in name:
        return "FAST"
    if "opus" in name:
        return "OPUS"
    return "DEEP"


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING.get(model, {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000})
    return input_tokens * rates["input"] + output_tokens * rates["output"]


@dataclass
class LLMCallRecord:
    timestamp: str
    request_type: str
    model: str
    tier: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    retry_count: int
    final_action: Optional[str]
    confidence_score: Optional[float]
    error: Optional[str]
    ticker: Optional[str]
    run_id: Optional[str]


def _append_record(record: LLMCallRecord) -> None:
    """Append one JSON line to the log file (thread-safe)."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def _send_to_langfuse(record: LLMCallRecord) -> None:
    """
    Forward the LLM call record to Langfuse as a 'generation-create' event.
    Requires LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY. No-op otherwise.
    Never raises.

    Langfuse ingestion docs: https://api.reference.langfuse.com/
    """
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")
    try:
        import base64
        import uuid
        import requests
        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        event_id = str(uuid.uuid4())
        observation_id = str(uuid.uuid4())
        body = {
            "id": observation_id,
            "traceId": record.run_id or f"trace-{observation_id}",
            "name": record.request_type,
            "type": "GENERATION",
            "startTime": record.timestamp,
            "endTime": record.timestamp,
            "model": record.model,
            "modelParameters": {"tier": record.tier},
            "usage": {
                "input": record.input_tokens,
                "output": record.output_tokens,
                "total": record.input_tokens + record.output_tokens,
                "unit": "TOKENS",
                "inputCost": None,
                "outputCost": None,
                "totalCost": record.estimated_cost_usd,
            },
            "level": "ERROR" if record.error else "DEFAULT",
            "statusMessage": record.error,
            "metadata": {
                "ticker": record.ticker,
                "final_action": record.final_action,
                "confidence_score": record.confidence_score,
                "latency_ms": record.latency_ms,
                "retry_count": record.retry_count,
            },
        }
        payload = {
            "batch": [{
                "id": event_id,
                "timestamp": record.timestamp,
                "type": "generation-create",
                "body": body,
            }],
        }
        requests.post(
            f"{host}/api/public/ingestion",
            json=payload,
            headers={"Authorization": f"Basic {auth}"},
            timeout=2.0,
        )
    except Exception:
        pass  # telemetry must never break main flow


def _send_to_posthog(record: LLMCallRecord) -> None:
    """
    Forward the LLM call record to PostHog LLM Analytics.
    No-op if POSTHOG_API_KEY is not set. Must never raise.
    """
    api_key = os.environ.get("POSTHOG_API_KEY")
    if not api_key:
        return
    host = os.environ.get("POSTHOG_HOST", "https://us.i.posthog.com").rstrip("/")
    distinct_id = os.environ.get("POSTHOG_DISTINCT_ID", "oralexxa")
    try:
        import requests
        payload = {
            "api_key": api_key,
            "event": "$ai_generation",
            "distinct_id": distinct_id,
            "properties": {
                "$ai_provider": "anthropic",
                "$ai_model": record.model,
                "$ai_input_tokens": record.input_tokens,
                "$ai_output_tokens": record.output_tokens,
                "$ai_latency": record.latency_ms / 1000.0,
                "$ai_http_status": 200 if record.error is None else 500,
                "$ai_is_error": record.error is not None,
                "$ai_error": record.error,
                "$ai_trace_id": record.run_id,
                "request_type": record.request_type,
                "tier": record.tier,
                "cost_usd": record.estimated_cost_usd,
                "ticker": record.ticker,
                "final_action": record.final_action,
                "confidence_score": record.confidence_score,
            },
            "timestamp": record.timestamp,
        }
        requests.post(f"{host}/capture/", json=payload, timeout=2.0)
    except Exception:
        pass  # telemetry must never break main flow


def logged_create(
    client,
    *,
    request_type: str,
    model: str,
    max_tokens: int,
    messages: list,
    ticker: Optional[str] = None,
    temperature: Optional[float] = None,
    final_action: Optional[str] = None,
    confidence_score: Optional[float] = None,
    effort: Optional[str] = None,
):
    """
    Drop-in wrapper for client.messages.create() with logging.

    `effort` controls the new Opus 4.7 reasoning depth knob:
    "low" / "medium" / "high" / "xhigh" / "max". Passed to the SDK
    via `output_config={"effort": ...}` when set; older SDKs that
    don't recognize the kwarg silently drop it (we catch the
    TypeError and retry without).

    Returns (response, LLMCallRecord).
    """
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if effort:
        kwargs["output_config"] = {"effort": effort}

    t0 = time.monotonic()
    error_msg = None
    input_tokens = 0
    output_tokens = 0
    retry_count = 0

    try:
        try:
            response = client.messages.create(**kwargs)
        except TypeError as te:
            # Older anthropic SDK doesn't accept output_config — retry without
            if "output_config" in kwargs and "output_config" in str(te):
                kwargs.pop("output_config", None)
                response = client.messages.create(**kwargs)
            else:
                raise
        input_tokens = getattr(response.usage, "input_tokens", 0)
        output_tokens = getattr(response.usage, "output_tokens", 0)
    except Exception as e:
        error_msg = str(e)[:200]
        raise
    finally:
        latency_ms = int((time.monotonic() - t0) * 1000)
        record = LLMCallRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            request_type=request_type,
            model=model,
            tier=get_tier(model),
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=round(_estimate_cost(model, input_tokens, output_tokens), 6),
            retry_count=retry_count,
            final_action=final_action,
            confidence_score=confidence_score,
            error=error_msg,
            ticker=ticker,
            run_id=current_run_id,
        )
        try:
            _append_record(record)
        except Exception:
            pass  # logging must never break the main flow
        _send_to_posthog(record)
        _send_to_langfuse(record)

    return response, record


def load_call_log(path: str = None) -> list[dict]:
    """Read all records from the JSONL log."""
    p = Path(path) if path else _LOG_PATH
    if not p.exists():
        return []
    records = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def load_call_log_by_run(run_id: str, path: str = None) -> list[dict]:
    """Load only records matching a specific run_id."""
    return [r for r in load_call_log(path) if r.get("run_id") == run_id]
