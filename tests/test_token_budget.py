"""
tests/test_token_budget.py
──────────────────────────────────────────────────────────────────
Tests for engine/token_budget.py and the call_logger effort kwarg.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.token_budget import TokenBudget, guarded_call


def _record(in_t: int, out_t: int, cost: float):
    r = MagicMock()
    r.input_tokens = in_t
    r.output_tokens = out_t
    r.estimated_cost_usd = cost
    return r


# ── TokenBudget basics ─────────────────────────────────────────────────────


class TestBasics:
    def test_no_caps_always_allows(self):
        b = TokenBudget()
        assert b.allow() is True
        b.consume(_record(1_000_000, 1_000_000, 100))
        assert b.allow() is True  # still allowed because no caps

    def test_consume_accumulates(self):
        b = TokenBudget(cap_tokens=10_000)
        b.consume(_record(100, 200, 0.001))
        b.consume(_record(50, 75, 0.0005))
        rep = b.report()
        assert rep["used_tokens"] == 425
        assert rep["used_cost_usd"] == pytest.approx(0.0015)
        assert rep["n_calls"] == 2

    def test_token_cap_blocks(self):
        b = TokenBudget(cap_tokens=500)
        b.consume(_record(300, 200, 0))
        assert b.allow() is False
        assert b.report()["exhausted"] is True

    def test_usd_cap_blocks(self):
        b = TokenBudget(cap_usd=0.01)
        b.consume(_record(0, 0, 0.012))
        assert b.allow() is False

    def test_either_cap_triggers_exhaustion(self):
        b = TokenBudget(cap_tokens=10_000, cap_usd=0.01)
        # Stay under tokens but blow USD
        b.consume(_record(100, 100, 0.05))
        assert b.allow() is False

    def test_remaining_returns_floor_zero(self):
        b = TokenBudget(cap_tokens=100, cap_usd=0.01)
        b.consume(_record(150, 0, 0.05))
        assert b.remaining_tokens() == 0
        assert b.remaining_usd() == 0.0

    def test_consume_handles_none_record(self):
        b = TokenBudget(cap_tokens=100)
        b.consume(None)  # must not raise
        assert b.report()["n_calls"] == 0


# ── guarded_call ───────────────────────────────────────────────────────────


class TestGuardedCall:
    def test_allowed_call_runs_and_charges(self):
        b = TokenBudget(cap_tokens=10_000)
        rec = _record(100, 50, 0.001)
        fn = MagicMock(return_value=("response", rec))
        result, charged = guarded_call(b, fn)
        assert charged is True
        assert result == ("response", rec)
        assert b.report()["used_tokens"] == 150

    def test_blocked_call_does_not_run(self):
        b = TokenBudget(cap_tokens=10)
        b.consume(_record(20, 0, 0))
        fn = MagicMock()
        result, charged = guarded_call(b, fn)
        assert charged is False
        assert result is None
        fn.assert_not_called()

    def test_accepts_record_only_return(self):
        b = TokenBudget(cap_usd=10.0)
        rec = _record(50, 25, 0.0005)
        fn = MagicMock(return_value=rec)
        _, charged = guarded_call(b, fn)
        assert charged is True
        assert b.report()["used_tokens"] == 75


# ── call_logger effort kwarg ───────────────────────────────────────────────


class TestEffortKwarg:
    def test_effort_passed_to_sdk(self):
        from llm.call_logger import logged_create

        fake_response = MagicMock()
        fake_response.usage.input_tokens = 10
        fake_response.usage.output_tokens = 20
        client = MagicMock()
        client.messages.create.return_value = fake_response

        logged_create(
            client, request_type="t", model="claude-opus-4-7",
            max_tokens=100, messages=[{"role": "user", "content": "hi"}],
            effort="xhigh",
        )
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["output_config"] == {"effort": "xhigh"}

    def test_effort_omitted_when_none(self):
        from llm.call_logger import logged_create

        fake_response = MagicMock()
        fake_response.usage.input_tokens = 10
        fake_response.usage.output_tokens = 20
        client = MagicMock()
        client.messages.create.return_value = fake_response

        logged_create(
            client, request_type="t", model="claude-sonnet-4-6",
            max_tokens=100, messages=[{"role": "user", "content": "hi"}],
        )
        kwargs = client.messages.create.call_args.kwargs
        assert "output_config" not in kwargs

    def test_falls_back_when_sdk_rejects_output_config(self):
        """Older anthropic SDKs without output_config support should retry without it."""
        from llm.call_logger import logged_create

        fake_response = MagicMock()
        fake_response.usage.input_tokens = 10
        fake_response.usage.output_tokens = 20
        client = MagicMock()

        call_count = {"n": 0}

        def fake_create(**kw):
            call_count["n"] += 1
            if "output_config" in kw:
                raise TypeError(
                    "messages.create() got an unexpected keyword argument 'output_config'"
                )
            return fake_response

        client.messages.create.side_effect = fake_create

        logged_create(
            client, request_type="t", model="claude-opus-4-7",
            max_tokens=100, messages=[{"role": "user", "content": "hi"}],
            effort="xhigh",
        )
        assert call_count["n"] == 2  # first failed, retry succeeded


# ── PRICING + tier ─────────────────────────────────────────────────────────


class TestPricing:
    def test_opus_4_7_priced(self):
        from llm.call_logger import PRICING, _estimate_cost
        assert "claude-opus-4-7" in PRICING
        # 1M input + 1M output → $5 + $25 = $30
        cost = _estimate_cost("claude-opus-4-7", 1_000_000, 1_000_000)
        assert cost == pytest.approx(30.0)

    def test_opus_tier_label(self):
        from llm.call_logger import get_tier
        assert get_tier("claude-opus-4-7") == "OPUS"
        assert get_tier("claude-sonnet-4-6") == "DEEP"
        assert get_tier("claude-haiku-4-5-20251001") == "FAST"

    def test_new_tokenizer_constants_present(self):
        from llm.call_logger import NEW_TOKENIZER_MODELS, NEW_TOKENIZER_INFLATION
        assert "claude-opus-4-7" in NEW_TOKENIZER_MODELS
        assert NEW_TOKENIZER_INFLATION == pytest.approx(1.35)
