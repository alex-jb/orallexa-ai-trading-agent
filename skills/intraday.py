"""
skills/intraday.py
──────────────────────────────────────────────────────────────────────────────
15-minute / 1-hour intraday analysis.

Scoring model:
  Trend     (EMA stack + price vs VWAP)      — 35%
  Momentum  (MACD histogram + RSI)           — 35%
  Session   (VWAP position + time context)   — 15%
  Volume    (Vol ratio vs 20-bar MA)          — 15%

Output: DecisionOutput(source="intraday")
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

import yfinance as yf

from skills.base import BaseFinancialSkill
from models.decision import DecisionOutput


_INTERVAL_MAP = {
    "15m": "15m",
    "1h":  "60m",
}

_STALE_MINUTES = {
    "15m": 30,
    "1h":  90,
}


class IntradaySkill(BaseFinancialSkill):
    """15m / 1h intraday trend + momentum analysis."""

    def execute(self, interval: str = "15m", lookback_bars: int = 96) -> DecisionOutput:
        yf_interval = _INTERVAL_MAP.get(interval, "15m")
        df = self._fetch(yf_interval, lookback_bars)
        df = self._add_indicators(df)
        return self._evaluate(df, interval)

    # ──────────────────────────────────────────────────────────────────────
    # Data
    # ──────────────────────────────────────────────────────────────────────

    def _fetch(self, yf_interval: str, bars: int) -> pd.DataFrame:
        ticker_obj = yf.Ticker(self.ticker)
        df = ticker_obj.history(period="10d", interval=yf_interval)

        if df is None or df.empty:
            raise ValueError(
                f"No {yf_interval} data for {self.ticker}. Market may be closed."
            )

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.tail(bars).copy()

        # Staleness check
        last_ts = df.index[-1]
        stale_threshold = _STALE_MINUTES.get(yf_interval, 60)
        try:
            if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is not None:
                now = datetime.now(timezone.utc)
            else:
                now = datetime.utcnow()
                last_ts = last_ts.replace(tzinfo=None)
            age_min = (now - last_ts).total_seconds() / 60
        except Exception:
            age_min = 0

        df.attrs["stale"]       = age_min > stale_threshold
        df.attrs["age_minutes"] = round(age_min, 1)
        return df

    # ──────────────────────────────────────────────────────────────────────
    # Indicators
    # ──────────────────────────────────────────────────────────────────────

    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        # EMA 9 / 21 — micro-trend
        df["EMA9"]  = df["Close"].ewm(span=9,  adjust=False).mean()
        df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()

        # MACD
        ema12 = df["Close"].ewm(span=12, adjust=False).mean()
        ema26 = df["Close"].ewm(span=26, adjust=False).mean()
        df["MACD"]      = ema12 - ema26
        df["MACD_Sig"]  = df["MACD"].ewm(span=9, adjust=False).mean()
        df["MACD_Hist"] = df["MACD"] - df["MACD_Sig"]

        # RSI-14
        delta = df["Close"].diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        df["RSI14"] = 100 - 100 / (1 + gain / (loss + 1e-9))

        # VWAP (rolling 20-bar)
        tp = (df["High"] + df["Low"] + df["Close"]) / 3
        df["VWAP"] = (tp * df["Volume"]).rolling(20).sum() / (df["Volume"].rolling(20).sum() + 1e-9)

        # Volume ratio
        df["Vol_MA20"]  = df["Volume"].rolling(20).mean()
        df["Vol_Ratio"] = df["Volume"] / (df["Vol_MA20"] + 1e-9)

        # ATR-14
        tr = pd.concat([
            df["High"] - df["Low"],
            (df["High"] - df["Close"].shift()).abs(),
            (df["Low"]  - df["Close"].shift()).abs(),
        ], axis=1).max(axis=1)
        df["ATR14"] = tr.rolling(14).mean()

        # ADX (simplified)
        plus_dm  = (df["High"].diff()).clip(lower=0)
        minus_dm = (-df["Low"].diff()).clip(lower=0)
        tr_smooth   = tr.rolling(14).mean()
        plus_di  = 100 * plus_dm.rolling(14).mean()  / (tr_smooth + 1e-9)
        minus_di = 100 * minus_dm.rolling(14).mean() / (tr_smooth + 1e-9)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
        df["ADX"] = dx.rolling(14).mean()

        return df.dropna().copy()

    # ──────────────────────────────────────────────────────────────────────
    # Evaluation
    # ──────────────────────────────────────────────────────────────────────

    def _evaluate(self, df: pd.DataFrame, interval: str) -> DecisionOutput:
        if len(df) < 5:
            return self._wait("Insufficient bars after indicator calculation.")

        latest = df.iloc[-1]
        prev   = df.iloc[-2]
        reasoning: list = []
        score = 0.0

        if df.attrs.get("stale"):
            age = df.attrs.get("age_minutes", "?")
            reasoning.append(
                f"Warning: last {interval} bar is {age} min old — data may be delayed."
            )

        close    = float(latest["Close"])
        ema9     = float(latest["EMA9"])
        ema21    = float(latest["EMA21"])
        ema50    = float(latest["EMA50"])
        macd_h   = float(latest["MACD_Hist"])
        rsi14    = float(latest["RSI14"])
        vwap     = float(latest["VWAP"])
        vol_rat  = float(latest["Vol_Ratio"])
        adx      = float(latest["ADX"])

        # ── TREND (35 pts max) ─────────────────────────────────────────────
        reasoning.append("Step 1: Trend analysis")

        if close > ema9 > ema21 > ema50:
            score += 25
            reasoning.append(f"  Strong uptrend: Price > EMA9 > EMA21 > EMA50")
        elif close > ema9 > ema21:
            score += 15
            reasoning.append(f"  Moderate uptrend: Price > EMA9 > EMA21")
        elif close < ema9 < ema21 < ema50:
            score -= 15
            reasoning.append(f"  Downtrend: Price < EMA9 < EMA21 < EMA50")
        elif close < ema9 < ema21:
            score -= 10
            reasoning.append(f"  Mild downtrend: Price < EMA9 < EMA21")
        else:
            reasoning.append(f"  Mixed/choppy trend")

        if adx > 25:
            score += 10
            reasoning.append(f"  ADX {adx:.1f} — trend is strong")
        elif adx < 15:
            score -= 5
            reasoning.append(f"  ADX {adx:.1f} — weak trend, choppy market")

        # ── MOMENTUM (35 pts max) ──────────────────────────────────────────
        reasoning.append("Step 2: Momentum")

        prev_macd_h = float(prev["MACD_Hist"])
        if macd_h > 0 and macd_h > prev_macd_h:
            score += 20
            reasoning.append(f"  MACD histogram rising ({macd_h:.4f}) — accelerating bullish")
        elif macd_h > 0:
            score += 10
            reasoning.append(f"  MACD histogram positive ({macd_h:.4f})")
        elif macd_h < 0 and macd_h < prev_macd_h:
            score -= 15
            reasoning.append(f"  MACD histogram falling ({macd_h:.4f}) — accelerating bearish")
        elif macd_h < 0:
            score -= 8
            reasoning.append(f"  MACD histogram negative ({macd_h:.4f})")

        if 45 < rsi14 < 70:
            score += 15
            reasoning.append(f"  RSI14 {rsi14:.1f} — healthy momentum range")
        elif rsi14 >= 70:
            score += 3
            reasoning.append(f"  RSI14 {rsi14:.1f} — overbought, momentum strong but extended")
        elif 30 < rsi14 <= 45:
            score -= 5
            reasoning.append(f"  RSI14 {rsi14:.1f} — below midline, mild bearish")
        else:
            score += 5
            reasoning.append(f"  RSI14 {rsi14:.1f} — oversold, potential bounce")

        # ── SESSION / VWAP (15 pts max) ────────────────────────────────────
        reasoning.append("Step 3: Session context")

        if close > vwap:
            score += 10
            reasoning.append(f"  Price {close:.2f} above VWAP {vwap:.2f} — buyers in control")
        elif close < vwap:
            score -= 10
            reasoning.append(f"  Price {close:.2f} below VWAP {vwap:.2f} — sellers in control")

        vwap_dist_pct = abs(close - vwap) / (vwap + 1e-9) * 100
        if vwap_dist_pct > 2.0:
            score -= 5
            reasoning.append(f"  Price extended {vwap_dist_pct:.1f}% from VWAP — mean reversion risk")

        # ── VOLUME (15 pts max) ────────────────────────────────────────────
        reasoning.append("Step 4: Volume")

        if vol_rat > 1.5:
            score += 15
            reasoning.append(f"  Volume spike {vol_rat:.2f}x — strong participation")
        elif vol_rat > 1.0:
            score += 5
            reasoning.append(f"  Volume ratio {vol_rat:.2f}x — normal")
        else:
            score -= 5
            reasoning.append(f"  Low volume {vol_rat:.2f}x — weak participation")

        # ── Conflicting signal detection ──────────────────────────────────
        _trend_bullish = (close > ema9 > ema21) or (close > vwap)
        _trend_bearish = (close < ema9 < ema21) or (close < vwap)
        _mom_bullish   = macd_h > 0 and rsi14 > 50
        _mom_bearish   = macd_h < 0 and rsi14 < 50
        _conflicting   = (_trend_bullish and _mom_bearish) or (_trend_bearish and _mom_bullish)

        if _conflicting:
            score *= 0.6   # dampen score when signals oppose each other
            reasoning.append("Warning: trend and momentum are opposing — signal reliability reduced")

        # ── Quality filter ────────────────────────────────────────────────
        has_trend    = abs(score) >= 15         # meaningful trend signal
        has_momentum = abs(macd_h) > 0 or (45 < rsi14 < 72)

        if not (has_trend or has_momentum):
            from models.confidence import scale_confidence, make_recommendation
            reasoning.append("Trade filter: no clear trend or momentum — WAIT")
            _norm = float(max(0.0, min(100.0, score + 50)))
            _conf = scale_confidence(abs(_norm - 50) * 2)
            _stale = df.attrs.get("stale", False)
            return DecisionOutput(
                decision="WAIT",
                confidence=_conf,
                risk_level="HIGH",
                reasoning=reasoning,
                probabilities={"up": 0.33, "down": 0.33, "neutral": 0.34},
                source="intraday",
                signal_strength=round(_norm, 1),
                recommendation=make_recommendation("WAIT", _conf, "HIGH", stale=_stale),
            )

        # ── Route to decision ─────────────────────────────────────────────
        reasoning.append("Step 5: Decision")

        normalized = float(max(0.0, min(100.0, score + 50)))  # shift -50..+50 → 0..100

        if normalized >= 65:
            decision = "BUY"
        elif normalized <= 35:
            decision = "SELL"
        else:
            decision = "WAIT"

        from models.confidence import scale_confidence, score_to_risk, make_recommendation
        raw_confidence = abs(normalized - 50) * 2   # 0–100 before capping
        confidence  = scale_confidence(raw_confidence)
        stale       = df.attrs.get("stale", False)
        risk_level  = score_to_risk(normalized, stale=stale)

        up   = round(min(0.85, 0.33 + normalized / 200), 2)
        down = round(max(0.05, 0.33 - normalized / 300), 2)
        neut = round(max(0.05, 1.0 - up - down), 2)

        if decision == "SELL":
            up, down = down, up

        recommendation = make_recommendation(decision, confidence, risk_level, stale=stale)
        reasoning.append(
            f"  {decision} | Signal: {normalized:.0f}/100 | Confidence: {confidence:.0f}%"
        )

        return DecisionOutput(
            decision=decision,
            confidence=round(confidence, 1),
            risk_level=risk_level,
            reasoning=reasoning,
            probabilities={"up": up, "neutral": neut, "down": down},
            source="intraday",
            signal_strength=round(normalized, 1),
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
            source="intraday",
            signal_strength=0.0,
            recommendation=make_recommendation("WAIT", 0.0, "HIGH"),
        )
