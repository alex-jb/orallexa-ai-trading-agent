"""
tests/test_context_compressor.py
──────────────────────────────────────────────────────────────────
Tests for engine/context_compressor.py — extractive + LLM strategies.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.context_compressor import (
    extractive_summary,
    llm_summary,
    compress,
    compression_ratio,
)


# ── extractive_summary ─────────────────────────────────────────────────────


class TestExtractive:
    def test_short_text_unchanged(self):
        s = "NVDA is trending up."
        assert extractive_summary(s, max_chars=600) == s

    def test_empty_returns_empty(self):
        assert extractive_summary("", max_chars=100) == ""

    def test_keeps_first_and_last_sentences(self):
        text = (
            "First sentence with no numbers. "
            "Middle filler one. Middle filler two. Middle filler three. "
            "Last sentence wraps things up."
        )
        # max_chars high enough to allow first+last but force middles to drop
        out = extractive_summary(text, max_chars=80)
        assert out.startswith("First sentence")
        assert "Last sentence" in out

    def test_preserves_sentences_with_numbers(self):
        text = (
            "Generic intro. "
            "NVDA closed at 142.50 today. "
            "Some filler prose here. "
            "We added more filler to push past the budget threshold so something has to drop. "
            "Final outlook."
        )
        out = extractive_summary(text, max_chars=120)
        assert "142.50" in out

    def test_preserves_directional_keywords(self):
        text = (
            "Generic intro. "
            "Setup looks bullish on multiple timeframes. "
            "Lots of unrelated filler. " * 3
            + "Final note."
        )
        out = extractive_summary(text, max_chars=120)
        assert "bullish" in out.lower()


# ── llm_summary ────────────────────────────────────────────────────────────


def _mock_llm_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


class TestLLMSummary:
    def test_short_input_returns_unchanged(self):
        s = "Brief text."
        assert llm_summary(s) == s

    def test_long_input_calls_llm(self):
        long_text = "x" * 500
        with patch("llm.claude_client.get_client", return_value=MagicMock()), \
             patch("llm.call_logger.logged_create",
                   return_value=(_mock_llm_response("Compressed."), {})):
            out = llm_summary(long_text, ticker="NVDA")
        assert out == "Compressed."

    def test_llm_failure_returns_original(self):
        long_text = "x" * 500
        with patch("llm.claude_client.get_client", side_effect=RuntimeError("api")):
            out = llm_summary(long_text)
        assert out == long_text

    def test_llm_empty_response_returns_original(self):
        long_text = "x" * 500
        with patch("llm.claude_client.get_client", return_value=MagicMock()), \
             patch("llm.call_logger.logged_create",
                   return_value=(_mock_llm_response(""), {})):
            out = llm_summary(long_text)
        assert out == long_text


# ── compress (router) ──────────────────────────────────────────────────────


class TestCompress:
    def test_off_mode_passes_through(self):
        s = "long " * 1000
        assert compress(s, mode="off") == s

    def test_extractive_mode(self):
        s = "first. second. third. " * 50
        out = compress(s, mode="extractive", max_chars=100)
        assert len(out) <= 110  # small slack for ellipsis

    def test_auto_mode_short_uses_extractive(self):
        s = "first. second. third. " * 10  # ~210 chars — under 1500 threshold
        with patch("engine.context_compressor.llm_summary",
                   side_effect=AssertionError("LLM must not be called")):
            compress(s, mode="auto")  # should not raise

    def test_auto_mode_long_uses_llm(self):
        s = "x" * 2000
        with patch("engine.context_compressor.llm_summary",
                   return_value="LLM_OUTPUT") as fake:
            out = compress(s, mode="auto")
        assert out == "LLM_OUTPUT"
        fake.assert_called_once()

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError):
            compress("x", mode="banana")


# ── compression_ratio ─────────────────────────────────────────────────────


class TestRatio:
    def test_basic(self):
        assert compression_ratio("a" * 100, "a" * 25) == 0.25

    def test_empty_original(self):
        assert compression_ratio("", "anything") == 1.0
