"""
skills/scalping.py
──────────────────────────────────────────────────────────────────────────────
5-minute scalping analysis.
Detects: breakout, pullback-to-EMA, volume spike setups.
Applies a quality filter to reject low-confidence setups.

Output: DecisionOutput(decision BUY/SELL/WAIT, confidence, risk_level,
                       reasoning, probabilities, source="scalping")
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

import yfinance as yf

from skills.base import BaseFinancialSkill
from models.decision import DecisionOutput


class ScalpingSkill(BaseFinancialSkill):
    """5-minute scalping setup detector."""

    STALE_MINUTES = 30  # warn if last bar is older than this

    def execute(self, lookback_bars: int = 80) -> DecisionOutput:
        df = self._fetch_5min(lookback_bars)
        df = self._add_indicators(df)
        return self._evaluate(df)

    # ──────────────────────────────────────────────────────────────────────
    # Data
    # ──────────────────────────────────────────────────────────────────────

    def _fetch_5min(self, bars: int) -> pd.DataFrame:
        ticker_obj = yf.Ticker(self.ticker)
        df = ticker_obj.history(period="5d", interval="5m")

        if df is None or df.empty:
            raise ValueError(f"No 5-min data for {self.ticker}. Market may be closed.")

        # Flatten MultiIndex if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.tail(bars).copy()

        # Staleness check — surface as metadata, not exception
        last_ts = df.index[-1]
        if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is not None:
            now = datetime.now(timezone.utc)
        else:
            now = datetime.utcnow()
            last_ts = last_ts.replace(tzinfo=None)

        age_minutes = (now - last_ts).total_seconds() / 60
        df.attrs["stale"] = age_minutes > self.STALE_MINUTES
        df.attrs["age_minutes"] = round(age_minutes, 1)

        return df

    # ──────────────────────────────────────────────────────────────────────
    # Indicators
    # ──────────────────────────────────────────────────────────────────────

    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        # EMA 9 / 21 for micro-trend (faster than SMA on 5-min)
        df["EMA9"]  = df["Close"].ewm(span=9,  adjust=False).mean()
        df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()

        # RSI-7 — shorter period for scalp sensitivity
        delta = df["Close"].diff()
        gain  = delta.clip(lower=0).rolling(7).mean()
        loss  = (-delta.clip(upper=0)).rolling(7).mean()
        df["RSI7"] = 100 - 100 / (1 + gain / (loss + 1e-9))

        # Volume ratio vs 20-bar rolling average
        df["Vol_MA20"] = df["Volume"].rolling(20).mean()
        df["Vol_Ratio"] = df["Volume"] / (df["Vol_MA20"] + 1e-9)

        # ATR-5 for volatility context
        tr = pd.concat([
            df["High"] - df["Low"],
            (df["High"] - df["Close"].shift()).abs(),
            (df["Low"]  - df["Close"].shift()).abs(),
        ], axis=1).max(axis=1)
        df["ATR5"] = tr.rolling(5).mean()

        # 20-bar rolling high/low for breakout detection
        df["High20"] = df["High"].rolling(20).max()
        df["Low20"]  = df["Low"].rolling(20).min()

        return df.dropna().copy()

    # ──────────────────────────────────────────────────────────────────────
    # Evaluation
    # ──────────────────────────────────────────────────────────────────────

    def _evaluate(self, df: pd.DataFrame) -> DecisionOutput:
        if len(df) < 3:
            return self._wait("Insufficient bars after indicator calculation.")

        latest = df.iloc[-1]
        prev   = df.iloc[-2]
        reasoning: list = []
        score = 0.0

        # Staleness warning
        if df.attrs.get("stale"):
            age = df.attrs.get("age_minutes", "?")
            reasoning.append(
                f"Warning: last bar is {age} min old — market may be closed or data delayed."
            )

        close     = float(latest["Close"])
        high20    = float(latest["High20"])
        low20     = float(latest["Low20"])
        ema9      = float(latest["EMA9"])
        ema21     = float(latest["EMA21"])
        rsi7      = float(latest["RSI7"])
        vol_ratio = float(latest["Vol_Ratio"])
        atr5      = float(latest["ATR5"])

        # ── Setup 1: Bullish breakout ──────────────────────────────────────
        bullish_breakout = close >= high20 * 0.999
        if bullish_breakout:
            score += 30
            reasoning.append(
                f"Breakout: Close {close:.2f} at/above 20-bar high {high20:.2f}"
            )

        # ── Setup 2: Bearish breakdown ─────────────────────────────────────
        bearish_breakdown = close <= low20 * 1.001
        if bearish_breakdown:
            score += 30  # counted separately for sell path
            reasoning.append(
                f"Breakdown: Close {close:.2f} at/below 20-bar low {low20:.2f}"
            )

        # ── Setup 3: Pullback to EMA9 in uptrend ──────────────────────────
        in_uptrend    = ema9 > ema21
        near_ema9     = abs(close - ema9) / (ema9 + 1e-9) < 0.003
        pullback_bull = in_uptrend and near_ema9
        if pullback_bull:
            score += 25
            reasoning.append(
                f"Pullback to EMA9 ({ema9:.2f}) in uptrend (EMA9 > EMA21)"
            )

        # ── Setup 4: Volume spike ──────────────────────────────────────────
        vol_spike = vol_ratio > 1.8
        if vol_spike:
            score += 20
            reasoning.append(f"Volume spike: {vol_ratio:.2f}x the 20-bar average")
        else:
            reasoning.append(f"Volume ratio: {vol_ratio:.2f}x (no spike)")

        # ── Setup 5: RSI momentum ──────────────────────────────────────────
        if 45 < rsi7 < 72:
            score += 15
            reasoning.append(f"RSI7 at {rsi7:.1f} — healthy momentum range")
        elif rsi7 > 80:
            score -= 20
            reasoning.append(f"RSI7 overbought ({rsi7:.1f}) — degraded signal quality")
        elif rsi7 < 30:
            score -= 10
            reasoning.append(f"RSI7 oversold ({rsi7:.1f}) — potential mean reversion risk")
        else:
            reasoning.append(f"RSI7 at {rsi7:.1f} — neutral")

        # ── Setup 6: EMA micro-trend confirmation ─────────────────────────
        prev_ema9  = float(prev["EMA9"])
        prev_ema21 = float(prev["EMA21"])
        trend_confirmed = in_uptrend and (prev_ema9 > prev_ema21)
        if trend_confirmed:
            score += 10
            reasoning.append("Micro-trend confirmed: EMA9 > EMA21 for 2+ consecutive bars")

        # ── ATR context ───────────────────────────────────────────────────
        atr_pct = atr5 / (close + 1e-9) * 100
        if atr_pct > 0.5:
            reasoning.append(
                f"ATR5 = {atr5:.2f} ({atr_pct:.2f}% of price) — good scalp range"
            )
        else:
            score -= 5
            reasoning.append(
                f"ATR5 = {atr5:.2f} ({atr_pct:.2f}% of price) — very tight range"
            )

        # ── Conflicting signal detection ──────────────────────────────────
        # Simultaneous breakout + breakdown = directionless chop
        if bullish_breakout and bearish_breakdown:
            reasoning.append("Warning: both breakout and breakdown detected — directionless, forcing WAIT")
            return self._wait("Conflicting signals — simultaneous breakout and breakdown detected.")

        # Breakout but RSI overbought = exhaustion risk
        if bullish_breakout and rsi7 > 80:
            score -= 15
            reasoning.append("Warning: breakout with overbought RSI — exhaustion risk, signal degraded")

        # Breakdown but RSI oversold = bounce risk
        if bearish_breakdown and rsi7 < 20:
            score -= 15
            reasoning.append("Warning: breakdown with oversold RSI — bounce risk, signal degraded")

        # ── Quality filter ────────────────────────────────────────────────
        # Require at least one primary setup AND (volume spike OR RSI in range)
        has_primary   = bullish_breakout or pullback_bull or bearish_breakdown
        has_secondary = vol_spike or (45 < rsi7 < 72)

        if not has_primary:
            from models.confidence import scale_confidence, make_recommendation
            reasoning.append("Trade filter: no primary setup detected (no breakout or pullback)")
            _sig = round(min(float(max(0.0, score)), 100.0), 1)
            return DecisionOutput(
                decision="WAIT",
                confidence=scale_confidence(max(0.0, float(score))),
                risk_level="HIGH",
                reasoning=reasoning,
                probabilities={"up": 0.33, "down": 0.33, "neutral": 0.34},
                source="scalping",
                signal_strength=_sig,
                recommendation=make_recommendation("WAIT", 0.0, "HIGH"),
            )

        if not has_secondary:
            from models.confidence import scale_confidence, make_recommendation
            reasoning.append("Trade filter: setup present but lacks volume or RSI confirmation")
            _sig = round(min(float(max(0.0, score)), 100.0), 1)
            return DecisionOutput(
                decision="WAIT",
                confidence=scale_confidence(max(0.0, float(score))),
                risk_level="HIGH",
                reasoning=reasoning,
                probabilities={"up": 0.38, "down": 0.32, "neutral": 0.30},
                source="scalping",
                signal_strength=_sig,
                recommendation=make_recommendation("WAIT", 0.0, "HIGH"),
            )

        # ── Route to BUY / SELL ───────────────────────────────────────────
        _stale = df.attrs.get("stale", False)
        if bearish_breakdown and not bullish_breakout:
            return self._sell_output(score, reasoning, stale=_stale)

        return self._buy_output(score, reasoning, stale=_stale)

    # ──────────────────────────────────────────────────────────────────────
    # Output builders
    # ──────────────────────────────────────────────────────────────────────

    def _buy_output(self, score: float, reasoning: list, stale: bool = False) -> DecisionOutput:
        from models.confidence import scale_confidence, score_to_risk, make_recommendation
        signal_strength = round(min(float(score), 100.0), 1)
        confidence  = scale_confidence(signal_strength)
        risk_level  = score_to_risk(signal_strength, stale=stale)
        up   = round(min(0.85, 0.33 + score / 200), 2)
        down = round(max(0.05, 0.33 - score / 300), 2)
        neut = round(max(0.05, 1.0 - up - down), 2)
        recommendation = make_recommendation("BUY", confidence, risk_level, stale=stale)
        reasoning.append(f"Decision: BUY | Signal: {signal_strength:.0f}/100 | Confidence: {confidence:.0f}%")
        return DecisionOutput(
            decision="BUY",
            confidence=confidence,
            risk_level=risk_level,
            reasoning=reasoning,
            probabilities={"up": up, "neutral": neut, "down": down},
            source="scalping",
            signal_strength=signal_strength,
            recommendation=recommendation,
        )

    def _sell_output(self, score: float, reasoning: list, stale: bool = False) -> DecisionOutput:
        from models.confidence import scale_confidence, score_to_risk, make_recommendation
        signal_strength = round(min(float(score), 100.0), 1)
        confidence  = scale_confidence(signal_strength)
        risk_level  = score_to_risk(signal_strength, stale=stale)
        down = round(min(0.80, 0.33 + score / 200), 2)
        up   = round(max(0.05, 0.33 - score / 300), 2)
        neut = round(max(0.05, 1.0 - up - down), 2)
        recommendation = make_recommendation("SELL", confidence, risk_level, stale=stale)
        reasoning.append(f"Decision: SELL | Signal: {signal_strength:.0f}/100 | Confidence: {confidence:.0f}%")
        return DecisionOutput(
            decision="SELL",
            confidence=confidence,
            risk_level=risk_level,
            reasoning=reasoning,
            probabilities={"up": up, "neutral": neut, "down": down},
            source="scalping",
            signal_strength=signal_strength,
            recommendation=recommendation,
        )

    def _wait(self, reason: str) -> DecisionOutput:
        from models.confidence import make_recommendation
        return DecisionOutput(
            decision="WAIT",
            confidence=0.0,
            risk_level="HIGH",
            reasoning=[reason],
            probabilities={"up": 0.33, "down": 0.33, "neutral": 0.34},
            source="scalping",
            signal_strength=0.0,
            recommendation=make_recommendation("WAIT", 0.0, "HIGH"),
        )
