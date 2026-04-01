"""
models/confidence.py
──────────────────────────────────────────────────────────────────
Shared utilities for confidence scaling, risk derivation,
recommendation generation, and edge-case decision guards.

Rules:
  - Confidence is ALWAYS capped at MAX_CONFIDENCE (82%).
    No model should express more than 82% certainty.
  - signal_strength is the raw 0-100 composite indicator score.
    It reflects how clear the technical picture is, independently
    of how certain we are about the outcome.
  - risk is derived from signal_strength + market conditions,
    NOT from confidence.
  - recommendation is always a plain-English action sentence.
  - BUY/SELL with confidence > 75% ALWAYS includes confirmation
    language — the system never presents a decision as certain.
  - Stale data, very low signal, or conflicting indicators
    force WAIT with a clear explanation.
"""
from __future__ import annotations

MAX_CONFIDENCE = 82.0   # no single analysis can exceed this

# Threshold above which we add confirmation language
HIGH_CONFIDENCE_THRESHOLD = 75.0

# Below this signal_strength, BUY/SELL is unreliable → force WAIT
WEAK_SIGNAL_THRESHOLD = 25.0


def scale_confidence(raw: float) -> float:
    """
    Rescale a 0-100 confidence value to the 0-MAX_CONFIDENCE range.

    Examples
    --------
    scale_confidence(100)  -> 82.0
    scale_confidence(75)   -> 61.5
    scale_confidence(50)   -> 41.0
    scale_confidence(0)    -> 0.0
    """
    return round(min(float(raw) * (MAX_CONFIDENCE / 100.0), MAX_CONFIDENCE), 1)


def score_to_risk(signal_strength: float, stale: bool = False) -> str:
    """
    Derive risk level from signal clarity, independent of confidence.

    Returns 'LOW' | 'MEDIUM' | 'HIGH'
    """
    if stale or signal_strength < 40:
        return "HIGH"
    if signal_strength >= 68:
        return "LOW"
    return "MEDIUM"


def make_recommendation(
    decision: str,
    confidence: float,
    risk: str,
    stale: bool = False,
) -> str:
    """
    Return a plain-English action sentence for the decision card.

    High-confidence BUY/SELL (>75%) always includes confirmation
    language so the system never presents a decision as certain.
    """
    if stale:
        return "Market closed. Verify at next open."

    if decision == "WAIT":
        if confidence < 15:
            return "No setup. Stand aside."
        return "Mixed signals. Wait for clarity."

    if confidence > HIGH_CONFIDENCE_THRESHOLD:
        if decision == "BUY":
            return "Strong signal. Confirm on next candle before entry."
        if decision == "SELL":
            return "Strong sell. Confirm on next candle before acting."

    if decision == "BUY":
        if risk == "HIGH":
            return "Weak setup. Only with very tight stop."
        if confidence < 45:
            return "Early signal. Reduce size until confirmed."
        if confidence < 65:
            return "Moderate setup. Half position, stop below support."
        return "Good setup. Enter with stop below support."

    if decision == "SELL":
        if risk == "HIGH":
            return "Weak breakdown. Only with tight stop."
        if confidence < 45:
            return "Early sell signal. Reduce exposure."
        if confidence < 65:
            return "Moderate sell. Stop above resistance."
        return "Good sell setup. Stop above resistance."

    return "Analysis complete."


# ── Edge-case guard ──────────────────────────────────────────────────────────

def _has_conflicting_signals(reasoning: list) -> bool:
    """
    Detect if the reasoning list contains opposing bullish + bearish
    signals, indicating an unclear picture.
    """
    bullish_kw = [
        "uptrend", "bullish", "breakout", "buyers in control",
        "histogram rising", "histogram positive", "above vwap",
        "healthy momentum", "volume spike",
    ]
    bearish_kw = [
        "downtrend", "bearish", "breakdown", "sellers in control",
        "histogram falling", "histogram negative", "below vwap",
        "overbought", "oversold", "low volume", "weak participation",
        "mean reversion risk",
    ]

    text = " ".join(str(r).lower() for r in reasoning)
    bull_count = sum(1 for kw in bullish_kw if kw in text)
    bear_count = sum(1 for kw in bearish_kw if kw in text)

    # Conflicting = at least 2 signals on EACH side
    return bull_count >= 2 and bear_count >= 2


def guard_decision(result) -> "DecisionOutput":
    """
    Post-processing edge guard applied after every analysis.

    Rules (in order of priority):
      1. Stale data + BUY/SELL -> override to WAIT
      2. Very weak signal (<25) + BUY/SELL -> override to WAIT
      3. Conflicting signals in reasoning -> override to WAIT
      4. High confidence (>75%) -> add caution (already in make_recommendation,
         but also flag in reasoning)

    Returns a new DecisionOutput (never mutates the input).
    """
    from models.decision import DecisionOutput

    # Only guard BUY/SELL — WAIT is already safe
    if result.decision == "WAIT":
        return result

    reasoning = list(result.reasoning)   # copy so we don't mutate
    override_wait = False
    override_reason = ""

    # ── Rule 1: Stale data ────────────────────────────────────────
    stale_markers = [
        "data may be delayed", "market may be closed",
        "market closed", "min old",
    ]
    is_stale = any(
        any(m in str(r).lower() for m in stale_markers)
        for r in reasoning
    )
    if is_stale:
        override_wait = True
        override_reason = "Stale data. Verify at next open."

    # ── Rule 2: Very weak signal ──────────────────────────────────
    if not override_wait and result.signal_strength < WEAK_SIGNAL_THRESHOLD:
        override_wait = True
        override_reason = f"Signal too weak ({result.signal_strength:.0f}/100). Stand aside."

    # ── Rule 3: Conflicting signals ───────────────────────────────
    if not override_wait and _has_conflicting_signals(reasoning):
        override_wait = True
        override_reason = "Conflicting signals. Wait for clarity."

    # ── Apply override ────────────────────────────────────────────
    if override_wait:
        reasoning.append(f"Edge guard: {override_reason}")
        return DecisionOutput(
            decision="WAIT",
            confidence=result.confidence,
            risk_level="HIGH",
            reasoning=reasoning,
            probabilities={"up": 0.34, "down": 0.33, "neutral": 0.33},
            source=result.source,
            signal_strength=result.signal_strength,
            recommendation=override_reason,
        )

    # ── Rule 4: High confidence caution ───────────────────────────
    if result.confidence > HIGH_CONFIDENCE_THRESHOLD:
        if not any("no signal is certain" in str(r).lower() for r in reasoning):
            reasoning.append(
                f"Caution: confidence is high ({result.confidence:.0f}%) "
                f"— wait for next candle to confirm before committing"
            )
        rec = result.recommendation
        if "no signal is certain" not in rec:
            rec = make_recommendation(
                result.decision, result.confidence, result.risk_level
            )
        return DecisionOutput(
            decision=result.decision,
            confidence=result.confidence,
            risk_level=result.risk_level,
            reasoning=reasoning,
            probabilities=result.probabilities,
            source=result.source,
            signal_strength=result.signal_strength,
            recommendation=rec,
        )

    return result
