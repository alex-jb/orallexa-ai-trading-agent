"""
skills/technical_analysis_v2.py
Enhanced TechnicalAnalysisSkill — inspired by ai_quant_trade strategies.
Adds: MACD, Bollinger Bands, ATR, Volume indicators, Stochastic, ADX.
Drop-in replacement for the original TechnicalAnalysisSkill.
"""

import numpy as np
import pandas as pd


class TechnicalAnalysisSkillV2:
    """
    Extended technical indicator library.
    Covers all signals used by the strategy engine:
      - Trend:     MA5/10/20/50, EMA, MACD, ADX
      - Momentum:  RSI, Stochastic %K/%D, ROC
      - Volatility: Bollinger Bands, ATR, Historical Volatility
      - Volume:    OBV, VWAP (daily), Volume MA, Volume Ratio
    """

    def __init__(self, df: pd.DataFrame):
        """
        df must have columns: Open, High, Low, Close, Volume
        Index should be a DatetimeIndex.
        """
        self.df = df.copy()

    # ──────────────────────────────────────────────
    # TREND INDICATORS
    # ──────────────────────────────────────────────

    def _add_moving_averages(self) -> "TechnicalAnalysisSkillV2":
        for period in [5, 10, 20, 50, 200]:
            self.df[f"MA{period}"] = (
                self.df["Close"].rolling(window=period, min_periods=1).mean()
            )
        # Exponential MAs
        for period in [12, 26]:
            self.df[f"EMA{period}"] = (
                self.df["Close"].ewm(span=period, adjust=False).mean()
            )
        return self

    def _add_macd(self) -> "TechnicalAnalysisSkillV2":
        """MACD = EMA12 - EMA26, Signal = EMA9 of MACD, Histogram = MACD - Signal"""
        ema12 = self.df["Close"].ewm(span=12, adjust=False).mean()
        ema26 = self.df["Close"].ewm(span=26, adjust=False).mean()
        self.df["MACD"]        = ema12 - ema26
        self.df["MACD_Signal"] = self.df["MACD"].ewm(span=9, adjust=False).mean()
        self.df["MACD_Hist"]   = self.df["MACD"] - self.df["MACD_Signal"]
        # Cross signals
        self.df["MACD_Cross_Up"]   = (
            (self.df["MACD"] > self.df["MACD_Signal"]) &
            (self.df["MACD"].shift(1) <= self.df["MACD_Signal"].shift(1))
        ).astype(int)
        self.df["MACD_Cross_Down"] = (
            (self.df["MACD"] < self.df["MACD_Signal"]) &
            (self.df["MACD"].shift(1) >= self.df["MACD_Signal"].shift(1))
        ).astype(int)
        return self

    def _add_adx(self, period: int = 14) -> "TechnicalAnalysisSkillV2":
        """Average Directional Index — measures trend strength (>25 = strong trend)"""
        high  = self.df["High"]
        low   = self.df["Low"]
        close = self.df["Close"]

        plus_dm  = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm  < 0] = 0
        minus_dm[minus_dm < 0] = 0
        plus_dm[plus_dm <= minus_dm]  = 0
        minus_dm[minus_dm <= plus_dm] = 0 if False else minus_dm[minus_dm <= plus_dm]  # keep

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs()
        ], axis=1).max(axis=1)

        atr       = tr.ewm(span=period, adjust=False).mean()
        plus_di   = 100 * plus_dm.ewm(span=period, adjust=False).mean()  / atr
        minus_di  = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr
        dx        = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)

        self.df["ADX"]       = dx.ewm(span=period, adjust=False).mean()
        self.df["Plus_DI"]   = plus_di
        self.df["Minus_DI"]  = minus_di
        return self

    # ──────────────────────────────────────────────
    # MOMENTUM INDICATORS
    # ──────────────────────────────────────────────

    def _add_rsi(self, period: int = 14) -> "TechnicalAnalysisSkillV2":
        delta  = self.df["Close"].diff()
        gain   = delta.clip(lower=0).rolling(window=period, min_periods=1).mean()
        loss   = (-delta.clip(upper=0)).rolling(window=period, min_periods=1).mean()
        rs     = gain / (loss + 1e-9)
        self.df["RSI"] = 100 - (100 / (1 + rs))
        return self

    def _add_stochastic(self, k_period: int = 14, d_period: int = 3) -> "TechnicalAnalysisSkillV2":
        """Stochastic Oscillator %K and %D"""
        low_min  = self.df["Low"].rolling(window=k_period, min_periods=1).min()
        high_max = self.df["High"].rolling(window=k_period, min_periods=1).max()
        self.df["Stoch_K"] = 100 * (self.df["Close"] - low_min) / (high_max - low_min + 1e-9)
        self.df["Stoch_D"] = self.df["Stoch_K"].rolling(window=d_period, min_periods=1).mean()
        return self

    def _add_roc(self, period: int = 10) -> "TechnicalAnalysisSkillV2":
        """Rate of Change — momentum"""
        self.df["ROC"] = self.df["Close"].pct_change(periods=period) * 100
        return self

    # ──────────────────────────────────────────────
    # VOLATILITY INDICATORS
    # ──────────────────────────────────────────────

    def _add_bollinger_bands(self, period: int = 20, std_dev: float = 2.0) -> "TechnicalAnalysisSkillV2":
        """Bollinger Bands — upper/lower/mid + %B + bandwidth"""
        mid   = self.df["Close"].rolling(window=period, min_periods=1).mean()
        std   = self.df["Close"].rolling(window=period, min_periods=1).std()
        self.df["BB_Mid"]   = mid
        self.df["BB_Upper"] = mid + std_dev * std
        self.df["BB_Lower"] = mid - std_dev * std
        # %B: 0 = at lower band, 1 = at upper band
        self.df["BB_Pct"]   = (
            (self.df["Close"] - self.df["BB_Lower"]) /
            (self.df["BB_Upper"] - self.df["BB_Lower"] + 1e-9)
        )
        # Bandwidth: measures squeeze
        self.df["BB_Width"] = (self.df["BB_Upper"] - self.df["BB_Lower"]) / (mid + 1e-9)
        return self

    def _add_atr(self, period: int = 14) -> "TechnicalAnalysisSkillV2":
        """Average True Range — volatility measure for stop-loss sizing"""
        high  = self.df["High"]
        low   = self.df["Low"]
        close = self.df["Close"]
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        self.df["ATR"] = tr.rolling(window=period, min_periods=1).mean()
        # ATR as % of price — normalized
        self.df["ATR_Pct"] = self.df["ATR"] / (self.df["Close"] + 1e-9)
        return self

    def _add_historical_volatility(self, period: int = 20) -> "TechnicalAnalysisSkillV2":
        """20-day historical volatility (annualised)"""
        log_ret = np.log(self.df["Close"] / self.df["Close"].shift(1))
        self.df["HV20"] = log_ret.rolling(window=period, min_periods=1).std() * np.sqrt(252)
        return self

    # ──────────────────────────────────────────────
    # VOLUME INDICATORS
    # ──────────────────────────────────────────────

    def _add_obv(self) -> "TechnicalAnalysisSkillV2":
        """On-Balance Volume"""
        direction = np.sign(self.df["Close"].diff().fillna(0))
        self.df["OBV"] = (direction * self.df["Volume"]).cumsum()
        return self

    def _add_volume_indicators(self, period: int = 20) -> "TechnicalAnalysisSkillV2":
        """Volume MA and Volume Ratio (current vs average)"""
        self.df["Volume_MA"] = self.df["Volume"].rolling(window=period, min_periods=1).mean()
        self.df["Volume_Ratio"] = self.df["Volume"] / (self.df["Volume_MA"] + 1e-9)
        # Volume surge flag
        self.df["Volume_Surge"] = (self.df["Volume_Ratio"] > 2.0).astype(int)
        return self

    def _add_vwap(self) -> "TechnicalAnalysisSkillV2":
        """Daily VWAP approximation using rolling window"""
        typical_price = (self.df["High"] + self.df["Low"] + self.df["Close"]) / 3
        self.df["VWAP"] = (
            (typical_price * self.df["Volume"]).rolling(window=20, min_periods=1).sum() /
            self.df["Volume"].rolling(window=20, min_periods=1).sum()
        )
        return self

    # ──────────────────────────────────────────────
    # COMPOSITE SIGNALS
    # ──────────────────────────────────────────────

    def _add_composite_signals(self) -> "TechnicalAnalysisSkillV2":
        """Pre-compute composite signals used by the strategy engine"""
        # Trend direction: price above/below key MAs
        self.df["Above_MA20"] = (self.df["Close"] > self.df["MA20"]).astype(int)
        self.df["Above_MA50"] = (self.df["Close"] > self.df["MA50"]).astype(int)
        # Golden cross / death cross
        self.df["Golden_Cross"] = (
            (self.df["MA20"] > self.df["MA50"]) &
            (self.df["MA20"].shift(1) <= self.df["MA50"].shift(1))
        ).astype(int)
        self.df["Death_Cross"] = (
            (self.df["MA20"] < self.df["MA50"]) &
            (self.df["MA20"].shift(1) >= self.df["MA50"].shift(1))
        ).astype(int)
        # RSI zones
        self.df["RSI_Oversold"]   = (self.df["RSI"] < 30).astype(int)
        self.df["RSI_Overbought"] = (self.df["RSI"] > 70).astype(int)
        # BB squeeze (low volatility → potential breakout)
        self.df["BB_Squeeze"] = (self.df["BB_Width"] < self.df["BB_Width"].rolling(50, min_periods=1).quantile(0.2)).astype(int)
        # Price relative to VWAP
        self.df["Above_VWAP"] = (self.df["Close"] > self.df["VWAP"]).astype(int)
        return self

    # ──────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────

    def add_indicators(self) -> "TechnicalAnalysisSkillV2":
        """Run all indicators. Returns self for chaining."""
        (self
         ._add_moving_averages()
         ._add_macd()
         ._add_adx()
         ._add_rsi()
         ._add_stochastic()
         ._add_roc()
         ._add_bollinger_bands()
         ._add_atr()
         ._add_historical_volatility()
         ._add_obv()
         ._add_volume_indicators()
         ._add_vwap()
         ._add_composite_signals()
         )
        return self

    def dropna(self) -> "TechnicalAnalysisSkillV2":
        self.df = self.df.dropna()
        return self

    def copy(self) -> pd.DataFrame:
        return self.df.copy()

    @property
    def columns(self):
        return self.df.columns

    def __len__(self):
        return len(self.df)
