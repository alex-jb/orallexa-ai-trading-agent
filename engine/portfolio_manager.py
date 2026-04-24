"""
engine/portfolio_manager.py
──────────────────────────────────────────────────────────────────
Portfolio Manager gate — the final layer before a decision executes.

Inspired by TauricResearch/TradingAgents (Apache-2.0), where a
Portfolio Manager weighs position sizing, concentration, and
correlation across the book before approving/rejecting a trade.

Rules (all overridable):
  - MIN_CONFIDENCE          reject if decision confidence < N
  - MAX_SINGLE_POSITION_PCT  reject/scale if position would exceed this %
  - MAX_SECTOR_CONCENTRATION warn if sector exposure > this %
  - MAX_SAME_DIRECTION_STREAK warn if recent decisions all same direction
  - BASE_POSITION_PCT        default position size per trade

The module is pure: caller passes current portfolio + recent-decision
history, manager returns approve/reject + scaled sizing.

Usage:
    from engine.portfolio_manager import approve_decision, Position
    result = approve_decision(
        ticker="NVDA",
        decision={"decision": "BUY", "confidence": 75, "signal_strength": 60},
        portfolio=[Position("NVDA", 2_500), Position("AAPL", 1_000)],
        portfolio_value=10_000,
    )
    print(result["approved"], result["scaled_position_pct"], result["reason"])
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


DEFAULT_RULES = {
    "min_confidence":             40,
    "max_single_position_pct":    20.0,
    "max_sector_concentration":   40.0,
    "max_same_direction_streak":  5,
    "base_position_pct":          5.0,
    "max_position_pct":           15.0,
}


@dataclass(frozen=True)
class Position:
    ticker: str
    value_usd: float
    sector: Optional[str] = None
    entry_date: Optional[str] = None


@dataclass
class ApprovalResult:
    approved: bool
    scaled_position_pct: float
    reason: str
    warnings: list[str] = field(default_factory=list)
    original_confidence: int = 0
    adjusted_confidence: int = 0
    checks: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "scaled_position_pct": round(self.scaled_position_pct, 2),
            "reason": self.reason,
            "warnings": list(self.warnings),
            "original_confidence": self.original_confidence,
            "adjusted_confidence": self.adjusted_confidence,
            "checks": dict(self.checks),
        }


def approve_decision(
    *,
    ticker: str,
    decision: dict,
    portfolio: Optional[list[Position]] = None,
    portfolio_value: float = 10_000.0,
    recent_decisions: Optional[list[dict]] = None,
    rules: Optional[dict] = None,
) -> dict:
    """
    Apply portfolio-level gates on a single ticker decision.

    Parameters
    ----------
    ticker           : target symbol
    decision         : dict with at least {decision, confidence}. Optional:
                       signal_strength, risk_level, sector.
    portfolio        : list of Position objects (current holdings). Empty list
                       means an empty book.
    portfolio_value  : total NAV in USD. Used for concentration math.
    recent_decisions : last N decisions (for streak detection). Each dict
                       should have a "decision" or "direction" key.
    rules            : optional overrides; merged on top of DEFAULT_RULES.

    Returns
    -------
    dict — serialized ApprovalResult
    """
    r = dict(DEFAULT_RULES)
    if rules:
        r.update(rules)

    direction = _normalize_direction(decision)
    confidence = int(decision.get("confidence", 0) or 0)
    signal_strength = int(decision.get("signal_strength", 0) or 0)
    sector = decision.get("sector")

    portfolio = portfolio or []
    recent_decisions = recent_decisions or []

    checks: dict = {}
    warnings: list[str] = []

    # 1. Confidence gate
    if confidence < r["min_confidence"]:
        return ApprovalResult(
            approved=False,
            scaled_position_pct=0.0,
            reason=f"Confidence {confidence} below minimum {r['min_confidence']}",
            warnings=warnings,
            original_confidence=confidence,
            adjusted_confidence=confidence,
            checks={"confidence": False},
        ).to_dict()
    checks["confidence"] = True

    # HOLD / WAIT decisions bypass sizing logic
    if direction == "HOLD":
        return ApprovalResult(
            approved=True,
            scaled_position_pct=0.0,
            reason="HOLD — no position change",
            warnings=warnings,
            original_confidence=confidence,
            adjusted_confidence=confidence,
            checks=checks,
        ).to_dict()

    # 2. Concentration check (only for BUY — SELL trims concentration)
    existing_value = sum(p.value_usd for p in portfolio if p.ticker.upper() == ticker.upper())
    existing_pct = (existing_value / portfolio_value * 100.0) if portfolio_value > 0 else 0.0
    checks["existing_position_pct"] = round(existing_pct, 2)
    if direction == "BUY" and existing_pct >= r["max_single_position_pct"]:
        return ApprovalResult(
            approved=False,
            scaled_position_pct=0.0,
            reason=(
                f"Position in {ticker} already {existing_pct:.1f}% of portfolio "
                f"(max {r['max_single_position_pct']}%)"
            ),
            warnings=warnings,
            original_confidence=confidence,
            adjusted_confidence=confidence,
            checks=checks,
        ).to_dict()

    # 3. Sector concentration (warn only)
    if sector:
        sector_value = sum(
            p.value_usd for p in portfolio
            if p.sector and p.sector.lower() == sector.lower()
        )
        sector_pct = (sector_value / portfolio_value * 100.0) if portfolio_value > 0 else 0.0
        checks["sector_pct"] = round(sector_pct, 2)
        if direction == "BUY" and sector_pct >= r["max_sector_concentration"]:
            warnings.append(
                f"Sector {sector} already {sector_pct:.1f}% — crowded exposure"
            )

    # 4. Direction streak check (warn only)
    streak = _same_direction_streak(recent_decisions)
    checks["same_direction_streak"] = streak
    if streak >= r["max_same_direction_streak"]:
        warnings.append(
            f"Last {streak} decisions all same direction — possible directional bias"
        )

    # 5. Position sizing: base × confidence factor × signal_strength factor
    conf_factor = max(0.0, min(1.5, (confidence - r["min_confidence"]) / 30.0 + 0.5))
    strength_factor = max(0.0, min(1.2, signal_strength / 100.0 + 0.4))
    raw_pct = r["base_position_pct"] * conf_factor * strength_factor

    # Scale down if existing position already has some exposure
    headroom_pct = max(0.0, r["max_single_position_pct"] - existing_pct)
    scaled_pct = min(raw_pct, headroom_pct, r["max_position_pct"])
    # If warnings, trim by 25%
    if warnings:
        scaled_pct *= 0.75

    scaled_pct = round(max(0.0, scaled_pct), 2)

    # Adjusted confidence reflects the scaling pressure
    scaling_ratio = scaled_pct / raw_pct if raw_pct > 0 else 0
    adjusted_conf = int(confidence * min(1.0, scaling_ratio * 1.05))

    reason = (
        f"Approved {direction} {ticker} at {scaled_pct:.1f}% "
        f"(conf {confidence}, strength {signal_strength}"
        f"{f', {len(warnings)} warning(s)' if warnings else ''})"
    )

    return ApprovalResult(
        approved=True,
        scaled_position_pct=scaled_pct,
        reason=reason,
        warnings=warnings,
        original_confidence=confidence,
        adjusted_confidence=adjusted_conf,
        checks=checks,
    ).to_dict()


def _normalize_direction(decision: dict) -> str:
    """Extract a canonical direction from a heterogeneous decision dict."""
    raw = (
        decision.get("decision")
        or decision.get("direction")
        or decision.get("action")
        or ""
    )
    s = str(raw).upper()
    if s in ("BUY", "LONG", "BULLISH"):
        return "BUY"
    if s in ("SELL", "SHORT", "BEARISH"):
        return "SELL"
    if s in ("HOLD", "WAIT", "NEUTRAL", "PASS"):
        return "HOLD"
    return s or "HOLD"


def _same_direction_streak(recent: list[dict]) -> int:
    """Count consecutive same-direction decisions (most-recent first)."""
    if not recent:
        return 0
    first = _normalize_direction(recent[0])
    if first == "HOLD":
        return 0
    count = 1
    for d in recent[1:]:
        if _normalize_direction(d) == first:
            count += 1
        else:
            break
    return count
