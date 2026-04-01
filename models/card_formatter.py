"""
models/card_formatter.py
──────────────────────────────────────────────────────────────────
Shared formatting for the decision card across all UI surfaces
(desktop popover, Streamlit web app, voice response).

Converts raw technical reasoning into human-readable coach language
suitable for a product-level decision card.
"""
from __future__ import annotations

import re


def humanize_reasoning(lines: list[str], max_bullets: int = 4) -> list[str]:
    """
    Convert raw technical reasoning lines into short, human-readable
    bullet points suitable for a decision card.

    Filters out step headers, warnings, and edge guard lines.
    Returns at most `max_bullets` lines.
    """
    skip_prefixes = (
        "step ", "trade filter:", "edge guard:", "decision:",
        "caution:", "warning:",
    )

    bullets: list[str] = []
    for line in lines:
        stripped = line.strip()
        low = stripped.lower()

        # Skip empty, step headers, metadata
        if not stripped or any(low.startswith(p) for p in skip_prefixes):
            continue

        # Clean up leading whitespace and bullet markers
        cleaned = stripped.lstrip(" -\u2022\u25b6\u25bc")

        # Skip very short or purely structural lines
        if len(cleaned) < 10:
            continue

        # Convert technical language to coach language
        cleaned = _coach_rewrite(cleaned)
        bullets.append(cleaned)

        if len(bullets) >= max_bullets:
            break

    return bullets if bullets else ["Analysis complete."]


def _coach_rewrite(line: str) -> str:
    """Light rewrites to make indicator language more readable."""
    # Remove score suffixes like "Score: 80/100"
    line = re.sub(r'\s*\|\s*Score:.*$', '', line)
    line = re.sub(r'\s*\|\s*Signal:.*$', '', line)
    line = re.sub(r'\s*\|\s*Confidence:.*$', '', line)

    # Simplify common patterns
    replacements = [
        (r'EMA9 > EMA21 > EMA50', 'all moving averages aligned bullish'),
        (r'EMA9 > EMA21', 'short-term trend is up'),
        (r'EMA9 < EMA21 < EMA50', 'all moving averages aligned bearish'),
        (r'EMA9 < EMA21', 'short-term trend is down'),
        (r'Price \([\d.]+\) > MA20 \([\d.]+\) > MA50 \([\d.]+\)', 'Price above key moving averages'),
        (r'Price \([\d.]+\) < MA20 \([\d.]+\) < MA50 \([\d.]+\)', 'Price below key moving averages'),
        (r'ADX [\d.]+ . trend is strong.*', 'Trend strength is solid'),
        (r'ADX [\d.]+ . weak trend.*', 'Trend is weak and choppy'),
        (r'MACD histogram rising \([\d.]+\).*', 'Momentum is accelerating higher'),
        (r'MACD histogram falling \([\d.-]+\).*', 'Momentum is accelerating lower'),
        (r'MACD histogram positive \([\d.]+\).*', 'Momentum is positive'),
        (r'MACD histogram negative \([\d.-]+\).*', 'Momentum is negative'),
        (r'RSI\d* [\d.]+ . healthy momentum range.*', 'Momentum is in a healthy range'),
        (r'RSI\d* [\d.]+ . overbought.*', 'Momentum is extended — overbought territory'),
        (r'RSI\d* [\d.]+ . oversold.*', 'Potential bounce — oversold territory'),
        (r'RSI [\d.]+ . bullish momentum.*', 'RSI confirms bullish momentum'),
        (r'RSI [\d.]+ . below midline.*', 'RSI shows mild bearish pressure'),
        (r'Volume spike [\d.]+x.*', 'Strong volume participation'),
        (r'Volume ratio [\d.]+x.*normal.*', 'Volume is normal'),
        (r'Low volume [\d.]+x.*', 'Volume is low — weak conviction'),
        (r'Price [\d.]+ above VWAP [\d.]+', 'Price is above VWAP — buyers in control'),
        (r'Price [\d.]+ below VWAP [\d.]+', 'Price is below VWAP — sellers in control'),
        (r'Breakout: Close [\d.]+ at/above.*', 'Breakout above recent highs'),
        (r'Breakdown: Close [\d.]+ at/below.*', 'Breakdown below recent lows'),
        (r'Pullback to EMA9.*in uptrend.*', 'Healthy pullback to support in uptrend'),
        (r'News sentiment bullish.*', 'News sentiment is positive'),
        (r'News sentiment bearish.*', 'News sentiment is negative'),
        (r'News sentiment neutral.*', 'News sentiment is neutral'),
        (r'BB%: [\d.-]+ . near lower band.*', 'Price near lower Bollinger Band'),
        (r'BB%: [\d.-]+ . mid-to-upper.*', 'Price in healthy trend zone'),
        (r'BB%: [\d.-]+ . near upper band.*', 'Price extended near upper band'),
    ]

    for pattern, replacement in replacements:
        line = re.sub(pattern, replacement, line, flags=re.IGNORECASE)

    return line


def signal_label(strength: float) -> str:
    """Primary human label for signal strength (shown large)."""
    if strength >= 80:
        return "Very Strong"
    if strength >= 65:
        return "Strong"
    if strength >= 50:
        return "Moderate"
    if strength >= 35:
        return "Weak"
    return "Very Weak"


def confidence_label(conf: float) -> str:
    """Primary human label for confidence (shown large)."""
    if conf >= 70:
        return "High"
    if conf >= 50:
        return "Moderate"
    if conf >= 30:
        return "Low"
    return "Very Low"


def risk_description(risk: str) -> str:
    """Primary human label for risk (shown large, color-coded)."""
    return {"LOW": "Low", "MEDIUM": "Moderate", "HIGH": "Elevated"}.get(risk, risk)


def decision_subtitle(decision: str) -> str:
    """Short contextual subtitle shown under the decision badge."""
    return {
        "BUY":  "Bullish setup detected",
        "SELL": "Bearish signal detected",
        "WAIT": "No clear setup",
    }.get(decision, "")


def decision_display(decision: str) -> str:
    """Display label for the hero card (institutional style)."""
    return {
        "BUY":  "BULLISH",
        "SELL": "BEARISH",
        "WAIT": "NEUTRAL",
    }.get(decision, decision)
