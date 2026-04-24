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

from llm.call_logger import LLMCallRecord, _send_to_posthog, _send_to_langfuse


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


class TestLangfuseExport:
    def test_no_op_when_keys_missing(self):
        rec = _sample_record()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            with patch("requests.post") as mock_post:
                _send_to_langfuse(rec)
                mock_post.assert_not_called()

    def test_no_op_when_only_one_key(self):
        rec = _sample_record()
        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "pk"}, clear=False):
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            with patch("requests.post") as mock_post:
                _send_to_langfuse(rec)
                mock_post.assert_not_called()

    def test_posts_generation_event_with_both_keys(self):
        rec = _sample_record()
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk-lf-abc",
            "LANGFUSE_SECRET_KEY": "sk-lf-xyz",
        }):
            with patch("requests.post") as mock_post:
                _send_to_langfuse(rec)
                assert mock_post.called
                args, kwargs = mock_post.call_args
                assert "langfuse.com" in args[0] or "api/public/ingestion" in args[0]
                assert "Authorization" in kwargs["headers"]
                assert kwargs["headers"]["Authorization"].startswith("Basic ")
                body = kwargs["json"]
                assert "batch" in body
                evt = body["batch"][0]
                assert evt["type"] == "generation-create"
                gen = evt["body"]
                assert gen["type"] == "GENERATION"
                assert gen["model"] == "claude-haiku-4-5-20251001"
                assert gen["usage"]["input"] == 120
                assert gen["usage"]["output"] == 80
                assert gen["usage"]["totalCost"] == 0.000416
                assert gen["metadata"]["ticker"] == "NVDA"

    def test_custom_host(self):
        rec = _sample_record()
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk",
            "LANGFUSE_SECRET_KEY": "sk",
            "LANGFUSE_HOST": "https://self-hosted.example.com",
        }):
            with patch("requests.post") as mock_post:
                _send_to_langfuse(rec)
                args, _ = mock_post.call_args
                assert args[0] == "https://self-hosted.example.com/api/public/ingestion"

    def test_error_record_sets_level_error(self):
        rec = _sample_record(error="rate_limited")
        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"}):
            with patch("requests.post") as mock_post:
                _send_to_langfuse(rec)
                gen = mock_post.call_args.kwargs["json"]["batch"][0]["body"]
                assert gen["level"] == "ERROR"
                assert gen["statusMessage"] == "rate_limited"

    def test_swallows_network_errors(self):
        rec = _sample_record()
        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"}):
            with patch("requests.post", side_effect=RuntimeError("boom")):
                _send_to_langfuse(rec)  # must not raise
