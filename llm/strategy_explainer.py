"""
llm/strategy_explainer.py
────────────────────────────────────────────────────────────────────────────
LLM-as-explainer: uses Claude to analyze WHY strategies succeed or fail
in different market regimes.

Feeds walk-forward window results to the LLM for narrative explanation
of performance patterns, regime classification, and improvement suggestions.

Usage:
    from llm.strategy_explainer import StrategyExplainer
    explainer = StrategyExplainer()
    report = explainer.explain_strategy("double_ma", wf_result, ticker="NVDA")
    full = explainer.explain_all(harness_result)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from core.logger import get_logger

logger = get_logger("strategy_explainer")


@dataclass
class StrategyExplanation:
    """LLM-generated explanation of strategy performance."""
    strategy_name: str
    ticker: str
    regime_analysis: str       # Which market regimes the strategy works/fails in
    strength_summary: str      # What the strategy does well
    weakness_summary: str      # Where it breaks down
    improvement_suggestions: str  # Concrete parameter/logic changes
    window_narratives: list[str] = field(default_factory=list)  # Per-window explanations
    overall_assessment: str = ""  # 1-line verdict

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "ticker": self.ticker,
            "regime_analysis": self.regime_analysis,
            "strength_summary": self.strength_summary,
            "weakness_summary": self.weakness_summary,
            "improvement_suggestions": self.improvement_suggestions,
            "window_narratives": self.window_narratives,
            "overall_assessment": self.overall_assessment,
        }

    def to_markdown(self) -> str:
        """Format as readable markdown."""
        lines = [
            f"### {self.strategy_name} on {self.ticker}",
            f"**Assessment:** {self.overall_assessment}",
            "",
            f"**Regime Analysis:** {self.regime_analysis}",
            "",
            f"**Strengths:** {self.strength_summary}",
            "",
            f"**Weaknesses:** {self.weakness_summary}",
            "",
            f"**Suggestions:** {self.improvement_suggestions}",
        ]
        if self.window_narratives:
            lines.append("")
            lines.append("**Per-Window Analysis:**")
            for i, narrative in enumerate(self.window_narratives):
                lines.append(f"- Window {i}: {narrative}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# PROMPT TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════

_EXPLAIN_PROMPT = """You are a quantitative analyst explaining strategy performance to a portfolio manager.

Strategy: {strategy_name}
Ticker: {ticker}

Walk-Forward Results ({num_windows} windows):
{window_table}

Aggregate Metrics:
- Average OOS Sharpe: {avg_sharpe:.3f}
- % Windows Positive Sharpe: {pct_positive:.0%}
- Average OOS Return: {avg_return:.2%}
- Average Information Ratio: {avg_ir:.3f}
- Pass/Fail: {"PASSED" if passed else "FAILED"}

Analyze this strategy's performance:

1. **Regime Analysis**: In which windows did the strategy succeed vs fail? What market conditions (trending, mean-reverting, volatile, calm) likely explain each? Reference specific window dates and metrics.

2. **Strengths**: What does this strategy do well? When is it most useful?

3. **Weaknesses**: Where does it break down? What market conditions kill it?

4. **Improvement Suggestions**: Give 2-3 concrete, actionable changes (parameter tweaks, additional filters, exit logic) that would address the weaknesses without destroying the strengths.

5. **Overall Assessment**: One sentence verdict.

Be specific. Reference actual window numbers, dates, and metrics. No generic advice."""


_COMPARE_PROMPT = """You are a quantitative analyst comparing strategy performance.

Here are {n_strategies} strategies evaluated on {ticker}:

{strategy_table}

Questions:
1. Which strategies complement each other (succeed in different regimes)?
2. Which are redundant (similar signals, correlated returns)?
3. What is the optimal 2-3 strategy ensemble and why?
4. What market regime is NOT covered by any strategy?

Be concrete. Reference specific strategies, metrics, and regimes."""


# ═══════════════════════════════════════════════════════════════════════════
# EXPLAINER
# ═══════════════════════════════════════════════════════════════════════════

class StrategyExplainer:
    """Uses Claude to explain strategy performance patterns."""

    def __init__(self):
        self._total_cost = 0.0

    def explain_strategy(
        self,
        strategy_name: str,
        wf_result,
        ticker: str = "UNKNOWN",
    ) -> StrategyExplanation:
        """
        Generate LLM explanation for a single strategy's walk-forward results.

        Args:
            strategy_name: Name of the strategy
            wf_result: WalkForwardResult from eval/walk_forward.py
            ticker: Stock ticker
        """
        import llm.claude_client as cc
        from llm.claude_client import get_client, _extract_text
        from llm.call_logger import logged_create

        # Build window table
        window_lines = []
        for w in wf_result.windows:
            window_lines.append(
                f"  Window {w.window_idx}: {w.test_start} to {w.test_end} | "
                f"Sharpe={w.sharpe:.2f} Return={w.total_return:.2%} "
                f"DD={w.max_drawdown:.2%} Trades={w.num_trades} "
                f"WinRate={w.win_rate:.0%} IR={w.information_ratio:.2f}"
            )
        window_table = "\n".join(window_lines) if window_lines else "No windows available"

        prompt = _EXPLAIN_PROMPT.format(
            strategy_name=strategy_name,
            ticker=ticker,
            num_windows=wf_result.num_windows,
            window_table=window_table,
            avg_sharpe=wf_result.avg_oos_sharpe,
            pct_positive=wf_result.pct_positive_sharpe,
            avg_return=wf_result.avg_oos_return,
            avg_ir=wf_result.avg_information_ratio,
            passed=wf_result.passed,
        )

        client = get_client()
        response, record = logged_create(
            client, request_type="strategy_explanation",
            model=cc.DEEP_MODEL,
            max_tokens=1500,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
            ticker=ticker,
        )

        if record:
            self._total_cost += record.estimated_cost_usd

        text = _extract_text(response)

        # Parse the response into structured sections
        explanation = self._parse_explanation(text, strategy_name, ticker, wf_result)
        return explanation

    def explain_all(
        self,
        harness_result,
        ticker: str | None = None,
    ) -> list[StrategyExplanation]:
        """
        Generate explanations for all strategies in a harness result.

        Args:
            harness_result: HarnessResult from eval/harness.py
            ticker: Optional filter for specific ticker
        """
        explanations = []
        for ev in harness_result.evaluations:
            if ticker and ev.ticker != ticker:
                continue
            if ev.walk_forward and ev.walk_forward.num_windows > 0:
                try:
                    explanation = self.explain_strategy(
                        ev.strategy_name,
                        ev.walk_forward,
                        ticker=ev.ticker,
                    )
                    explanations.append(explanation)
                except Exception as e:
                    logger.warning("Explanation failed for %s/%s: %s", ev.strategy_name, ev.ticker, e)

        logger.info("Generated %d explanations (total cost: $%.3f)", len(explanations), self._total_cost)
        return explanations

    def compare_strategies(
        self,
        harness_result,
        ticker: str,
    ) -> str:
        """
        Generate a comparative analysis of all strategies for a given ticker.

        Returns markdown-formatted comparison.
        """
        import llm.claude_client as cc
        from llm.claude_client import get_client, _extract_text
        from llm.call_logger import logged_create

        # Build strategy comparison table
        rows = []
        for ev in harness_result.evaluations:
            if ev.ticker != ticker:
                continue
            wf = ev.walk_forward
            if wf is None:
                continue
            rows.append(
                f"  {ev.strategy_name}: Sharpe={wf.avg_oos_sharpe:.2f} "
                f"PctPositive={wf.pct_positive_sharpe:.0%} "
                f"Return={wf.avg_oos_return:.2%} "
                f"IR={wf.avg_information_ratio:.2f} "
                f"Pass={'YES' if ev.overall_pass else 'NO'}"
            )

        if not rows:
            return f"No walk-forward results available for {ticker}"

        strategy_table = "\n".join(rows)
        prompt = _COMPARE_PROMPT.format(
            n_strategies=len(rows),
            ticker=ticker,
            strategy_table=strategy_table,
        )

        client = get_client()
        response, record = logged_create(
            client, request_type="strategy_comparison",
            model=cc.DEEP_MODEL,
            max_tokens=1200,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
            ticker=ticker,
        )

        if record:
            self._total_cost += record.estimated_cost_usd

        return _extract_text(response)

    def _parse_explanation(
        self,
        text: str,
        strategy_name: str,
        ticker: str,
        wf_result,
    ) -> StrategyExplanation:
        """Parse LLM response into structured StrategyExplanation."""
        sections = {
            "regime_analysis": "",
            "strength_summary": "",
            "weakness_summary": "",
            "improvement_suggestions": "",
            "overall_assessment": "",
        }

        current_key = None
        lines_buffer = []

        for line in text.split("\n"):
            lower = line.lower().strip()
            if "regime" in lower and ("analysis" in lower or ":" in lower):
                if current_key and lines_buffer:
                    sections[current_key] = "\n".join(lines_buffer).strip()
                current_key = "regime_analysis"
                lines_buffer = []
            elif "strength" in lower and (":" in lower or "**" in lower):
                if current_key and lines_buffer:
                    sections[current_key] = "\n".join(lines_buffer).strip()
                current_key = "strength_summary"
                lines_buffer = []
            elif "weakness" in lower and (":" in lower or "**" in lower):
                if current_key and lines_buffer:
                    sections[current_key] = "\n".join(lines_buffer).strip()
                current_key = "weakness_summary"
                lines_buffer = []
            elif "improvement" in lower or "suggestion" in lower:
                if current_key and lines_buffer:
                    sections[current_key] = "\n".join(lines_buffer).strip()
                current_key = "improvement_suggestions"
                lines_buffer = []
            elif "overall" in lower and ("assessment" in lower or "verdict" in lower):
                if current_key and lines_buffer:
                    sections[current_key] = "\n".join(lines_buffer).strip()
                current_key = "overall_assessment"
                lines_buffer = []
            else:
                lines_buffer.append(line)

        if current_key and lines_buffer:
            sections[current_key] = "\n".join(lines_buffer).strip()

        # Fallback: if parsing failed, put everything in regime_analysis
        if not any(sections.values()):
            sections["regime_analysis"] = text

        return StrategyExplanation(
            strategy_name=strategy_name,
            ticker=ticker,
            **sections,
        )

    @property
    def total_cost(self) -> float:
        return self._total_cost
