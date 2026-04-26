"""
llm/debate.py
──────────────────────────────────────────────────────────────────
Lightweight Bull/Bear adversarial debate for trading decisions.

Instead of the heavy TradingAgents multi-agent pipeline, this runs
a 3-call debate using direct Claude API calls:
  1. Bull analyst argues FOR the trade  (FAST_MODEL)
  2. Bear analyst argues AGAINST         (FAST_MODEL)
  3. Judge synthesizes both sides         (DEEP_MODEL)

Usage:
    from llm.debate import run_lightweight_debate
    result = run_lightweight_debate(initial_decision, summary, "NVDA")
"""
from __future__ import annotations

import json
from models.decision import DecisionOutput
import llm.claude_client as cc
from llm.claude_client import get_client, _extract_text
from llm.call_logger import logged_create


def _build_context(summary: dict, ticker: str, rag_context: str) -> str:
    """Format market data into a compact context block."""
    lines = [
        f"Ticker: {ticker}",
        f"Close: {summary.get('close')}  MA20: {summary.get('ma20')}  MA50: {summary.get('ma50')}",
        f"RSI: {summary.get('rsi')}  MACD Hist: {summary.get('macd_hist')}",
        f"BB%: {summary.get('bb_pct')}  ADX: {summary.get('adx')}  Vol Ratio: {summary.get('volume_ratio')}",
    ]
    if rag_context:
        lines.append(f"\nContext:\n{rag_context[:500]}")
    return "\n".join(lines)


def _call_bull(
    client,
    initial: DecisionOutput,
    context: str,
) -> str:
    """Bull analyst: argue FOR the initial decision direction."""
    direction = "entering a long position" if initial.decision == "BUY" else \
                "entering a short position" if initial.decision == "SELL" else \
                "taking a position"
    prompt = f"""You are a Bull Analyst. Build a compelling, evidence-based case FOR {direction} on this stock.

{context}

Initial signal: {initial.decision} (confidence {initial.confidence:.0f}%, signal strength {initial.signal_strength:.0f})
Initial reasoning: {'; '.join(initial.reasoning[:3])}

Structure your argument with numbered points:

1. **Momentum & Trend** — What does price action, moving averages, and MACD tell us?
2. **Entry Setup** — Why is now a good time? Reference specific indicator values.
3. **Catalyst / Context** — Any news, sector strength, or volume confirmation?
4. **Risk/Reward** — Why is the upside worth the risk? Quantify if possible.

Write 3-4 detailed paragraphs (300-400 words). Use specific data from the indicators above. Be persuasive but grounded in evidence."""

    response, _ = logged_create(
        client, request_type="_call_bull",
        model=cc.FAST_MODEL, max_tokens=800, temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_text(response)


def _call_bear(
    client,
    initial: DecisionOutput,
    context: str,
    bull_argument: str,
) -> str:
    """Bear analyst: argue AGAINST, countering the bull's case."""
    prompt = f"""You are a Bear Analyst. Build a compelling, evidence-based case AGAINST this trade.

{context}

Initial signal: {initial.decision} (confidence {initial.confidence:.0f}%)

The Bull Analyst argues:
{bull_argument[:800]}

Directly counter the bull's argument with numbered points:

1. **Trend Risks** — What bearish signals is the bull ignoring? Divergences, exhaustion, overhead resistance?
2. **Timing Concerns** — Why might this NOT be the right entry? Overbought conditions, low volume?
3. **Downside Scenario** — What happens if the trade goes wrong? Key support levels to watch.
4. **Macro / Context Risk** — Sector weakness, earnings risk, broader market headwinds?

Write 3-4 detailed paragraphs (300-400 words). Counter specific claims from the bull. Be persuasive but grounded in evidence."""

    response, _ = logged_create(
        client, request_type="_call_bear",
        model=cc.FAST_MODEL, max_tokens=800, temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_text(response)


def _call_judge(
    client,
    initial: DecisionOutput,
    context: str,
    bull_argument: str,
    bear_argument: str,
    bias_context: str = "",
) -> dict:
    """Judge: synthesize both sides and output a final decision as JSON."""
    bias_block = f"\n{bias_context}\n" if bias_context else ""
    prompt = f"""You are a senior portfolio manager making the final trading decision.

{context}{bias_block}

Initial signal: {initial.decision} (confidence {initial.confidence:.0f}%)

BULL CASE:
{bull_argument[:800]}

BEAR CASE:
{bear_argument[:800]}

Synthesize both arguments. Weigh the evidence. Make a decisive call.

Output ONLY valid JSON (no markdown):
{{
  "decision": "BUY",
  "confidence": 65.0,
  "risk_level": "MEDIUM",
  "up_probability": 0.60,
  "neutral_probability": 0.25,
  "down_probability": 0.15,
  "reasoning_summary": "one sentence explaining the final call",
  "reasoning_detail": "2-3 sentences expanding on the key factors that tipped the decision, what you found most convincing from each side, and the specific condition that would invalidate this call"
}}

Rules:
- decision: "BUY", "SELL", or "WAIT"
- risk_level: "LOW", "MEDIUM", or "HIGH"
- probabilities sum to 1.0
- confidence: 0-100
- reasoning_detail: 2-3 sentences, be specific"""

    # Judge is the most expensive reasoning hop in the deep-analysis path —
    # route to Opus 4.7 + xhigh effort. Other debate roles (Bull/Bear) stay
    # on sonnet to keep cost manageable.
    response, _ = logged_create(
        client, request_type="_call_judge",
        model=cc.OPUS_MODEL, max_tokens=600, temperature=0,
        effort=cc.DEEP_EFFORT,
        messages=[{"role": "user", "content": prompt}],
    )
    text = _extract_text(response).strip()
    text = text.replace("```json", "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def run_lightweight_debate(
    initial_decision: DecisionOutput,
    summary: dict,
    ticker: str,
    rag_context: str = "",
) -> DecisionOutput:
    """
    Run a 3-call adversarial debate and return an improved DecisionOutput.

    On any failure, returns the original decision unchanged (graceful degradation).

    Cost: ~$0.003 per debate (2 Haiku + 1 Sonnet call).
    """
    try:
        client = get_client()
        context = _build_context(summary, ticker, rag_context)

        # Load bias awareness for self-correction
        bias_context = ""
        try:
            from engine.bias_tracker import get_bias_context
            bias_context = get_bias_context(ticker)
        except Exception:
            pass  # non-critical

        # Stage 1: Bull argues FOR
        bull_argument = _call_bull(client, initial_decision, context)

        # Stage 2: Bear argues AGAINST
        bear_argument = _call_bear(client, initial_decision, context, bull_argument)

        # Stage 3: Judge synthesizes (with bias awareness)
        judge_data = _call_judge(client, initial_decision, context, bull_argument, bear_argument, bias_context)

        # Parse judge output
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

        # Build enriched reasoning from debate
        reasoning = list(initial_decision.reasoning)
        reasoning.append(f"Bull: {bull_argument.replace(chr(10), ' ')}")
        reasoning.append(f"Bear: {bear_argument.replace(chr(10), ' ')}")
        judge_summary = judge_data.get('reasoning_summary', '')
        judge_detail = judge_data.get('reasoning_detail', '')
        reasoning.append(f"Judge: {judge_summary}")
        if judge_detail:
            reasoning.append(f"Judge: {judge_detail}")

        from models.confidence import scale_confidence, score_to_risk, make_recommendation

        scaled_conf = scale_confidence(confidence)
        recommendation = make_recommendation(decision, scaled_conf, risk_level)

        out = DecisionOutput(
            decision=decision,
            confidence=scaled_conf,
            risk_level=risk_level,
            reasoning=reasoning,
            probabilities={"up": round(up, 3), "neutral": round(neut, 3), "down": round(down, 3)},
            source=f"{initial_decision.source}+debate",
            signal_strength=initial_decision.signal_strength,
            recommendation=recommendation,
        )
        # Stash full Bull/Bear/Judge text on .extra so decision_log captures it.
        # Used by scripts/build_dspy_eval_set.py to assemble the Phase B
        # eval set without rerunning the debate pipeline.
        out.extra["debate"] = {
            "bull_argument":     bull_argument[:2000],
            "bear_argument":     bear_argument[:2000],
            "judge_summary":     judge_summary,
            "judge_detail":      judge_detail,
            "judge_decision":    decision,
            "judge_confidence":  int(confidence),
            "judge_risk_level":  risk_level,
        }
        return out

    except Exception:
        # Graceful degradation: return original decision unchanged
        return initial_decision
