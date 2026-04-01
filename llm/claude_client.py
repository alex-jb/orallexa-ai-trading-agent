import json
from anthropic import Anthropic

# ── Dual-tier model routing ───────────────────────────────────────────────
# FAST_MODEL: cheap & fast — structured JSON, quick summaries, parameter gen
# DEEP_MODEL: quality reasoning — strategy reflection, deep analysis, decisions
FAST_MODEL = "claude-haiku-4-5-20251001"
DEEP_MODEL = "claude-sonnet-4-6"


def get_client():
    return Anthropic()


def _extract_text(response) -> str:
    result = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            result += block.text
    return result.strip()


def real_llm_analysis(summary: dict) -> str:
    prompt = f"""
You are a trading analyst.

Given:
- Close price: {summary.get('close')}
- MA20: {summary.get('ma20')}
- MA50: {summary.get('ma50')}
- RSI: {summary.get('rsi')}

Analyze:
1. Trend
2. Bullish or bearish bias
3. Risks
4. Action (watch / enter / avoid)

Be concise and practical.
"""

    try:
        from llm.call_logger import logged_create
        client = get_client()
        response, _ = logged_create(
            client, request_type="real_llm_analysis",
            model=FAST_MODEL, max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_text(response)
    except Exception as e:
        return f"LLM failed: {str(e)}"


def reflect_on_strategy(summary: dict, metrics: dict) -> str:
    prompt = f"""
You are an AI trading strategy reviewer.

Here is the latest market summary:
- Close price: {summary.get('close')}
- MA20: {summary.get('ma20')}
- MA50: {summary.get('ma50')}
- RSI: {summary.get('rsi')}

Here is the backtest result:
- Total return: {metrics.get('total_return')}
- Annualized return: {metrics.get('annualized_return')}
- Sharpe ratio: {metrics.get('sharpe')}
- Max drawdown: {metrics.get('max_drawdown')}
- Win rate: {metrics.get('win_rate')}
- Number of trades: {metrics.get('num_trades')}

Please answer:
1. What weaknesses do you see in the current strategy?
2. Is the strategy too aggressive, too weak, or too noisy?
3. What specific improvements would you suggest to the entry/exit logic?
4. Should we adjust MA, RSI, stop loss, or take profit rules?

Be specific and actionable.
"""

    try:
        from llm.call_logger import logged_create
        client = get_client()
        response, _ = logged_create(
            client, request_type="reflect_on_strategy",
            model=DEEP_MODEL, max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_text(response)
    except Exception as e:
        return f"Reflection failed: {str(e)}"


def generate_new_parameters(summary: dict, metrics: dict) -> dict:
    prompt = f"""
You are an AI trading strategist.

Based on:

Market:
- Close: {summary.get('close')}
- MA20: {summary.get('ma20')}
- MA50: {summary.get('ma50')}
- RSI: {summary.get('rsi')}

Performance:
- Sharpe: {metrics.get('sharpe')}
- Return: {metrics.get('total_return')}
- Drawdown: {metrics.get('max_drawdown')}
- Win rate: {metrics.get('win_rate')}
- Number of trades: {metrics.get('num_trades')}

IMPORTANT CONSTRAINTS:
- Strategy must generate trades
- Do NOT make RSI range too narrow
- Keep stop_loss between 0.02 and 0.08
- Keep take_profit between 0.05 and 0.20
- Ensure rsi_min < rsi_max

Output ONLY valid JSON:
{{
  "rsi_min": 40,
  "rsi_max": 65,
  "stop_loss": 0.04,
  "take_profit": 0.12
}}
"""

    try:
        from llm.call_logger import logged_create
        client = get_client()
        response, _ = logged_create(
            client, request_type="generate_new_parameters",
            model=FAST_MODEL, max_tokens=250,
            messages=[{"role": "user", "content": prompt}],
        )

        text = _extract_text(response).strip()
        text = text.replace("```json", "").replace("```", "").strip()

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]

        params = json.loads(text)

        return {
            "rsi_min": int(params["rsi_min"]),
            "rsi_max": int(params["rsi_max"]),
            "stop_loss": float(params["stop_loss"]),
            "take_profit": float(params["take_profit"]),
        }

    except Exception:
        return {
            "rsi_min": 35,
            "rsi_max": 60,
            "stop_loss": 0.04,
            "take_profit": 0.10
        }
