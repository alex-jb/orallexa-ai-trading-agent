"""
tests/test_posthog_export.py
──────────────────────────────────────────────────────────────────
Tests the optional PostHog LLM Analytics export in llm/call_logger.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from llm.call_logger import LLMCallRecord, _send_to_posthog


def _sample_record(**overrides) -> LLMCallRecord:
    base = dict(
        timestamp="2026-04-23T12:00:00+00:00",
        request_type="real_llm_analysis",
        model="claude-haiku-4-5-20251001",
        tier="FAST",
        latency_ms=350,
        input_tokens=120,
        output_tokens=80,
        estimated_cost_usd=0.000416,
        retry_count=0,
        final_action="WAIT",
        confidence_score=0.62,
        error=None,
        ticker="NVDA",
        run_id="run-42",
    )
    base.update(overrides)
    return LLMCallRecord(**base)


class TestPostHogExport:
    def test_no_op_when_api_key_missing(self):
        rec = _sample_record()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("POSTHOG_API_KEY", None)
            with patch("requests.post") as mock_post:
                _send_to_posthog(rec)
                mock_post.assert_not_called()

    def test_posts_with_api_key(self):
        rec = _sample_record()
        with patch.dict(os.environ, {"POSTHOG_API_KEY": "phc_test"}):
            with patch("requests.post") as mock_post:
                _send_to_posthog(rec)
                assert mock_post.called
                _, kwargs = mock_post.call_args
                body = kwargs["json"]
                assert body["api_key"] == "phc_test"
                assert body["event"] == "$ai_generation"
                assert body["properties"]["$ai_model"] == "claude-haiku-4-5-20251001"
                assert body["properties"]["$ai_input_tokens"] == 120
                assert body["properties"]["$ai_output_tokens"] == 80
                assert body["properties"]["$ai_latency"] == pytest.approx(0.35)
                assert body["properties"]["$ai_is_error"] is False
                assert body["properties"]["ticker"] == "NVDA"
                assert body["properties"]["tier"] == "FAST"
                assert body["properties"]["$ai_trace_id"] == "run-42"

    def test_custom_host_respected(self):
        rec = _sample_record()
        with patch.dict(os.environ, {
            "POSTHOG_API_KEY": "phc_test",
            "POSTHOG_HOST": "https://eu.i.posthog.com",
        }):
            with patch("requests.post") as mock_post:
                _send_to_posthog(rec)
                args, _ = mock_post.call_args
                assert args[0] == "https://eu.i.posthog.com/capture/"

    def test_swallows_network_errors(self):
        rec = _sample_record()
        with patch.dict(os.environ, {"POSTHOG_API_KEY": "phc_test"}):
            with patch("requests.post", side_effect=RuntimeError("boom")):
                _send_to_posthog(rec)  # must not raise

    def test_error_record_flags_is_error(self):
        rec = _sample_record(error="timeout", final_action=None)
        with patch.dict(os.environ, {"POSTHOG_API_KEY": "phc_test"}):
            with patch("requests.post") as mock_post:
                _send_to_posthog(rec)
                body = mock_post.call_args.kwargs["json"]
                assert body["properties"]["$ai_is_error"] is True
                assert body["properties"]["$ai_error"] == "timeout"
                assert body["properties"]["$ai_http_status"] == 500
