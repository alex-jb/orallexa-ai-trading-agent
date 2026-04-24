"""
tests/test_mirofish.py
──────────────────────────────────────────────────────────────────
Tests for MiroFish engine modules:
  - engine/scenario_sim.py
  - engine/bias_tracker.py
  - engine/role_memory.py
  - engine/signal_fusion.py
  - engine/micro_swarm.py
  - llm/perspective_panel.py

All LLM and network calls are mocked. No API keys required.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

# Ensure project root is importable
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def _make_llm_response(data: dict) -> MagicMock:
    """Create a mock LLM response whose _extract_text returns JSON."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(data)
    resp = MagicMock()
    resp.content = [text_block]
    return resp


# ════════════════════════════════════════════════════════════════════
# 1. engine/scenario_sim.py
# ════════════════════════════════════════════════════════════════════


class TestScenarioSim:
    """Tests for engine/scenario_sim.py — run_scenario + helpers."""

    @patch(
        "engine.scenario_sim._build_current_context",
        return_value="NVDA: $900.00 (+1.2%)",
    )
    @patch("engine.scenario_sim.get_client")
    @patch("engine.scenario_sim.logged_create")
    def test_run_scenario_happy_path(self, mock_logged, mock_client, mock_ctx):
        from engine.scenario_sim import run_scenario

        payload = {
            "impacts": [
                {
                    "ticker": "NVDA",
                    "impact_pct": -5.0,
                    "direction": "bearish",
                    "severity": "high",
                    "reasoning": "Rate hike hurts growth.",
                    "time_horizon": "1-2 weeks",
                    "key_level": 850.0,
                },
            ],
            "portfolio_delta_pct": -5.0,
            "historical_analog": {
                "event": "Dec 2018",
                "date": "2018-12",
                "market_reaction": "fell",
                "relevance": "high",
            },
            "hedging_suggestions": ["Buy puts"],
            "summary": "Bearish scenario.",
            "confidence": 72,
            "regime_shift": "risk-off",
        }
        mock_logged.return_value = (_make_llm_response(payload), {})

        result = run_scenario("Fed hikes 50bp", ["NVDA"])
        assert result["scenario"] == "Fed hikes 50bp"
        assert len(result["impacts"]) == 1
        assert result["impacts"][0]["direction"] == "bearish"
        assert result["confidence"] == 72
        assert result["regime_shift"] == "risk-off"

    @patch("engine.scenario_sim._build_current_context", return_value="")
    @patch("engine.scenario_sim.get_client")
    @patch("engine.scenario_sim.logged_create")
    def test_run_scenario_normalizes_invalid_direction(
        self, mock_logged, mock_client, mock_ctx
    ):
        from engine.scenario_sim import run_scenario

        payload = {
            "impacts": [
                {
                    "ticker": "AAPL",
                    "impact_pct": 2.0,
                    "direction": "SIDEWAYS",
                    "severity": "WRONG",
                    "reasoning": "ok",
                    "time_horizon": "1w",
                    "key_level": 200,
                },
            ],
            "portfolio_delta_pct": 2.0,
            "summary": "ok",
            "confidence": 55,
        }
        mock_logged.return_value = (_make_llm_response(payload), {})

        result = run_scenario("good news", ["AAPL"])
        # "SIDEWAYS" lowered to "sideways" not in allowed set -> neutral
        assert result["impacts"][0]["direction"] == "neutral"
        # "WRONG" lowered to "wrong" not in allowed set -> medium
        assert result["impacts"][0]["severity"] == "medium"

    @patch("engine.scenario_sim._build_current_context", return_value="")
    @patch("engine.scenario_sim.get_client")
    @patch("engine.scenario_sim.logged_create")
    def test_run_scenario_valid_direction_preserved(
        self, mock_logged, mock_client, mock_ctx
    ):
        from engine.scenario_sim import run_scenario

        payload = {
            "impacts": [
                {
                    "ticker": "AAPL",
                    "impact_pct": 3.0,
                    "direction": "bullish",
                    "severity": "low",
                    "reasoning": "good",
                    "time_horizon": "1d",
                    "key_level": 200,
                },
            ],
            "portfolio_delta_pct": 3.0,
            "summary": "ok",
            "confidence": 60,
        }
        mock_logged.return_value = (_make_llm_response(payload), {})

        result = run_scenario("earnings beat", ["AAPL"])
        assert result["impacts"][0]["direction"] == "bullish"
        assert result["impacts"][0]["severity"] == "low"

    @patch("engine.scenario_sim._build_current_context", return_value="")
    @patch("engine.scenario_sim.get_client")
    @patch(
        "engine.scenario_sim.logged_create", side_effect=Exception("LLM down")
    )
    def test_run_scenario_fallback_on_error(
        self, mock_logged, mock_client, mock_ctx
    ):
        from engine.scenario_sim import run_scenario

        result = run_scenario("crash", ["NVDA", "AAPL"])
        assert result["confidence"] == 0
        assert len(result["impacts"]) == 2
        assert all(i["direction"] == "neutral" for i in result["impacts"])

    @patch("engine.scenario_sim._build_current_context", return_value="")
    @patch("engine.scenario_sim.get_client")
    @patch("engine.scenario_sim.logged_create")
    def test_run_scenario_equal_weights_default(
        self, mock_logged, mock_client, mock_ctx
    ):
        from engine.scenario_sim import run_scenario

        payload = {
            "impacts": [],
            "portfolio_delta_pct": 0,
            "summary": "",
            "confidence": 50,
        }
        mock_logged.return_value = (_make_llm_response(payload), {})

        result = run_scenario("neutral", ["A", "B", "C", "D"])
        assert result["confidence"] == 50

    @patch("engine.scenario_sim._build_current_context", return_value="")
    @patch("engine.scenario_sim.get_client")
    @patch("engine.scenario_sim.logged_create")
    def test_confidence_clamped_high(self, mock_logged, mock_client, mock_ctx):
        from engine.scenario_sim import run_scenario

        payload = {
            "impacts": [],
            "portfolio_delta_pct": 0,
            "summary": "",
            "confidence": 999,
        }
        mock_logged.return_value = (_make_llm_response(payload), {})
        result = run_scenario("x", ["A"])
        assert result["confidence"] == 100

    @patch("engine.scenario_sim._build_current_context", return_value="")
    @patch("engine.scenario_sim.get_client")
    @patch("engine.scenario_sim.logged_create")
    def test_confidence_clamped_low(self, mock_logged, mock_client, mock_ctx):
        from engine.scenario_sim import run_scenario

        payload = {
            "impacts": [],
            "portfolio_delta_pct": 0,
            "summary": "",
            "confidence": -50,
        }
        mock_logged.return_value = (_make_llm_response(payload), {})
        result = run_scenario("x", ["A"])
        assert result["confidence"] == 0

    def test_scenario_templates_exist(self):
        from engine.scenario_sim import SCENARIO_TEMPLATES

        assert "rate_hike" in SCENARIO_TEMPLATES
        assert "black_swan" in SCENARIO_TEMPLATES
        assert len(SCENARIO_TEMPLATES) >= 5


# ════════════════════════════════════════════════════════════════════
# 2. engine/bias_tracker.py
# ════════════════════════════════════════════════════════════════════


class TestBiasTracker:
    """Tests for engine/bias_tracker.py — pattern detection + recommendations."""

    def test_detect_directional_bias(self):
        from engine.bias_tracker import _detect_patterns

        evaluated = [{"decision": "BUY"}] * 10
        patterns = _detect_patterns(
            evaluated=evaluated,
            buy_acc=0.8,
            sell_acc=0.4,
            calibration=[],
            ticker_stats={},
        )
        types = [p["type"] for p in patterns]
        assert "directional_bias" in types

    def test_detect_overconfidence(self):
        from engine.bias_tracker import _detect_patterns

        calibration = [
            {
                "range": "0-35",
                "label": "very_low",
                "count": 10,
                "accuracy": 0.7,
                "avg_return": 0.01,
            },
            {
                "range": "35-50",
                "label": "low",
                "count": 5,
                "accuracy": 0.6,
                "avg_return": 0.01,
            },
            {
                "range": "50-65",
                "label": "moderate",
                "count": 5,
                "accuracy": 0.5,
                "avg_return": 0.0,
            },
            {
                "range": "65-100",
                "label": "high",
                "count": 10,
                "accuracy": 0.45,
                "avg_return": -0.01,
            },
        ]
        evaluated = [{"decision": "BUY"}] * 5 + [{"decision": "SELL"}] * 5
        patterns = _detect_patterns(evaluated, 0.5, 0.5, calibration, {})
        types = [p["type"] for p in patterns]
        assert "overconfidence" in types

    def test_detect_ticker_weakness(self):
        from engine.bias_tracker import _detect_patterns

        ticker_stats = {
            "TSLA": {"count": 5, "accuracy": 0.2, "avg_return": -0.03}
        }
        evaluated = [{"decision": "BUY"}] * 5 + [{"decision": "SELL"}] * 5
        patterns = _detect_patterns(evaluated, 0.5, 0.5, [], ticker_stats)
        assert any(p["type"] == "ticker_weakness" for p in patterns)

    def test_detect_bull_bias(self):
        from engine.bias_tracker import _detect_patterns

        evaluated = [{"decision": "BUY"}] * 80 + [{"decision": "SELL"}] * 20
        patterns = _detect_patterns(evaluated, 0.5, 0.5, [], {})
        assert any(p["type"] == "bull_bias" for p in patterns)

    def test_detect_bear_bias(self):
        from engine.bias_tracker import _detect_patterns

        evaluated = [{"decision": "BUY"}] * 10 + [{"decision": "SELL"}] * 90
        patterns = _detect_patterns(evaluated, 0.5, 0.5, [], {})
        assert any(p["type"] == "bear_bias" for p in patterns)

    def test_no_directional_bias_when_close(self):
        from engine.bias_tracker import _detect_patterns

        evaluated = [{"decision": "BUY"}] * 5 + [{"decision": "SELL"}] * 5
        patterns = _detect_patterns(evaluated, 0.55, 0.50, [], {})
        assert not any(p["type"] == "directional_bias" for p in patterns)

    def test_build_recommendations_directional(self):
        from engine.bias_tracker import _build_recommendations

        patterns = [
            {
                "type": "directional_bias",
                "bias_direction": "SELL",
                "magnitude": 0.2,
            }
        ]
        recs = _build_recommendations(patterns, 0.8, 0.4, 0.6)
        assert any("SELL" in r for r in recs)

    def test_build_recommendations_low_accuracy(self):
        from engine.bias_tracker import _build_recommendations

        recs = _build_recommendations([], 0.4, 0.4, 0.40)
        assert any("below 45%" in r for r in recs)

    def test_build_recommendations_no_issues(self):
        from engine.bias_tracker import _build_recommendations

        recs = _build_recommendations([], 0.6, 0.6, 0.65)
        assert any("No significant" in r for r in recs)

    def test_evaluate_decisions_buy_correct(self):
        from engine.bias_tracker import _evaluate_decisions

        decisions = [
            {
                "ticker": "NVDA",
                "decision": "BUY",
                "timestamp": datetime.now().isoformat(),
                "confidence": 70,
                "risk_level": "LOW",
                "mode": "scalp",
                "source": "test",
            },
        ]
        with patch(
            "engine.bias_tracker._get_forward_returns_batch",
            return_value={decisions[0]["timestamp"]: 0.05},
        ):
            evaluated = _evaluate_decisions(decisions, forward_days=5)
        assert len(evaluated) == 1
        assert evaluated[0]["correct"] is True

    def test_evaluate_decisions_sell_correct(self):
        from engine.bias_tracker import _evaluate_decisions

        ts = datetime.now().isoformat()
        decisions = [
            {
                "ticker": "AAPL",
                "decision": "SELL",
                "timestamp": ts,
                "confidence": 60,
                "risk_level": "HIGH",
                "mode": "predict",
                "source": "test",
            },
        ]
        with patch(
            "engine.bias_tracker._get_forward_returns_batch",
            return_value={ts: -0.03},
        ):
            evaluated = _evaluate_decisions(decisions)
        assert evaluated[0]["correct"] is True

    def test_evaluate_decisions_skips_wait(self):
        from engine.bias_tracker import _evaluate_decisions

        ts = datetime.now().isoformat()
        decisions = [
            {
                "ticker": "NVDA",
                "decision": "WAIT",
                "timestamp": ts,
                "confidence": 50,
                "risk_level": "LOW",
                "mode": "scalp",
                "source": "test",
            },
        ]
        with patch(
            "engine.bias_tracker._get_forward_returns_batch", return_value={}
        ):
            evaluated = _evaluate_decisions(decisions)
        assert len(evaluated) == 0


# ════════════════════════════════════════════════════════════════════
# 3. engine/role_memory.py
# ════════════════════════════════════════════════════════════════════


class TestRoleMemory:
    """Tests for engine/role_memory.py — RoleMemory class."""

    def _make_memory(self, tmp_path: Path) -> "RoleMemory":
        from engine.role_memory import RoleMemory

        return RoleMemory(path=tmp_path / "role_mem.json")

    def test_record_prediction(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_prediction(
            "Conservative Analyst",
            "NVDA",
            "BULLISH",
            40,
            70,
            reasoning="Strong earnings.",
            key_factor="Earnings beat",
        )
        role = mem._data["roles"]["Conservative Analyst"]
        assert len(role["predictions"]) == 1
        assert role["predictions"][0]["bias"] == "BULLISH"

    def test_update_outcomes_bullish_correct(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_prediction("Aggressive Trader", "AAPL", "BULLISH", 60, 80)
        updated = mem.update_outcomes("AAPL", actual_return=0.03)
        assert updated == 1
        pred = mem._data["roles"]["Aggressive Trader"]["predictions"][0]
        assert pred["correct"] is True

    def test_update_outcomes_bearish_correct(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_prediction("Macro Strategist", "TSLA", "BEARISH", -50, 75)
        updated = mem.update_outcomes("TSLA", actual_return=-0.04)
        assert updated == 1
        pred = mem._data["roles"]["Macro Strategist"]["predictions"][0]
        assert pred["correct"] is True

    def test_update_outcomes_neutral_correct(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_prediction("Quant Researcher", "SPY", "NEUTRAL", 0, 60)
        updated = mem.update_outcomes("SPY", actual_return=0.001)
        assert updated == 1
        pred = mem._data["roles"]["Quant Researcher"]["predictions"][0]
        assert pred["correct"] is True

    def test_update_outcomes_wrong(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_prediction(
            "Conservative Analyst", "GLD", "BULLISH", 30, 65
        )
        mem.update_outcomes("GLD", actual_return=-0.05)
        pred = mem._data["roles"]["Conservative Analyst"]["predictions"][0]
        assert pred["correct"] is False

    def test_update_outcomes_skips_resolved(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_prediction("Aggressive Trader", "NVDA", "BULLISH", 50, 80)
        mem.update_outcomes("NVDA", actual_return=0.02)
        updated = mem.update_outcomes("NVDA", actual_return=-0.02)
        assert updated == 0

    def test_update_outcomes_skips_wrong_ticker(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_prediction("Aggressive Trader", "NVDA", "BULLISH", 50, 80)
        updated = mem.update_outcomes("AAPL", actual_return=0.02)
        assert updated == 0

    def test_get_role_context_empty(self, tmp_path):
        mem = self._make_memory(tmp_path)
        ctx = mem.get_role_context("NonExistent", "NVDA")
        assert ctx == ""

    def test_get_role_context_insufficient_data(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_prediction(
            "Conservative Analyst", "NVDA", "BULLISH", 30, 60
        )
        mem.update_outcomes("NVDA", actual_return=0.02)
        # Only 1 total, needs >= 3
        ctx = mem.get_role_context("Conservative Analyst", "NVDA")
        assert ctx == ""

    def test_get_role_context_with_data(self, tmp_path):
        mem = self._make_memory(tmp_path)
        for _ in range(5):
            mem.record_prediction(
                "Conservative Analyst", "NVDA", "BULLISH", 30, 60
            )
            mem.update_outcomes("NVDA", actual_return=0.02)
        ctx = mem.get_role_context("Conservative Analyst", "NVDA")
        assert "TRACK RECORD" in ctx
        assert "NVDA" in ctx

    def test_max_records_capped(self, tmp_path):
        from engine.role_memory import _MAX_RECORDS_PER_ROLE

        mem = self._make_memory(tmp_path)
        for _ in range(_MAX_RECORDS_PER_ROLE + 50):
            mem.record_prediction("Aggressive Trader", "X", "BULLISH", 10, 50)
        preds = mem._data["roles"]["Aggressive Trader"]["predictions"]
        assert len(preds) == _MAX_RECORDS_PER_ROLE

    def test_get_all_role_stats(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_prediction(
            "Conservative Analyst", "NVDA", "BULLISH", 30, 60
        )
        mem.update_outcomes("NVDA", actual_return=0.02)
        stats = mem.get_all_role_stats()
        assert "Conservative Analyst" in stats
        assert stats["Conservative Analyst"]["total"] == 1

    def test_persistence_round_trip(self, tmp_path):
        from engine.role_memory import RoleMemory

        path = tmp_path / "rm.json"
        mem1 = RoleMemory(path=path)
        mem1.record_prediction("Quant Researcher", "MSFT", "BEARISH", -20, 55)
        mem2 = RoleMemory(path=path)
        assert "Quant Researcher" in mem2._data["roles"]


# ════════════════════════════════════════════════════════════════════
# 4. engine/signal_fusion.py
# ════════════════════════════════════════════════════════════════════


class TestSignalFusion:
    """Tests for engine/signal_fusion.py — scoring helpers + fuse_signals."""

    def test_score_technical_overbought(self):
        from engine.signal_fusion import _score_technical

        result = _score_technical(
            {"rsi": 75, "close": 100, "ma20": 95, "ma50": 90}
        )
        assert result["score"] < 0
        assert "RSI overbought" in result["signals"]

    def test_score_technical_oversold(self):
        from engine.signal_fusion import _score_technical

        result = _score_technical({"rsi": 25})
        assert result["score"] > 0
        assert "RSI oversold" in result["signals"]

    def test_score_technical_bullish_ma(self):
        from engine.signal_fusion import _score_technical

        result = _score_technical(
            {"rsi": 55, "close": 110, "ma20": 105, "ma50": 100}
        )
        assert "Bullish MA alignment" in result["signals"]

    def test_score_technical_bearish_ma(self):
        from engine.signal_fusion import _score_technical

        result = _score_technical(
            {"rsi": 45, "close": 90, "ma20": 95, "ma50": 100}
        )
        assert "Bearish MA alignment" in result["signals"]

    def test_score_technical_adx_amplifies(self):
        from engine.signal_fusion import _score_technical

        without_adx = _score_technical(
            {"rsi": 25, "close": 110, "ma20": 105, "ma50": 100}
        )
        with_adx = _score_technical(
            {"rsi": 25, "close": 110, "ma20": 105, "ma50": 100, "adx": 30}
        )
        assert abs(with_adx["score"]) >= abs(without_adx["score"])

    def test_score_ml_no_data(self):
        from engine.signal_fusion import _score_ml

        result = _score_ml(None)
        assert result["score"] == 0
        assert result["available"] is False

    def test_score_ml_with_models(self):
        from engine.signal_fusion import _score_ml

        ml_result = {
            "results": {
                "random_forest": {
                    "status": "ok",
                    "metrics": {"sharpe": 1.5, "total_return": 0.1},
                },
                "xgboost": {
                    "status": "ok",
                    "metrics": {"sharpe": 0.8, "total_return": 0.05},
                },
            }
        }
        result = _score_ml(ml_result)
        assert result["available"] is True
        assert result["n_models"] == 2
        assert result["score"] > 0

    def test_score_ml_failed_models_skipped(self):
        from engine.signal_fusion import _score_ml

        ml_result = {
            "results": {
                "random_forest": {"status": "error", "metrics": {}},
                "xgboost": {
                    "status": "ok",
                    "metrics": {"sharpe": 1.0, "total_return": 0.05},
                },
            }
        }
        result = _score_ml(ml_result)
        assert result["n_models"] == 1

    def test_score_news_empty(self):
        from engine.signal_fusion import _score_news

        result = _score_news([])
        assert result["score"] == 0
        assert result["available"] is False

    def test_score_news_bullish(self):
        from engine.signal_fusion import _score_news

        # All scores > 0.1 threshold
        items = [{"score": 0.3}, {"score": 0.5}, {"score": 0.2}]
        result = _score_news(items)
        assert result["score"] > 0
        assert result["available"] is True
        assert result["bullish_count"] == 3

    def test_score_news_bearish(self):
        from engine.signal_fusion import _score_news

        items = [{"score": -0.3}, {"score": -0.5}]
        result = _score_news(items)
        assert result["score"] < 0
        assert result["bearish_count"] == 2

    @patch(
        "engine.signal_fusion._fetch_options_flow",
        return_value={"available": False},
    )
    @patch(
        "engine.signal_fusion._fetch_institutional_signals",
        return_value={"available": False},
    )
    def test_fuse_signals_tech_only(self, mock_inst, mock_opt):
        from engine.signal_fusion import fuse_signals

        summary = {"rsi": 25, "close": 100, "ma20": 95, "ma50": 90}
        result = fuse_signals("NVDA", summary=summary)
        assert "conviction" in result
        assert result["direction"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert result["n_sources"] >= 1

    @patch(
        "engine.signal_fusion._fetch_prediction_markets_signal",
        return_value={"available": False, "score": 0},
    )
    @patch(
        "engine.signal_fusion._fetch_earnings_signal",
        return_value={"available": False, "score": 0},
    )
    @patch(
        "engine.signal_fusion._fetch_social_signal",
        return_value={"available": False, "score": 0},
    )
    @patch(
        "engine.signal_fusion._fetch_options_flow",
        return_value={"available": False},
    )
    @patch(
        "engine.signal_fusion._fetch_institutional_signals",
        return_value={"available": False},
    )
    def test_fuse_signals_no_sources(
        self, mock_inst, mock_opt, mock_social, mock_earnings, mock_pred
    ):
        from engine.signal_fusion import fuse_signals

        result = fuse_signals("NVDA")
        assert result["conviction"] == 0
        assert result["direction"] == "NEUTRAL"

    @patch(
        "engine.signal_fusion._fetch_prediction_markets_signal",
        return_value={"available": False, "score": 0},
    )
    @patch(
        "engine.signal_fusion._fetch_earnings_signal",
        return_value={"available": False, "score": 0},
    )
    @patch(
        "engine.signal_fusion._fetch_social_signal",
        return_value={"available": False, "score": 0},
    )
    @patch(
        "engine.signal_fusion._fetch_options_flow",
        return_value={"available": True, "score": 60},
    )
    @patch(
        "engine.signal_fusion._fetch_institutional_signals",
        return_value={"available": True, "score": 40},
    )
    def test_fuse_signals_all_sources(
        self, mock_inst, mock_opt, mock_social, mock_earnings, mock_pred
    ):
        from engine.signal_fusion import fuse_signals

        summary = {"rsi": 30}
        ml_result = {
            "results": {
                "random_forest": {
                    "status": "ok",
                    "metrics": {"sharpe": 2.0, "total_return": 0.15},
                }
            }
        }
        news = [{"score": 0.4}, {"score": 0.3}]

        result = fuse_signals(
            "NVDA", summary=summary, ml_result=ml_result, news_items=news
        )
        assert result["n_sources"] >= 3
        assert result["direction"] == "BULLISH"

    @patch(
        "engine.signal_fusion._fetch_prediction_markets_signal",
        return_value={"available": False, "score": 0},
    )
    @patch(
        "engine.signal_fusion._fetch_earnings_signal",
        return_value={"available": False, "score": 0},
    )
    @patch(
        "engine.signal_fusion._fetch_social_signal",
        return_value={"available": False, "score": 0},
    )
    @patch(
        "engine.signal_fusion._fetch_options_flow",
        return_value={"available": False},
    )
    @patch(
        "engine.signal_fusion._fetch_institutional_signals",
        return_value={"available": False},
    )
    def test_fuse_signals_custom_weights(
        self, mock_inst, mock_opt, mock_social, mock_earnings, mock_pred
    ):
        from engine.signal_fusion import fuse_signals

        custom = {
            "technical": 1.0,
            "ml_ensemble": 0,
            "news_sentiment": 0,
            "options_flow": 0,
            "institutional": 0,
            "social_sentiment": 0,
            "earnings": 0,
            "prediction_markets": 0,
        }
        result = fuse_signals("NVDA", summary={"rsi": 25}, weights=custom)
        assert result["n_sources"] >= 1


# ════════════════════════════════════════════════════════════════════
# 5. engine/micro_swarm.py
# ════════════════════════════════════════════════════════════════════


class TestMicroSwarm:
    """Tests for engine/micro_swarm.py — SwarmAgent + run_swarm_simulation."""

    def test_create_agents_count(self):
        from engine.micro_swarm import _create_agents

        agents = _create_agents()
        assert len(agents) == 20

    def test_create_agents_types(self):
        from engine.micro_swarm import _create_agents

        agents = _create_agents()
        types = [a.agent_type for a in agents]
        assert types.count("momentum") == 5
        assert types.count("mean_reversion") == 5
        assert types.count("news_reactor") == 3
        assert types.count("institutional") == 3
        assert types.count("retail") == 4

    def test_swarm_agent_momentum_positive_shock(self):
        from engine.micro_swarm import SwarmAgent

        agent = SwarmAgent(
            name="M1",
            agent_type="momentum",
            risk_appetite=0.8,
            reaction_speed=0,
            contrarian=False,
            noise=0.0,
        )
        pos = agent.react(
            price_change=0.05, sentiment=0, step=0, crowd_position=0
        )
        assert pos > 0

    def test_swarm_agent_mean_reversion_fades(self):
        from engine.micro_swarm import SwarmAgent

        agent = SwarmAgent(
            name="MR1",
            agent_type="mean_reversion",
            risk_appetite=0.8,
            reaction_speed=0,
            contrarian=True,
            noise=0.0,
        )
        pos = agent.react(
            price_change=0.05, sentiment=0, step=0, crowd_position=0
        )
        assert pos < 0

    def test_swarm_agent_delayed_reaction(self):
        from engine.micro_swarm import SwarmAgent

        agent = SwarmAgent(
            name="Inst1",
            agent_type="institutional",
            risk_appetite=0.5,
            reaction_speed=5,
            contrarian=False,
            noise=0.0,
        )
        pos = agent.react(
            price_change=0.05, sentiment=0, step=2, crowd_position=0
        )
        assert pos == 0.0

    def test_swarm_agent_news_reactor(self):
        from engine.micro_swarm import SwarmAgent

        agent = SwarmAgent(
            name="N1",
            agent_type="news_reactor",
            risk_appetite=0.8,
            reaction_speed=0,
            contrarian=False,
            noise=0.0,
        )
        pos = agent.react(
            price_change=0, sentiment=0.8, step=0, crowd_position=0
        )
        assert pos > 0

    def test_swarm_agent_retail_fomo(self):
        from engine.micro_swarm import SwarmAgent

        agent = SwarmAgent(
            name="R1",
            agent_type="retail",
            risk_appetite=0.8,
            reaction_speed=0,
            contrarian=False,
            noise=0.0,
        )
        pos = agent.react(
            price_change=0.05, sentiment=0, step=0, crowd_position=0.6
        )
        assert pos > 0

    def test_swarm_agent_position_clamped(self):
        from engine.micro_swarm import SwarmAgent

        agent = SwarmAgent(
            name="M1",
            agent_type="momentum",
            risk_appetite=1.0,
            reaction_speed=0,
            contrarian=False,
            noise=0.0,
        )
        for _ in range(20):
            agent.react(
                price_change=0.5, sentiment=0, step=10, crowd_position=0
            )
        assert -1.0 <= agent.position <= 1.0

    def test_run_swarm_simulation_bearish_shock(self):
        from engine.micro_swarm import run_swarm_simulation

        np.random.seed(42)
        result = run_swarm_simulation(
            shock_pct=-8.0,
            sentiment=-0.8,
            rsi=72,
            adx=30,
            n_simulations=20,
            ticker="NVDA",
        )
        assert result["convergence"] in ("BUY", "SELL", "MIXED")
        assert 0 <= result["conviction"] <= 100
        assert result["convergence_speed"] in (
            "fast",
            "medium",
            "slow",
            "none",
        )
        assert result["ticker"] == "NVDA"

    def test_run_swarm_simulation_neutral(self):
        from engine.micro_swarm import run_swarm_simulation

        np.random.seed(123)
        result = run_swarm_simulation(
            shock_pct=0.0, sentiment=0.0, rsi=50, adx=15, n_simulations=20
        )
        assert (
            result["buy_pct"] + result["sell_pct"] + result["mixed_pct"]
            == 100
        )

    def test_run_swarm_simulation_sample_path(self):
        from engine.micro_swarm import run_swarm_simulation

        np.random.seed(7)
        result = run_swarm_simulation(
            shock_pct=3.0, sentiment=0.5, rsi=45, adx=28, n_simulations=10
        )
        assert len(result["sample_path"]) <= 10
        for point in result["sample_path"]:
            assert "step" in point
            assert "avg_position" in point

    def test_run_swarm_simulation_strong_bullish(self):
        from engine.micro_swarm import run_swarm_simulation

        np.random.seed(0)
        result = run_swarm_simulation(
            shock_pct=10.0,
            sentiment=1.0,
            rsi=35,
            adx=35,
            n_simulations=30,
        )
        assert result["buy_pct"] >= result["sell_pct"]

    def test_run_swarm_simulation_inputs_preserved(self):
        from engine.micro_swarm import run_swarm_simulation

        np.random.seed(0)
        result = run_swarm_simulation(
            shock_pct=5.0, sentiment=0.3, rsi=60, adx=22, n_simulations=5
        )
        assert result["inputs"]["shock_pct"] == 5.0
        assert result["inputs"]["sentiment"] == 0.3
        assert result["inputs"]["rsi"] == 60
        assert result["n_simulations"] == 5


# ════════════════════════════════════════════════════════════════════
# 6. llm/perspective_panel.py
# ════════════════════════════════════════════════════════════════════


class TestPerspectivePanel:
    """Tests for llm/perspective_panel.py — roles, context, consensus."""

    def test_roles_defined(self):
        from llm.perspective_panel import ROLES

        assert len(ROLES) == 4
        names = {r["name"] for r in ROLES}
        assert "Conservative Analyst" in names
        assert "Aggressive Trader" in names

    def test_build_panel_context(self):
        from llm.perspective_panel import _build_panel_context

        summary = {
            "close": 150.0,
            "ma20": 145,
            "ma50": 140,
            "rsi": 55,
            "macd_hist": 0.3,
            "bb_pct": 0.6,
            "adx": 28,
            "volume_ratio": 1.2,
        }
        ctx = _build_panel_context(summary, "AAPL", "good news", "RF bullish")
        assert "AAPL" in ctx
        assert "$150.00" in ctx
        assert "good news" in ctx

    def test_build_panel_context_no_extras(self):
        from llm.perspective_panel import _build_panel_context

        summary = {
            "close": 100.0,
            "ma20": 95,
            "ma50": 90,
            "rsi": 50,
            "macd_hist": 0,
            "bb_pct": 0.5,
            "adx": 20,
            "volume_ratio": 1.0,
        }
        ctx = _build_panel_context(summary, "NVDA", "", "")
        assert "NVDA" in ctx
        assert "NEWS" not in ctx

    def test_perspective_result_dataclass(self):
        from llm.perspective_panel import PerspectiveResult

        pr = PerspectiveResult(
            role="Conservative Analyst",
            icon="shield",
            bias="BEARISH",
            score=-30,
            conviction=65,
            reasoning="Downside risk.",
            key_factor="Support broken",
        )
        assert pr.bias == "BEARISH"
        assert pr.score == -30

    @patch(
        "engine.role_memory.RoleMemory",
        side_effect=Exception("no mem"),
    )
    @patch("llm.perspective_panel.get_client")
    @patch("llm.perspective_panel.logged_create")
    def test_run_perspective_panel_all_bullish(
        self, mock_logged, mock_client, mock_mem_cls
    ):
        from llm.perspective_panel import run_perspective_panel

        mock_logged.return_value = (
            _make_llm_response(
                {
                    "bias": "BULLISH",
                    "score": 50,
                    "conviction": 70,
                    "reasoning": "Strong momentum.",
                    "key_factor": "Breakout",
                }
            ),
            {},
        )

        summary = {
            "close": 100,
            "ma20": 95,
            "ma50": 90,
            "rsi": 55,
            "macd_hist": 0.2,
            "bb_pct": 0.5,
            "adx": 25,
            "volume_ratio": 1.1,
        }

        result = run_perspective_panel(summary, "NVDA")
        assert result["consensus"] == "BULLISH"
        assert result["avg_score"] > 0
        assert len(result["perspectives"]) == 4
        assert result["agreement"] == 100

    @patch(
        "engine.role_memory.RoleMemory",
        side_effect=Exception("no mem"),
    )
    @patch("llm.perspective_panel.get_client")
    @patch(
        "llm.perspective_panel.logged_create",
        side_effect=Exception("API error"),
    )
    def test_run_perspective_panel_all_fail(
        self, mock_logged, mock_client, mock_mem_cls
    ):
        from llm.perspective_panel import run_perspective_panel

        summary = {
            "close": 100,
            "ma20": 95,
            "ma50": 90,
            "rsi": 50,
            "macd_hist": 0,
            "bb_pct": 0.5,
            "adx": 20,
            "volume_ratio": 1.0,
        }

        result = run_perspective_panel(summary, "NVDA")
        assert result["consensus"] == "NEUTRAL"
        assert result["agreement"] == 0

    @patch(
        "engine.role_memory.RoleMemory",
        side_effect=Exception("no mem"),
    )
    @patch("llm.perspective_panel.get_client")
    @patch("llm.perspective_panel.logged_create")
    def test_run_perspective_panel_mixed(
        self, mock_logged, mock_client, mock_mem_cls
    ):
        from llm.perspective_panel import run_perspective_panel

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] % 2 == 1:
                data = {
                    "bias": "BULLISH",
                    "score": 40,
                    "conviction": 60,
                    "reasoning": "up",
                    "key_factor": "momentum",
                }
            else:
                data = {
                    "bias": "BEARISH",
                    "score": -40,
                    "conviction": 60,
                    "reasoning": "down",
                    "key_factor": "resistance",
                }
            return (_make_llm_response(data), {})

        mock_logged.side_effect = side_effect

        summary = {
            "close": 100,
            "ma20": 100,
            "ma50": 100,
            "rsi": 50,
            "macd_hist": 0,
            "bb_pct": 0.5,
            "adx": 20,
            "volume_ratio": 1.0,
        }

        result = run_perspective_panel(summary, "NVDA")
        assert len(result["perspectives"]) == 4
        assert result["panel_summary"]

    def test_call_perspective_invalid_bias_normalized(self):
        from llm.perspective_panel import _call_perspective

        client = MagicMock()
        role = {
            "name": "Test",
            "icon": "X",
            "system": "test",
            "focus": "test",
        }

        with patch(
            "llm.perspective_panel.logged_create",
            return_value=(
                _make_llm_response(
                    {
                        "bias": "INVALID",
                        "score": 10,
                        "conviction": 50,
                        "reasoning": "ok",
                        "key_factor": "ok",
                    }
                ),
                {},
            ),
        ):
            result = _call_perspective(client, role, "ctx", "NVDA")
        assert result.bias == "NEUTRAL"

    def test_call_perspective_score_clamped(self):
        from llm.perspective_panel import _call_perspective

        client = MagicMock()
        role = {
            "name": "Test",
            "icon": "X",
            "system": "test",
            "focus": "test",
        }

        with patch(
            "llm.perspective_panel.logged_create",
            return_value=(
                _make_llm_response(
                    {
                        "bias": "BULLISH",
                        "score": 999,
                        "conviction": 200,
                        "reasoning": "ok",
                        "key_factor": "ok",
                    }
                ),
                {},
            ),
        ):
            result = _call_perspective(client, role, "ctx", "NVDA")
        assert result.score == 100
        assert result.conviction == 100
