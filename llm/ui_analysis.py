import json

import llm.claude_client as cc
from llm.claude_client import get_client, _extract_text
from llm.call_logger import logged_create

_DEFAULT_PREDICTION = {
    "decision": "WAIT",
    "confidence": 40.0,
    "risk_level": "MEDIUM",
    "up_probability": 0.38,
    "neutral_probability": 0.28,
    "down_probability": 0.34,
    "reasoning_summary": "Insufficient data for a confident call.",
}


def ui_analysis_with_rag(summary: dict, metrics: dict, rag_context: str, ticker: str) -> str:
    prompt = f"""
You are an AI trading research assistant.

Ticker: {ticker}

Market Summary:
- Close: {summary.get('close')}
- MA20: {summary.get('ma20')}
- MA50: {summary.get('ma50')}
- RSI: {summary.get('rsi')}

Backtest Metrics:
- Total Return: {metrics.get('total_return')}
- Annualized Return: {metrics.get('annualized_return')}
- Sharpe: {metrics.get('sharpe')}
- Max Drawdown: {metrics.get('max_drawdown')}
- Win Rate: {metrics.get('win_rate')}
- Number of Trades: {metrics.get('num_trades')}

Retrieved RAG Context:
{rag_context if rag_context else "No additional context available."}

Please provide:
1. Current market bias
2. Key technical interpretation
3. How the retrieved context affects the outlook
4. Main risks
5. Practical action: Watch / Long Bias / Avoid / Wait for Confirmation

Be concise but useful.
"""

    try:
        client = get_client()
        response, _ = logged_create(
            client, request_type="ui_analysis_with_rag",
            model=cc.DEEP_MODEL, max_tokens=600,
            messages=[{"role": "user", "content": prompt}], ticker=ticker,
        )
        return _extract_text(response)
    except Exception as e:
        return f"AI report failed: {e}"


def ui_probability_report(summary: dict, metrics: dict, rag_context: str, ticker: str) -> dict:
    prompt = f"""
You are an AI trading strategist.

Ticker: {ticker}

Market Summary:
- Close: {summary.get('close')}
- MA20: {summary.get('ma20')}
- MA50: {summary.get('ma50')}
- RSI: {summary.get('rsi')}

Backtest Metrics:
- Total Return: {metrics.get('total_return')}
- Annualized Return: {metrics.get('annualized_return')}
- Sharpe: {metrics.get('sharpe')}
- Max Drawdown: {metrics.get('max_drawdown')}
- Win Rate: {metrics.get('win_rate')}
- Number of Trades: {metrics.get('num_trades')}

Retrieved RAG Context:
{rag_context if rag_context else "No additional context available."}

Return ONLY valid JSON in this format:
{{
  "bull_probability": 55,
  "neutral_probability": 25,
  "bear_probability": 20,
  "confidence": "medium",
  "action": "Wait for Confirmation",
  "bias": "Mild Bullish",
  "key_driver": "Price structure is improving while risk remains event-sensitive.",
  "main_risk": "Momentum can fail if the price loses MA20 again."
}}
"""

    try:
        client = get_client()
        response, _ = logged_create(
            client, request_type="ui_probability_report",
            model=cc.FAST_MODEL, max_tokens=300,
            messages=[{"role": "user", "content": prompt}], ticker=ticker,
        )

        text = _extract_text(response).strip()
        text = text.replace("```json", "").replace("```", "").strip()

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]

        data = json.loads(text)

        bull = int(data.get("bull_probability", 40))
        neutral = int(data.get("neutral_probability", 30))
        bear = int(data.get("bear_probability", 30))

        total = bull + neutral + bear
        if total != 100 and total > 0:
            bull = round(bull / total * 100)
            neutral = round(neutral / total * 100)
            bear = 100 - bull - neutral

        return {
            "bull_probability": bull,
            "neutral_probability": neutral,
            "bear_probability": bear,
            "confidence": str(data.get("confidence", "medium")).lower(),
            "action": str(data.get("action", "Watch")),
            "bias": str(data.get("bias", "Neutral")),
            "key_driver": str(data.get("key_driver", "Mixed signals.")),
            "main_risk": str(data.get("main_risk", "Unclear risk environment.")),
        }

    except Exception:
        return {
            "bull_probability": 45,
            "neutral_probability": 30,
            "bear_probability": 25,
            "confidence": "medium",
            "action": "Watch",
            "bias": "Neutral",
            "key_driver": "Technical structure is mixed.",
            "main_risk": "Signal quality may not generalize out of sample.",
        }


def prediction_decision_report(
    summary: dict,
    tech_score: float,
    ticker: str,
    rag_context: str = "",
) -> dict:
    """
    Claude overlay for PredictionSkill.
    Returns a dict matching DecisionOutput fields:
      decision, confidence, risk_level, up/neutral/down_probability, reasoning_summary.
    """
    prompt = f"""You are a trading analyst making a short-term directional call.

Ticker: {ticker}
Technical Score: {tech_score:.0f}/100 (>65 bullish, <35 bearish, 35-65 neutral)

Market Indicators:
- Close: {summary.get('close')}
- MA20: {summary.get('ma20')}, MA50: {summary.get('ma50')}
- RSI: {summary.get('rsi')}
- MACD Histogram: {summary.get('macd_hist')}
- BB%: {summary.get('bb_pct')}
- ADX: {summary.get('adx')}
- Volume Ratio: {summary.get('volume_ratio')}

{f"News/Context:{chr(10)}{rag_context}" if rag_context else "No additional context."}

Output ONLY valid JSON (no markdown):
{{
  "decision": "BUY",
  "confidence": 65.0,
  "risk_level": "MEDIUM",
  "up_probability": 0.60,
  "neutral_probability": 0.25,
  "down_probability": 0.15,
  "reasoning_summary": "one sentence explaining the call"
}}

Rules:
- decision must be "BUY", "SELL", or "WAIT"
- risk_level must be "LOW", "MEDIUM", or "HIGH"
- probabilities must sum to 1.0
- confidence is 0-100
"""

    try:
        client = get_client()
        response, _ = logged_create(
            client, request_type="prediction_decision_report",
            model=cc.DEEP_MODEL, max_tokens=300,
            messages=[{"role": "user", "content": prompt}], ticker=ticker,
        )
        text = _extract_text(response).strip()
        text = text.replace("```json", "").replace("```", "").strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        data = json.loads(text)

        # Normalise probabilities to sum to 1.0
        up   = float(data.get("up_probability", 0.38))
        neut = float(data.get("neutral_probability", 0.28))
        down = float(data.get("down_probability", 0.34))
        total = up + neut + down
        if abs(total - 1.0) > 0.05 and total > 0:
            up, neut, down = up / total, neut / total, down / total

        return {
            "decision":            str(data.get("decision", "WAIT")).upper(),
            "confidence":          float(data.get("confidence", 40.0)),
            "risk_level":          str(data.get("risk_level", "MEDIUM")).upper(),
            "up_probability":      round(up, 3),
            "neutral_probability": round(neut, 3),
            "down_probability":    round(down, 3),
            "reasoning_summary":   str(data.get("reasoning_summary", "")),
        }

    except Exception:
        return dict(_DEFAULT_PREDICTION)