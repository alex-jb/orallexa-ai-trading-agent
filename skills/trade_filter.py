"""
skills/trade_filter.py
──────────────────────────────────────────────────────────────────────────────
Mode-aware trade quality filter.

Evaluates a DecisionOutput + market context and decides whether the trade
meets minimum quality standards for the selected mode.

Modes:
  scalp    — volume + RSI + ATR range + primary setup required
  intraday — MACD direction + VWAP side + ADX strength
  swing    — MA alignment + ADX + no extended RSI

Output: FilterResult (passed, reason, warnings, quality_score)
"""

from dataclasses import dataclass, field
from models.decision import DecisionOutput


@dataclass
class FilterResult:
    passed: bool
    reason: str              # primary pass/fail message
    warnings: list = field(default_factory=list)   # non-blocking flags
    quality_score: float = 0.0                      # 0-100

    def to_dict(self) -> dict:
        return {
            "passed":        self.passed,
            "reason":        self.reason,
            "warnings":      self.warnings,
            "quality_score": round(self.quality_score, 1),
        }


class TradeFilterSkill:
    """
    Mode-aware quality gate applied AFTER a DecisionOutput is generated.

    Usage:
        result = TradeFilterSkill().evaluate(
            decision=decision_out,
            mode="scalp",
            context={"rsi": 74, "vol_ratio": 1.2, "atr_pct": 0.4, ...},
            trades_today=3,
        )
        if not result.passed:
            st.warning(result.reason)
    """

    # Hard caps regardless of mode
    MAX_TRADES_PER_DAY = 10
    MIN_CONFIDENCE_BY_MODE = {"scalp": 35, "intraday": 30, "swing": 25}

    def evaluate(
        self,
        decision: DecisionOutput,
        mode: str,
        context: dict,
        trades_today: int = 0,
    ) -> FilterResult:
        """
        Args:
            decision:     DecisionOutput from brain.run_for_mode()
            mode:         "scalp" | "intraday" | "swing"
            context:      dict with market indicators — keys depend on mode
                          Common: rsi, vol_ratio, atr_pct, adx, macd_hist,
                                  vwap_above (bool), ma_aligned (bool)
            trades_today: how many trades have been taken today
        Returns:
            FilterResult
        """
        warnings: list = []
        score = 50.0  # neutral baseline

        # ── Universal hard filters ─────────────────────────────────────────

        if decision.decision == "WAIT":
            return FilterResult(
                passed=False,
                reason="Decision is WAIT — no trade to filter",
                warnings=[],
                quality_score=0.0,
            )

        if trades_today >= self.MAX_TRADES_PER_DAY:
            return FilterResult(
                passed=False,
                reason=f"Overtrading: {trades_today} trades today (max {self.MAX_TRADES_PER_DAY})",
                warnings=["Consider stopping for the day"],
                quality_score=20.0,
            )

        min_conf = self.MIN_CONFIDENCE_BY_MODE.get(mode, 30)
        if decision.confidence < min_conf:
            return FilterResult(
                passed=False,
                reason=f"Confidence {decision.confidence:.0f}% too low for {mode} (min {min_conf}%)",
                warnings=[],
                quality_score=decision.confidence,
            )

        # ── Mode-specific filters ──────────────────────────────────────────

        if mode == "scalp":
            score, warnings = self._filter_scalp(context, warnings)
        elif mode == "intraday":
            score, warnings = self._filter_intraday(context, warnings)
        elif mode == "swing":
            score, warnings = self._filter_swing(context, warnings)
        else:
            warnings.append(f"Unknown mode '{mode}' — applying relaxed filter")
            score = 55.0

        # Boost score if decision confidence is high
        score += decision.confidence * 0.10

        # ── Risk level penalty ─────────────────────────────────────────────
        if decision.risk_level == "HIGH":
            score -= 15
            warnings.append("Risk level is HIGH — position size should be reduced")
        elif decision.risk_level == "MEDIUM":
            score -= 5

        score = float(max(0.0, min(100.0, score)))

        # ── Pass/fail threshold ────────────────────────────────────────────
        if score >= 45:
            return FilterResult(
                passed=True,
                reason=f"Setup quality: {score:.0f}/100 — trade accepted ({mode})",
                warnings=warnings,
                quality_score=score,
            )
        else:
            return FilterResult(
                passed=False,
                reason=f"Setup quality too low: {score:.0f}/100 — NO TRADE ({mode})",
                warnings=warnings,
                quality_score=score,
            )

    # ──────────────────────────────────────────────────────────────────────
    # Mode-specific scoring
    # ──────────────────────────────────────────────────────────────────────

    def _filter_scalp(self, ctx: dict, warnings: list) -> tuple:
        score = 50.0
        rsi      = ctx.get("rsi")
        vol_rat  = ctx.get("vol_ratio", 1.0)
        atr_pct  = ctx.get("atr_pct", 0.5)

        # Volume confirmation
        if vol_rat and vol_rat >= 1.5:
            score += 20
        elif vol_rat and vol_rat >= 1.0:
            score += 5
        else:
            score -= 20
            warnings.append(f"Weak volume ({vol_rat:.2f}x) — breakout may be false")

        # RSI extremes
        if rsi is not None:
            if rsi > 80:
                score -= 20
                warnings.append(f"RSI {rsi:.1f} overbought — avoid chasing")
            elif rsi < 20:
                score -= 15
                warnings.append(f"RSI {rsi:.1f} oversold — risky short entry")
            elif 40 < rsi < 72:
                score += 15

        # ATR range (too tight = no scalp opportunity)
        if atr_pct is not None:
            if atr_pct < 0.2:
                score -= 15
                warnings.append(f"ATR {atr_pct:.2f}% — range too tight for scalping")
            elif atr_pct > 1.5:
                score -= 10
                warnings.append(f"ATR {atr_pct:.2f}% — very volatile, widen stops")
            else:
                score += 10

        return score, warnings

    def _filter_intraday(self, ctx: dict, warnings: list) -> tuple:
        score = 50.0
        macd_hist   = ctx.get("macd_hist")
        vwap_above  = ctx.get("vwap_above")   # bool: price above VWAP
        adx         = ctx.get("adx")
        rsi         = ctx.get("rsi")

        # MACD direction
        if macd_hist is not None:
            if macd_hist > 0:
                score += 15
            else:
                score -= 15
                warnings.append("MACD histogram negative — momentum against trade")

        # VWAP position
        if vwap_above is not None:
            if vwap_above:
                score += 15
            else:
                score -= 10
                warnings.append("Price below VWAP — selling pressure dominates session")

        # Trend strength
        if adx is not None:
            if adx > 25:
                score += 15
            elif adx < 15:
                score -= 15
                warnings.append(f"ADX {adx:.1f} — choppy market, intraday trend weak")

        # RSI
        if rsi is not None:
            if rsi > 75 or rsi < 25:
                score -= 10
                warnings.append(f"RSI {rsi:.1f} at extreme — extended move, beware reversal")

        return score, warnings

    def _filter_swing(self, ctx: dict, warnings: list) -> tuple:
        score = 50.0
        ma_aligned  = ctx.get("ma_aligned")    # bool: MA20 > MA50 for bull
        adx         = ctx.get("adx")
        rsi         = ctx.get("rsi")
        vol_rat     = ctx.get("vol_ratio", 1.0)

        # MA alignment
        if ma_aligned is not None:
            if ma_aligned:
                score += 20
            else:
                score -= 20
                warnings.append("MA20 below MA50 — swing trade against trend")

        # ADX
        if adx is not None:
            if adx > 20:
                score += 15
            else:
                score -= 10
                warnings.append(f"ADX {adx:.1f} — weak trend, swing setups less reliable")

        # RSI sanity
        if rsi is not None:
            if 30 < rsi < 75:
                score += 10
            elif rsi >= 75:
                score -= 10
                warnings.append(f"RSI {rsi:.1f} extended — swing entry near resistance")
            elif rsi <= 30:
                score += 5  # oversold can be swing entry but warn
                warnings.append(f"RSI {rsi:.1f} oversold — confirm reversal before entry")

        # Volume confirmation less strict for swing
        if vol_rat and vol_rat >= 1.2:
            score += 5

        return score, warnings
