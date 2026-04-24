"""
tests/test_regime_llm.py
──────────────────────────────────────────────────────────────────
Tests for llm/regime_llm.py — JSON parsing + llm_regime_fn end-to-end.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from llm.regime_llm import _parse_json, _features_summary, llm_regime_fn


# ── _parse_json ────────────────────────────────────────────────────────────


class TestParseJson:
    def test_plain_object(self):
        r = _parse_json('{"strategy": "rsi_reversal", "params": {"rsi_min": 30}}')
        assert r["strategy"] == "rsi_reversal"

    def test_markdown_fenced(self):
        r = _parse_json('```json\n{"strategy": "trend_momentum"}\n```')
        assert r["strategy"] == "trend_momentum"

    def test_plain_fence(self):
        r = _parse_json('```\n{"a": 1}\n```')
        assert r == {"a": 1}

    def test_embedded_prose(self):
        r = _parse_json('Sure, here you go: {"strategy": "dual_thrust"} — done!')
        assert r["strategy"] == "dual_thrust"

    def test_non_json_returns_none(self):
        assert _parse_json("sorry, I can't help") is None

    def test_broken_json_returns_none(self):
        assert _parse_json("{strategy: not quoted}") is None


# ── _features_summary ──────────────────────────────────────────────────────


class TestFeaturesSummary:
    def test_short_df_reports_missing(self):
        assert "not enough" in _features_summary(None)
        assert "not enough" in _features_summary(pd.DataFrame())

    def test_extracts_common_indicators(self):
        n = 30
        df = pd.DataFrame({
            "Close": np.linspace(100, 110, n),
            "ADX": np.full(n, 25.0),
            "ATR": np.full(n, 2.0),
            "RSI": np.linspace(50, 65, n),
        })
        s = _features_summary(df)
        assert "close:" in s
        assert "ADX" in s
        assert "ATR/Close" in s
        assert "RSI" in s


# ── llm_regime_fn ──────────────────────────────────────────────────────────


def _mock_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


class TestLLMRegimeFn:
    def test_no_api_key_returns_sentinel(self):
        base = {"strategy": "trend_momentum", "params": {"stop_loss": 0.04}}
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            r = llm_regime_fn(ticker="NVDA", regime="trending", base=base)
        assert r["strategy"] is None
        assert "no API key" in r["reasoning"]

    def test_happy_path_returns_parsed_proposal(self):
        base = {"strategy": "trend_momentum", "params": {"stop_loss": 0.04}}
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            fake_client = MagicMock()
            with patch("llm.regime_llm.get_client", return_value=fake_client), \
                 patch("llm.call_logger.logged_create", return_value=(
                     _mock_response('{"strategy": "trend_momentum", "params": {"rsi_min": 42}, "reasoning": "Strong trend."}'),
                     {},
                 )):
                r = llm_regime_fn(ticker="NVDA", regime="trending", base=base)
        assert r["strategy"] == "trend_momentum"
        assert r["params"]["rsi_min"] == 42

    def test_parse_failure_returns_sentinel(self):
        base = {"strategy": "trend_momentum", "params": {}}
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            with patch("llm.regime_llm.get_client", return_value=MagicMock()), \
                 patch("llm.call_logger.logged_create", return_value=(
                     _mock_response("sorry, no JSON for you"), {},
                 )):
                r = llm_regime_fn(ticker="NVDA", regime="trending", base=base)
        assert r["strategy"] is None
        assert "parse failed" in r["reasoning"]

    def test_network_exception_returns_sentinel(self):
        base = {"strategy": "trend_momentum", "params": {}}
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            with patch("llm.regime_llm.get_client", side_effect=RuntimeError("net")):
                r = llm_regime_fn(ticker="NVDA", regime="trending", base=base)
        assert r["strategy"] is None
        assert "call failed" in r["reasoning"]


# ── Integration with propose_regime_strategy ───────────────────────────────


class TestIntegration:
    def test_llm_proposal_wins_when_valid(self):
        from engine.regime_strategist import propose_regime_strategy

        def fake_llm(**kwargs):
            return {
                "strategy": "trend_momentum",
                "params": {"rsi_min": 38, "take_profit": 0.12},
                "reasoning": "Trend strength supports tighter entry.",
            }
        r = propose_regime_strategy("NVDA", regime="trending", use_llm=True, llm_fn=fake_llm)
        assert r["source"] == "llm"
        assert r["params"]["rsi_min"] == 38

    def test_llm_sentinel_falls_back_to_heuristic(self):
        from engine.regime_strategist import propose_regime_strategy

        def sentinel_llm(**kwargs):
            return {"strategy": None, "params": {}, "reasoning": "no API key"}
        r = propose_regime_strategy("NVDA", regime="trending", use_llm=True, llm_fn=sentinel_llm)
        assert r["source"] == "heuristic"
