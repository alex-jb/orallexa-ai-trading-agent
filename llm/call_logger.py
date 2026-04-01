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
PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.80 / 1_000_000, "output": 4.00 / 1_000_000},
    "claude-sonnet-4-5":        {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-sonnet-4-6":        {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
}


def get_tier(model: str) -> str:
    if "haiku" in model.lower():
        return "FAST"
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
):
    """
    Drop-in wrapper for client.messages.create() with logging.

    Returns (response, LLMCallRecord).
    """
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature

    t0 = time.monotonic()
    error_msg = None
    input_tokens = 0
    output_tokens = 0
    retry_count = 0

    try:
        response = client.messages.create(**kwargs)
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
