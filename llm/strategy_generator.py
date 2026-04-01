import json

import llm.claude_client as cc
from llm.claude_client import get_client, _extract_text
from llm.call_logger import logged_create


def generate_strategy_proposal(summary: dict, metrics: dict, ticker: str, rag_context: str = "") -> dict:
    prompt = f"""
You are an AI quant strategy designer.

Ticker: {ticker}

Market Summary:
- Close: {summary.get('close')}
- MA20: {summary.get('ma20')}
- MA50: {summary.get('ma50')}
- RSI: {summary.get('rsi')}

Performance Metrics:
- Net Total Return: {metrics.get('net', {}).get('total_return')}
- Net Annualized Return: {metrics.get('net', {}).get('annualized_return')}
- Net Sharpe: {metrics.get('net', {}).get('sharpe')}
- Net Max Drawdown: {metrics.get('net', {}).get('max_drawdown')}
- Net Win Rate: {metrics.get('net', {}).get('win_rate')}
- Number of Trades: {metrics.get('net', {}).get('num_trades')}

Optional RAG Context:
{rag_context if rag_context else "No extra context."}

Your job:
Design a SAFE structured strategy suggestion for this trading system.

Return ONLY valid JSON in this exact format:
{{
  "strategy_type": "trend_following",
  "use_ma_filter": true,
  "use_rsi_filter": true,
  "rsi_min": 35,
  "rsi_max": 65,
  "stop_loss": 0.03,
  "take_profit": 0.08,
  "max_positions": 2,
  "holding_bias": "medium_term",
  "reasoning": "Explain briefly why this strategy setup is appropriate.",
  "risk_notes": "Explain the main risk."
}}

Rules:
- strategy_type must be one of: trend_following, mean_reversion, breakout, defensive
- use_ma_filter must be true or false
- use_rsi_filter must be true or false
- rsi_min must be between 10 and 60
- rsi_max must be between 30 and 90
- rsi_min must be smaller than rsi_max
- stop_loss must be between 0.01 and 0.10
- take_profit must be between 0.03 and 0.25
- max_positions must be between 1 and 5
- holding_bias must be one of: short_term, swing, medium_term
- no markdown
- no explanation outside JSON
"""

    try:
        client = get_client()
        response, _ = logged_create(
            client, request_type="generate_strategy_proposal",
            model=cc.DEEP_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        text = _extract_text(response).strip()
        text = text.replace("```json", "").replace("```", "").strip()

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]

        data = json.loads(text)

        strategy_type = str(data.get("strategy_type", "trend_following"))
        if strategy_type not in {"trend_following", "mean_reversion", "breakout", "defensive"}:
            strategy_type = "trend_following"

        use_ma_filter = bool(data.get("use_ma_filter", True))
        use_rsi_filter = bool(data.get("use_rsi_filter", True))

        rsi_min = int(data.get("rsi_min", 35))
        rsi_max = int(data.get("rsi_max", 65))
        rsi_min = max(10, min(60, rsi_min))
        rsi_max = max(30, min(90, rsi_max))
        if rsi_min >= rsi_max:
            rsi_min, rsi_max = 35, 65

        stop_loss = float(data.get("stop_loss", 0.03))
        take_profit = float(data.get("take_profit", 0.08))
        stop_loss = max(0.01, min(0.10, stop_loss))
        take_profit = max(0.03, min(0.25, take_profit))

        max_positions = int(data.get("max_positions", 2))
        max_positions = max(1, min(5, max_positions))

        holding_bias = str(data.get("holding_bias", "medium_term"))
        if holding_bias not in {"short_term", "swing", "medium_term"}:
            holding_bias = "medium_term"

        return {
            "strategy_type": strategy_type,
            "use_ma_filter": use_ma_filter,
            "use_rsi_filter": use_rsi_filter,
            "rsi_min": rsi_min,
            "rsi_max": rsi_max,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "max_positions": max_positions,
            "holding_bias": holding_bias,
            "reasoning": str(data.get("reasoning", "AI suggests a balanced strategy configuration.")),
            "risk_notes": str(data.get("risk_notes", "Performance may not generalize across regimes.")),
        }

    except Exception as e:
        return {
            "strategy_type": "trend_following",
            "use_ma_filter": True,
            "use_rsi_filter": True,
            "rsi_min": 35,
            "rsi_max": 65,
            "stop_loss": 0.03,
            "take_profit": 0.08,
            "max_positions": 2,
            "holding_bias": "medium_term",
            "reasoning": f"Fallback strategy used because AI generation failed: {e}",
            "risk_notes": "Fallback proposal may be generic."
        }