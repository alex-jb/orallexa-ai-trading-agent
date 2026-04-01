"""
skills/prediction.py
──────────────────────────────────────────────────────────────────────────────
Probability-based prediction skill.
Combines technical indicator scoring with an optional Claude overlay.

Output: DecisionOutput with source="prediction"
"""

import pandas as pd

from skills.base import BaseFinancialSkill
from skills.market_data import MarketDataSkill
from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2
from models.decision import DecisionOutput


class PredictionSkill(BaseFinancialSkill):
    """
    Daily/swing prediction using technical indicators + optional Claude analysis.
    Returns a DecisionOutput with probability breakdown and step-by-step reasoning.
    """

    def execute(
        self,
        period: str = "3mo",
        use_claude: bool = True,
        rag_context: str = "",
        sentiment_score: float = None,  # avg_compound from engine/sentiment.py (-1 to +1)
        mode: str = "swing",            # affects how much sentiment is weighted
    ) -> DecisionOutput:
        data = MarketDataSkill(self.ticker).execute()
        ta   = TechnicalAnalysisSkillV2(data).add_indicators().dropna().copy()

        summary = self._extract_summary(ta)
        score, reasoning = self._score_technicals(summary)

        # Apply news sentiment weighting for swing mode (Step 12)
        if sentiment_score is not None and mode == "swing":
            if sentiment_score > 0.15:
                score = min(100.0, score + 10)
                reasoning.append(
                    f"  News sentiment bullish ({sentiment_score:+.2f}) — swing bias boosted"
                )
            elif sentiment_score < -0.15:
                score = max(0.0, score - 10)
                reasoning.append(
                    f"  News sentiment bearish ({sentiment_score:+.2f}) — swing bias reduced"
                )
            else:
                reasoning.append(
                    f"  News sentiment neutral ({sentiment_score:+.2f}) — no adjustment"
                )

        # Inject past trade reflections for this ticker into RAG context
        try:
            from bot.behavior import BehaviorMemory
            reflections = BehaviorMemory().get_relevant_reflections(self.ticker, n=3)
            if reflections:
                reflection_block = "\n\nPast Trade Reflections:\n" + "\n---\n".join(reflections)
                rag_context = (rag_context or "") + reflection_block
        except Exception:
            pass

        return self._build_output(summary, score, reasoning, use_claude, rag_context)

    # ──────────────────────────────────────────────────────────────────────
    # Technical scoring
    # ──────────────────────────────────────────────────────────────────────

    def _extract_summary(self, ta: pd.DataFrame) -> dict:
        latest = ta.iloc[-1]

        def safe(x):
            try:
                v = float(x)
                return None if v != v else v
            except Exception:
                return None

        close_col = "Close" if "Close" in ta.columns else "Adj Close"
        return {
            "close":        safe(latest.get(close_col)),
            "ma20":         safe(latest.get("MA20")),
            "ma50":         safe(latest.get("MA50")),
            "rsi":          safe(latest.get("RSI")),
            "macd":         safe(latest.get("MACD")),
            "macd_hist":    safe(latest.get("MACD_Hist")),
            "bb_pct":       safe(latest.get("BB_Pct")),
            "atr_pct":      safe(latest.get("ATR_Pct")),
            "adx":          safe(latest.get("ADX")),
            "volume_ratio": safe(latest.get("Volume_Ratio")),
        }

    def _score_technicals(self, s: dict) -> tuple:
        """
        Score indicators on a 0–100 scale (bullish = higher).
        Returns (score: float, reasoning: list[str]).
        """
        score = 50.0  # neutral baseline
        reasoning = ["Step 1: Technical analysis"]

        close = s.get("close") or 0
        ma20  = s.get("ma20")
        ma50  = s.get("ma50")
        rsi   = s.get("rsi")
        macd_hist = s.get("macd_hist")
        bb_pct    = s.get("bb_pct")
        adx       = s.get("adx")
        vol_ratio = s.get("volume_ratio")

        # MA alignment
        if ma20 and ma50:
            if close > ma20 > ma50:
                score += 15
                reasoning.append(f"  Price ({close:.2f}) > MA20 ({ma20:.2f}) > MA50 ({ma50:.2f}) — bullish stack")
            elif close < ma20 < ma50:
                score -= 15
                reasoning.append(f"  Price ({close:.2f}) < MA20 ({ma20:.2f}) < MA50 ({ma50:.2f}) — bearish stack")
            elif close > ma20:
                score += 5
                reasoning.append(f"  Price above MA20 but MA20 < MA50 — mixed")
            else:
                score -= 5
                reasoning.append(f"  Price below MA20 — weak short-term trend")

        # RSI
        if rsi is not None:
            if 50 < rsi < 70:
                score += 10
                reasoning.append(f"  RSI {rsi:.1f} — bullish momentum, not overbought")
            elif rsi >= 70:
                score += 3
                reasoning.append(f"  RSI {rsi:.1f} — overbought, momentum strong but risky")
            elif 30 < rsi <= 50:
                score -= 5
                reasoning.append(f"  RSI {rsi:.1f} — below midline, mild bearish pressure")
            else:
                score += 8
                reasoning.append(f"  RSI {rsi:.1f} — oversold, potential mean reversion")

        # MACD histogram
        if macd_hist is not None:
            if macd_hist > 0:
                score += 8
                reasoning.append(f"  MACD histogram positive ({macd_hist:.3f}) — bullish momentum")
            else:
                score -= 8
                reasoning.append(f"  MACD histogram negative ({macd_hist:.3f}) — bearish momentum")

        # Bollinger Band position
        if bb_pct is not None:
            if 0.4 < bb_pct < 0.8:
                score += 5
                reasoning.append(f"  BB%: {bb_pct:.2f} — mid-to-upper band, healthy trend")
            elif bb_pct >= 0.9:
                score -= 5
                reasoning.append(f"  BB%: {bb_pct:.2f} — near upper band, extended")
            elif bb_pct <= 0.1:
                score += 3
                reasoning.append(f"  BB%: {bb_pct:.2f} — near lower band, mean reversion possible")

        # ADX (trend strength)
        if adx is not None:
            if adx > 25:
                score += 7
                reasoning.append(f"  ADX {adx:.1f} — strong trend in play")
            elif adx < 15:
                score -= 5
                reasoning.append(f"  ADX {adx:.1f} — weak/choppy market")

        # Volume
        if vol_ratio is not None:
            if vol_ratio > 1.5:
                score += 5
                reasoning.append(f"  Volume ratio {vol_ratio:.2f}x — institutional participation likely")

        score = float(max(0.0, min(100.0, score)))
        return score, reasoning

    # ──────────────────────────────────────────────────────────────────────
    # Output construction
    # ──────────────────────────────────────────────────────────────────────

    def _build_output(
        self,
        summary: dict,
        score: float,
        reasoning: list,
        use_claude: bool,
        rag_context: str,
    ) -> DecisionOutput:
        reasoning.append("Step 2: Probability estimation")

        if use_claude:
            try:
                from llm.ui_analysis import prediction_decision_report
                result = prediction_decision_report(
                    summary=summary,
                    tech_score=score,
                    ticker=self.ticker,
                    rag_context=rag_context,
                )
                from models.confidence import scale_confidence, score_to_risk, make_recommendation
                raw_conf   = float(result.get("confidence", 50))
                confidence = scale_confidence(raw_conf)
                risk_level = result.get("risk_level", score_to_risk(score))
                decision   = result["decision"]
                recommendation = make_recommendation(decision, confidence, risk_level)

                reasoning.append(f"  Claude overlay applied (tech score: {score:.0f}/100)")
                reasoning.append(f"  Claude reasoning: {result.get('reasoning_summary', 'N/A')}")
                reasoning.append("Step 3: Decision")
                reasoning.append(f"  {decision} | Signal: {score:.0f}/100 | Confidence: {confidence:.0f}%")

                # Normalize Claude probabilities to sum to 1.0
                _up   = float(result.get("up_probability", 0.33))
                _neut = float(result.get("neutral_probability", 0.33))
                _down = float(result.get("down_probability", 0.34))
                _total = _up + _neut + _down
                if _total > 0 and abs(_total - 1.0) > 0.01:
                    _up, _neut, _down = _up / _total, _neut / _total, _down / _total

                return DecisionOutput(
                    decision=decision,
                    confidence=confidence,
                    risk_level=risk_level,
                    reasoning=reasoning,
                    probabilities={
                        "up":      round(_up, 3),
                        "neutral": round(_neut, 3),
                        "down":    round(_down, 3),
                    },
                    source="prediction",
                    signal_strength=round(float(score), 1),
                    recommendation=recommendation,
                )
            except Exception as e:
                reasoning.append(f"  Claude overlay failed: {e} — using technicals only")

        # Fallback: pure technical decision
        return self._technical_only_output(score, reasoning)

    def _technical_only_output(self, score: float, reasoning: list) -> DecisionOutput:
        from models.confidence import scale_confidence, score_to_risk, make_recommendation
        reasoning.append("Step 3: Decision (technical only)")

        if score >= 65:
            decision = "BUY"
            up   = round(min(0.85, 0.33 + score / 200), 2)
            down = round(max(0.05, 0.33 - score / 300), 2)
        elif score <= 35:
            decision = "SELL"
            down = round(min(0.85, 0.33 + (100 - score) / 200), 2)
            up   = round(max(0.05, 0.33 - (100 - score) / 300), 2)
        else:
            decision = "WAIT"
            up, down = 0.38, 0.28

        neut       = round(max(0.05, 1.0 - up - down), 2)
        confidence = scale_confidence(abs(score - 50) * 2)
        risk_level = score_to_risk(score)
        recommendation = make_recommendation(decision, confidence, risk_level)
        reasoning.append(f"  {decision} | Signal: {score:.0f}/100 | Confidence: {confidence:.0f}%")

        return DecisionOutput(
            decision=decision,
            confidence=float(confidence),
            risk_level=risk_level,
            reasoning=reasoning,
            probabilities={"up": up, "neutral": neut, "down": down},
            source="prediction",
            signal_strength=round(float(score), 1),
            recommendation=recommendation,
        )
