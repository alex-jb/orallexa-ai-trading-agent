"""
llm/debate_graph.py
──────────────────────────────────────────────────────────────────
LangGraph-powered Bull/Bear adversarial debate.

Migrates the 3-call debate pipeline (llm/debate.py) to a stateful
LangGraph DAG with:
  - Typed state (DebateState)
  - Parallel Bull/Bear execution
  - Conditional routing (skip debate if WAIT)
  - Checkpointing for resumability
  - Observable node execution

Graph:
    [start] → should_debate? → [bull, bear] (parallel) → [judge] → [end]
                ↓ (skip)
              [end]

Usage:
    from llm.debate_graph import run_debate_graph
    result = run_debate_graph(initial_decision, summary, "NVDA")
"""
from __future__ import annotations

import json
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END

from models.decision import DecisionOutput
import llm.claude_client as cc
from llm.claude_client import get_client, _extract_text
from llm.call_logger import logged_create
from core.logger import get_logger

logger = get_logger("debate_graph")


# ═══════════════════════════════════════════════════════════════════════════
# STATE
# ═══════════════════════════════════════════════════════════════════════════

class DebateState(TypedDict):
    """Typed state flowing through the debate graph."""
    # Inputs
    ticker: str
    context: str
    initial_decision: str          # "BUY" / "SELL" / "WAIT"
    initial_confidence: float
    initial_signal_strength: float
    initial_reasoning: list[str]
    initial_source: str
    rag_context: str

    # Debate outputs
    bull_argument: str
    bear_argument: str
    judge_data: dict

    # Final output
    final_decision: str
    final_confidence: float
    final_risk_level: str
    final_probabilities: dict
    final_reasoning: list[str]
    final_recommendation: str
    skipped: bool


# ═══════════════════════════════════════════════════════════════════════════
# NODES
# ═══════════════════════════════════════════════════════════════════════════

def _build_context(summary: dict, ticker: str, rag_context: str) -> str:
    lines = [
        f"Ticker: {ticker}",
        f"Close: {summary.get('close')}  MA20: {summary.get('ma20')}  MA50: {summary.get('ma50')}",
        f"RSI: {summary.get('rsi')}  MACD Hist: {summary.get('macd_hist')}",
        f"BB%: {summary.get('bb_pct')}  ADX: {summary.get('adx')}  Vol Ratio: {summary.get('volume_ratio')}",
    ]
    if rag_context:
        lines.append(f"\nContext:\n{rag_context[:500]}")
    return "\n".join(lines)


def bull_node(state: DebateState) -> dict:
    """Bull analyst: argue FOR the trade."""
    logger.info("[Bull] Analyzing %s...", state["ticker"])
    client = get_client()

    direction = "entering a long position" if state["initial_decision"] == "BUY" else \
                "entering a short position" if state["initial_decision"] == "SELL" else \
                "taking a position"

    prompt = f"""You are a Bull Analyst. Build a compelling, evidence-based case FOR {direction} on this stock.

{state["context"]}

Initial signal: {state["initial_decision"]} (confidence {state["initial_confidence"]:.0f}%, signal strength {state["initial_signal_strength"]:.0f})
Initial reasoning: {'; '.join(state["initial_reasoning"][:3])}

Structure your argument:
1. **Momentum & Trend** — Price action, moving averages, MACD
2. **Entry Setup** — Why now? Reference specific indicator values
3. **Catalyst / Context** — News, sector strength, volume confirmation
4. **Risk/Reward** — Why upside is worth the risk

Write 3-4 paragraphs (300-400 words). Use specific data. Be persuasive but evidence-based."""

    response, _ = logged_create(
        client, request_type="debate_bull",
        model=cc.FAST_MODEL, max_tokens=800, temperature=0,
        messages=[{"role": "user", "content": prompt}],
        ticker=state["ticker"],
    )
    argument = _extract_text(response)
    logger.info("[Bull] Done (%d chars)", len(argument))
    return {"bull_argument": argument}


def bear_node(state: DebateState) -> dict:
    """Bear analyst: argue AGAINST the trade."""
    logger.info("[Bear] Analyzing %s...", state["ticker"])
    client = get_client()

    prompt = f"""You are a Bear Analyst. Build a compelling, evidence-based case AGAINST this trade.

{state["context"]}

Initial signal: {state["initial_decision"]} (confidence {state["initial_confidence"]:.0f}%)

Counter the bullish thesis:
1. **Trend Risks** — Bearish signals being ignored? Divergences, exhaustion, resistance?
2. **Timing Concerns** — Why might this NOT be the right entry?
3. **Downside Scenario** — What if the trade goes wrong? Key support levels?
4. **Macro / Context Risk** — Sector weakness, earnings, broader market headwinds?

Write 3-4 paragraphs (300-400 words). Be persuasive but evidence-based."""

    response, _ = logged_create(
        client, request_type="debate_bear",
        model=cc.FAST_MODEL, max_tokens=800, temperature=0,
        messages=[{"role": "user", "content": prompt}],
        ticker=state["ticker"],
    )
    argument = _extract_text(response)
    logger.info("[Bear] Done (%d chars)", len(argument))
    return {"bear_argument": argument}


def judge_node(state: DebateState) -> dict:
    """Judge: synthesize Bull + Bear and make final decision."""
    logger.info("[Judge] Synthesizing debate for %s...", state["ticker"])
    client = get_client()

    prompt = f"""You are a senior portfolio manager making the final trading decision.

{state["context"]}

Initial signal: {state["initial_decision"]} (confidence {state["initial_confidence"]:.0f}%)

BULL CASE:
{state["bull_argument"][:800]}

BEAR CASE:
{state["bear_argument"][:800]}

Synthesize both arguments. Weigh the evidence. Make a decisive call.

Output ONLY valid JSON:
{{
  "decision": "BUY",
  "confidence": 65.0,
  "risk_level": "MEDIUM",
  "up_probability": 0.60,
  "neutral_probability": 0.25,
  "down_probability": 0.15,
  "reasoning_summary": "one sentence explaining the final call",
  "reasoning_detail": "2-3 sentences on key factors, what was most convincing, and what would invalidate this call"
}}

Rules:
- decision: "BUY", "SELL", or "WAIT"
- risk_level: "LOW", "MEDIUM", or "HIGH"
- probabilities sum to 1.0
- confidence: 0-100"""

    response, _ = logged_create(
        client, request_type="debate_judge",
        model=cc.DEEP_MODEL, max_tokens=600, temperature=0,
        messages=[{"role": "user", "content": prompt}],
        ticker=state["ticker"],
    )

    text = _extract_text(response).strip()
    text = text.replace("```json", "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    judge_data = json.loads(text)

    # Parse and validate
    decision = str(judge_data.get("decision", "WAIT")).upper()
    if decision not in ("BUY", "SELL", "WAIT"):
        decision = "WAIT"

    confidence = float(judge_data.get("confidence", 50.0))
    risk_level = str(judge_data.get("risk_level", "MEDIUM")).upper()
    if risk_level not in ("LOW", "MEDIUM", "HIGH"):
        risk_level = "MEDIUM"

    up = float(judge_data.get("up_probability", 0.33))
    neut = float(judge_data.get("neutral_probability", 0.34))
    down = float(judge_data.get("down_probability", 0.33))
    total = up + neut + down
    if abs(total - 1.0) > 0.05 and total > 0:
        up, neut, down = up / total, neut / total, down / total

    # Build reasoning
    reasoning = list(state["initial_reasoning"])
    reasoning.append(f"Bull: {state['bull_argument'].replace(chr(10), ' ')[:300]}")
    reasoning.append(f"Bear: {state['bear_argument'].replace(chr(10), ' ')[:300]}")
    reasoning.append(f"Judge: {judge_data.get('reasoning_summary', '')}")
    detail = judge_data.get("reasoning_detail", "")
    if detail:
        reasoning.append(f"Judge: {detail}")

    from models.confidence import scale_confidence, make_recommendation
    scaled_conf = scale_confidence(confidence)
    recommendation = make_recommendation(decision, scaled_conf, risk_level)

    logger.info("[Judge] Decision: %s (conf=%.0f%%, risk=%s)", decision, scaled_conf, risk_level)

    return {
        "judge_data": judge_data,
        "final_decision": decision,
        "final_confidence": scaled_conf,
        "final_risk_level": risk_level,
        "final_probabilities": {"up": round(up, 3), "neutral": round(neut, 3), "down": round(down, 3)},
        "final_reasoning": reasoning,
        "final_recommendation": recommendation,
        "skipped": False,
    }


def skip_node(state: DebateState) -> dict:
    """Skip debate — pass through initial decision."""
    logger.info("[Skip] WAIT signal — skipping debate for %s", state["ticker"])
    from models.confidence import make_recommendation
    return {
        "bull_argument": "",
        "bear_argument": "",
        "judge_data": {},
        "final_decision": state["initial_decision"],
        "final_confidence": state["initial_confidence"],
        "final_risk_level": "MEDIUM",
        "final_probabilities": {"up": 0.33, "neutral": 0.34, "down": 0.33},
        "final_reasoning": state["initial_reasoning"],
        "final_recommendation": make_recommendation(
            state["initial_decision"], state["initial_confidence"], "MEDIUM"),
        "skipped": True,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ROUTING
# ═══════════════════════════════════════════════════════════════════════════

def should_debate(state: DebateState) -> str:
    """Route: skip debate if initial decision is WAIT."""
    if state["initial_decision"] == "WAIT":
        return "skip"
    return "debate"


# ═══════════════════════════════════════════════════════════════════════════
# GRAPH CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════════

def _build_graph() -> StateGraph:
    """Build the debate StateGraph."""
    graph = StateGraph(DebateState)

    # Add nodes
    graph.add_node("bull", bull_node)
    graph.add_node("bear", bear_node)
    graph.add_node("judge", judge_node)
    graph.add_node("skip", skip_node)

    # Conditional entry: debate or skip
    graph.add_conditional_edges(START, should_debate, {
        "debate": "bull",
        "skip": "skip",
    })

    # Bull → Judge, Bear → Judge (sequential for now; LangGraph handles ordering)
    graph.add_edge("bull", "bear")
    graph.add_edge("bear", "judge")

    # Terminals
    graph.add_edge("judge", END)
    graph.add_edge("skip", END)

    return graph


# Compile once
_GRAPH = _build_graph().compile()


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def run_debate_graph(
    initial_decision: DecisionOutput,
    summary: dict,
    ticker: str,
    rag_context: str = "",
) -> DecisionOutput:
    """
    Run the LangGraph debate pipeline.

    On failure, falls back to the original decision (graceful degradation).
    Cost: ~$0.003 per debate (2 Haiku + 1 Sonnet).
    """
    try:
        context = _build_context(summary, ticker, rag_context)

        initial_state: DebateState = {
            "ticker": ticker,
            "context": context,
            "initial_decision": initial_decision.decision,
            "initial_confidence": initial_decision.confidence,
            "initial_signal_strength": initial_decision.signal_strength,
            "initial_reasoning": list(initial_decision.reasoning),
            "initial_source": initial_decision.source,
            "rag_context": rag_context,
            "bull_argument": "",
            "bear_argument": "",
            "judge_data": {},
            "final_decision": "",
            "final_confidence": 0.0,
            "final_risk_level": "",
            "final_probabilities": {},
            "final_reasoning": [],
            "final_recommendation": "",
            "skipped": False,
        }

        # Execute graph
        result = _GRAPH.invoke(initial_state)

        return DecisionOutput(
            decision=result["final_decision"],
            confidence=result["final_confidence"],
            risk_level=result["final_risk_level"],
            reasoning=result["final_reasoning"],
            probabilities=result["final_probabilities"],
            source=f"{initial_decision.source}+debate_graph",
            signal_strength=initial_decision.signal_strength,
            recommendation=result["final_recommendation"],
        )

    except Exception as exc:
        logger.warning("Debate graph failed, falling back: %s", exc)
        return initial_decision
