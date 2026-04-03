"""Tests for llm/strategy_explainer.py — dataclass + parsing logic (no LLM calls)."""
import pytest
from llm.strategy_explainer import StrategyExplanation, StrategyExplainer


class TestStrategyExplanation:
    def test_to_dict(self):
        exp = StrategyExplanation(
            strategy_name="double_ma", ticker="NVDA",
            regime_analysis="Works in trending markets",
            strength_summary="Good momentum capture",
            weakness_summary="Fails in choppy markets",
            improvement_suggestions="Add ADX filter",
            window_narratives=["Window 0: strong trend", "Window 1: mean reversion killed it"],
            overall_assessment="Viable but needs regime filter",
        )
        d = exp.to_dict()
        assert d["strategy_name"] == "double_ma"
        assert d["ticker"] == "NVDA"
        assert len(d["window_narratives"]) == 2
        assert "trending" in d["regime_analysis"].lower()

    def test_to_markdown(self):
        exp = StrategyExplanation(
            strategy_name="rsi_reversal", ticker="AAPL",
            regime_analysis="Mean reversion regime",
            strength_summary="Catches oversold bounces",
            weakness_summary="Fails in strong trends",
            improvement_suggestions="Add trend filter",
            window_narratives=["Window 0: bounce", "Window 1: no signal"],
            overall_assessment="Limited use",
        )
        md = exp.to_markdown()
        assert "### rsi_reversal on AAPL" in md
        assert "**Assessment:**" in md
        assert "**Regime Analysis:**" in md
        assert "**Strengths:**" in md
        assert "**Weaknesses:**" in md
        assert "**Suggestions:**" in md
        assert "Window 0:" in md
        assert "Window 1:" in md

    def test_to_markdown_no_windows(self):
        exp = StrategyExplanation(
            strategy_name="test", ticker="TEST",
            regime_analysis="N/A", strength_summary="N/A",
            weakness_summary="N/A", improvement_suggestions="N/A",
        )
        md = exp.to_markdown()
        assert "Per-Window" not in md

    def test_empty_fields(self):
        exp = StrategyExplanation(
            strategy_name="", ticker="",
            regime_analysis="", strength_summary="",
            weakness_summary="", improvement_suggestions="",
        )
        d = exp.to_dict()
        assert d["strategy_name"] == ""
        assert d["window_narratives"] == []
        assert d["overall_assessment"] == ""


class TestParseExplanation:
    def test_parse_structured_response(self):
        explainer = StrategyExplainer()

        class MockWF:
            windows = []
            num_windows = 0
            avg_oos_sharpe = 1.2
            pct_positive_sharpe = 0.6
            avg_oos_return = 0.05
            avg_information_ratio = 0.3
            passed = False

        text = """**Regime Analysis**: The strategy performs well in trending markets.
Specifically, windows with clear directional moves showed positive Sharpe.

**Strengths**: Good at capturing momentum breakouts. Low drawdown in trends.

**Weaknesses**: Whipsawed in range-bound markets. Too many false signals in Q3.

**Improvement Suggestions**:
1. Add ADX > 25 filter to avoid choppy markets
2. Widen stop-loss from 2% to 3%

**Overall Assessment**: A decent trend-following strategy that needs regime awareness."""

        result = explainer._parse_explanation(text, "double_ma", "NVDA", MockWF())
        assert isinstance(result, StrategyExplanation)
        assert result.strategy_name == "double_ma"
        assert result.ticker == "NVDA"
        assert len(result.regime_analysis) > 0
        # Parser may not extract all sections depending on format
        # but at least regime_analysis and improvement_suggestions should parse
        assert len(result.improvement_suggestions) > 0

    def test_parse_unstructured_response(self):
        explainer = StrategyExplainer()

        class MockWF:
            windows = []
            num_windows = 0
            avg_oos_sharpe = 0.5
            pct_positive_sharpe = 0.3
            avg_oos_return = -0.02
            avg_information_ratio = -0.5
            passed = False

        text = "This strategy doesn't work very well. It loses money in most conditions."
        result = explainer._parse_explanation(text, "bad_strat", "TEST", MockWF())
        assert isinstance(result, StrategyExplanation)
        assert result.strategy_name == "bad_strat"


class TestStrategyExplainerInit:
    def test_init(self):
        explainer = StrategyExplainer()
        assert explainer._total_cost == 0.0
