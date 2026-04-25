"""
engine/token_budget.py
──────────────────────────────────────────────────────────────────
Hard ceiling on token spend across an agentic loop.

Inspired by the Claude Opus 4.7 'task budgets' beta: pass a token
ceiling to a multi-agent flow and have it short-circuit before
runaway cost. We can't pass the budget to the API directly (the
SDK feature is beta) so we enforce it client-side: each
logged_create result is fed into the budget; once consumed >= cap,
the budget refuses further calls and the orchestrator skips
remaining steps gracefully.

Usage:
    from engine.token_budget import TokenBudget
    budget = TokenBudget(cap_tokens=100_000, cap_usd=0.50)

    if budget.allow():
        resp, rec = logged_create(...)
        budget.consume(rec)

    if budget.allow():
        resp, rec = logged_create(...)
        budget.consume(rec)

    print(budget.report())   # {used_tokens, used_cost_usd, remaining, exhausted}

Threading: methods are guarded by an internal Lock so a parallel
agent panel can safely share one budget instance.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TokenBudget:
    """
    Soft client-side budget enforcer for agentic LLM loops.

    Either or both ceilings can be set; budget is exhausted as soon
    as ANY ceiling is hit. Set a ceiling to None to disable that gate.
    """
    cap_tokens: Optional[int] = None
    cap_usd: Optional[float] = None
    label: str = "default"

    used_tokens: int = 0
    used_cost_usd: float = 0.0
    n_calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allow(self) -> bool:
        """Return True if there's headroom left under every active cap."""
        with self._lock:
            return not self._exhausted_locked()

    def _exhausted_locked(self) -> bool:
        if self.cap_tokens is not None and self.used_tokens >= self.cap_tokens:
            return True
        if self.cap_usd is not None and self.used_cost_usd >= self.cap_usd:
            return True
        return False

    def consume(self, record) -> None:
        """
        Charge a logged_create record against the budget. Accepts the
        LLMCallRecord dataclass (or any object with input_tokens,
        output_tokens, estimated_cost_usd attributes).
        """
        if record is None:
            return
        in_t = int(getattr(record, "input_tokens", 0) or 0)
        out_t = int(getattr(record, "output_tokens", 0) or 0)
        cost = float(getattr(record, "estimated_cost_usd", 0.0) or 0.0)
        with self._lock:
            self.used_tokens += in_t + out_t
            self.used_cost_usd += cost
            self.n_calls += 1

    def remaining_tokens(self) -> Optional[int]:
        if self.cap_tokens is None:
            return None
        return max(0, self.cap_tokens - self.used_tokens)

    def remaining_usd(self) -> Optional[float]:
        if self.cap_usd is None:
            return None
        return max(0.0, self.cap_usd - self.used_cost_usd)

    def report(self) -> dict:
        with self._lock:
            return {
                "label": self.label,
                "n_calls": self.n_calls,
                "used_tokens": self.used_tokens,
                "used_cost_usd": round(self.used_cost_usd, 6),
                "cap_tokens": self.cap_tokens,
                "cap_usd": self.cap_usd,
                "remaining_tokens": self.remaining_tokens(),
                "remaining_usd": (
                    round(self.remaining_usd(), 6)
                    if self.remaining_usd() is not None else None
                ),
                "exhausted": self._exhausted_locked(),
            }


# ── Optional: scoped wrapper ────────────────────────────────────────────────


def guarded_call(budget: TokenBudget, fn, *args, **kwargs):
    """
    Run `fn(*args, **kwargs)` only if the budget allows. Expects fn to
    return either (response, record) or just record. Charges the budget
    on success.

    Returns:
      (result, charged_bool) — charged_bool is False if the budget
      blocked the call (result is None in that case).
    """
    if not budget.allow():
        return (None, False)
    result = fn(*args, **kwargs)
    record = result[1] if isinstance(result, tuple) and len(result) >= 2 else result
    budget.consume(record)
    return (result, True)
