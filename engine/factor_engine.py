"""
engine/factor_engine.py
────────────────────────────────────────────────────────────────────────────
Alpha factor library for Orallexa.
Inspired by ai_quant_trade egs_alpha patterns.

Factors are computed as cross-sectional or time-series signals
that can be used to rank stocks or as features for ML models.

Factor convention:
  Higher factor value = more bullish signal
  Lower factor value  = more bearish signal

Factors included:
  1. MomentumFactor     — price momentum at multiple horizons
  2. VolatilityFactor   — volatility-adjusted signals
  3. VolumeFactor       — volume trend and pressure
  4. TrendFactor        — MA alignment and ADX strength
  5. ReversalFactor     — short-term mean reversion
  6. CompositeAlpha     — weighted combination of all factors
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional


# ══════════════════════════════════════════════════════════════════════════
# BASE
# ══════════════════════════════════════════════════════════════════════════

class FactorEngine:
    """
    Computes and stores factor scores for a single ticker.
    Each factor returns a pd.Series aligned to df.index.

    Usage:
        fe = FactorEngine(df)
        factors = fe.compute_all()
        alpha   = fe.composite_alpha()
    """

    def __init__(self, df: pd.DataFrame):
        """
        df must have OHLCV columns + technical indicators from TechnicalAnalysisSkillV2.
        """
        self.df = df.copy()
        self._factors: Dict[str, pd.Series] = {}

    # ──────────────────────────────────────────────────────────
    # FACTOR 1 — MOMENTUM
    # ──────────────────────────────────────────────────────────

    def momentum_factor(
        self,
        short_period: int = 5,
        mid_period: int   = 20,
        long_period: int  = 60,
        weights: tuple    = (0.5, 0.3, 0.2),
    ) -> pd.Series:
        """
        Multi-horizon momentum.
        Combines short, medium, long term ROC.
        Higher = stronger upward momentum.
        """
        close = self.df["Close"]
        m_short = close.pct_change(short_period).fillna(0)
        m_mid   = close.pct_change(mid_period).fillna(0)
        m_long  = close.pct_change(long_period).fillna(0)

        factor = weights[0]*m_short + weights[1]*m_mid + weights[2]*m_long

        # Z-score normalisation (rolling 60-bar)
        factor = self._rolling_zscore(factor, 60)
        self._factors["momentum"] = factor
        return factor

    # ──────────────────────────────────────────────────────────
    # FACTOR 2 — VOLATILITY
    # ──────────────────────────────────────────────────────────

    def volatility_factor(self, period: int = 20) -> pd.Series:
        """
        Low-volatility factor (inverse of HV).
        Higher score = lower volatility = more attractive for risk-adjusted entry.
        """
        log_ret = np.log(self.df["Close"] / self.df["Close"].shift(1)).fillna(0)
        hv      = log_ret.rolling(window=period, min_periods=1).std() * np.sqrt(252)

        # Inverse: low volatility → high factor
        factor = -self._rolling_zscore(hv, 60)
        self._factors["volatility"] = factor
        return factor

    def atr_breakout_factor(self) -> pd.Series:
        """
        ATR-normalised price momentum. Measures recent move relative to typical range.
        High value = strong directional move relative to recent volatility.
        """
        if "ATR" not in self.df.columns:
            return pd.Series(0.0, index=self.df.index)

        close_change = self.df["Close"].diff(5).fillna(0)
        atr_norm     = close_change / (self.df["ATR"] * np.sqrt(5) + 1e-9)
        factor       = self._rolling_zscore(atr_norm, 60)
        self._factors["atr_breakout"] = factor
        return factor

    # ──────────────────────────────────────────────────────────
    # FACTOR 3 — VOLUME
    # ──────────────────────────────────────────────────────────

    def volume_factor(self, period: int = 20) -> pd.Series:
        """
        Volume pressure factor: rising price + rising volume = positive.
        Combines OBV trend and volume ratio.
        """
        volume = self.df["Volume"]
        close  = self.df["Close"]

        # Volume-weighted price change
        direction = np.sign(close.diff().fillna(0))
        obv       = (direction * volume).cumsum()
        obv_trend = obv.rolling(window=period, min_periods=1).mean()
        obv_signal= obv - obv_trend  # OBV above its own MA = accumulation

        # Volume ratio
        vol_ratio = volume / (volume.rolling(period, min_periods=1).mean() + 1e-9)
        vol_momentum = vol_ratio * direction  # positive = volume surge in trend direction

        factor = 0.6 * self._rolling_zscore(obv_signal, 60) + \
                 0.4 * self._rolling_zscore(vol_momentum, 60)
        self._factors["volume"] = factor
        return factor

    # ──────────────────────────────────────────────────────────
    # FACTOR 4 — TREND
    # ──────────────────────────────────────────────────────────

    def trend_factor(self) -> pd.Series:
        """
        Trend alignment factor.
        Counts how many MAs the price is above (5, 10, 20, 50).
        Weighted by ADX strength.
        """
        close = self.df["Close"]
        score = pd.Series(0.0, index=self.df.index)

        for ma_col, weight in [("MA5",0.15), ("MA10",0.2), ("MA20",0.3), ("MA50",0.35)]:
            if ma_col in self.df.columns:
                score += weight * (close > self.df[ma_col]).astype(float)

        # ADX amplification: stronger trend → higher weight
        if "ADX" in self.df.columns:
            adx_norm  = (self.df["ADX"] / 100).clip(0, 1)
            score     = score * (0.5 + adx_norm)  # amplify by trend strength

        factor = self._rolling_zscore(score, 60)
        self._factors["trend"] = factor
        return factor

    # ──────────────────────────────────────────────────────────
    # FACTOR 5 — REVERSAL
    # ──────────────────────────────────────────────────────────

    def reversal_factor(self, short_period: int = 5) -> pd.Series:
        """
        Short-term reversal factor.
        Recent losers tend to outperform over next few days (mean reversion).
        Negative of short-term momentum.
        """
        close  = self.df["Close"]
        recent = close.pct_change(short_period).fillna(0)
        factor = -self._rolling_zscore(recent, 60)  # inverse
        self._factors["reversal"] = factor
        return factor

    def rsi_reversal_factor(self) -> pd.Series:
        """RSI distance from 50 as a mean-reversion signal."""
        if "RSI" not in self.df.columns:
            return pd.Series(0.0, index=self.df.index)
        # RSI < 50 → positive signal (oversold tendency)
        factor = (50 - self.df["RSI"]) / 50
        factor = self._rolling_zscore(factor, 60)
        self._factors["rsi_reversal"] = factor
        return factor

    # ──────────────────────────────────────────────────────────
    # COMPOSITE ALPHA
    # ──────────────────────────────────────────────────────────

    def composite_alpha(
        self,
        weights: Optional[Dict[str, float]] = None,
    ) -> pd.Series:
        """
        Weighted combination of all computed factors.
        Call compute_all() first, or individual factor methods.

        Default weights optimised for trend-following regime.
        """
        if weights is None:
            weights = {
                "momentum":    0.35,
                "trend":       0.30,
                "volume":      0.20,
                "volatility":  0.10,
                "atr_breakout":0.05,
            }

        if not self._factors:
            self.compute_all()

        alpha = pd.Series(0.0, index=self.df.index)
        total_weight = 0.0

        for name, w in weights.items():
            if name in self._factors:
                alpha += w * self._factors[name].fillna(0)
                total_weight += w

        if total_weight > 0:
            alpha /= total_weight

        return self._rolling_zscore(alpha, 60)

    def compute_all(self) -> Dict[str, pd.Series]:
        """Compute all factors and return as dict."""
        self.momentum_factor()
        self.volatility_factor()
        self.atr_breakout_factor()
        self.volume_factor()
        self.trend_factor()
        self.reversal_factor()
        self.rsi_reversal_factor()
        return self._factors

    def factor_table(self) -> pd.DataFrame:
        """Return all factors as a DataFrame."""
        if not self._factors:
            self.compute_all()
        return pd.DataFrame(self._factors)

    # ──────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
        """Rolling z-score normalisation."""
        mean = series.rolling(window=window, min_periods=1).mean()
        std  = series.rolling(window=window, min_periods=1).std()
        return (series - mean) / (std + 1e-9)


# ══════════════════════════════════════════════════════════════════════════
# FACTOR-BASED SIGNAL GENERATOR
# ══════════════════════════════════════════════════════════════════════════

def factor_signal(
    df: pd.DataFrame,
    params: Dict,
) -> pd.Series:
    """
    Generate trading signal from composite alpha factor.
    Compatible with strategies.STRATEGY_REGISTRY interface.

    params:
        alpha_threshold (float): enter when alpha > threshold, default 0.5
        exit_threshold  (float): exit when alpha < threshold, default 0.0
        factor_weights  (dict):  custom factor weights, optional
    """
    entry_thresh = params.get("alpha_threshold", 0.5)
    exit_thresh  = params.get("exit_threshold",  0.0)
    fw           = params.get("factor_weights",  None)

    fe    = FactorEngine(df)
    alpha = fe.composite_alpha(weights=fw)

    in_position  = False
    signals_list = []

    for i in range(len(df)):
        a = alpha.iloc[i]
        if np.isnan(a):
            signals_list.append(1 if in_position else 0)
            continue

        if a > entry_thresh and not in_position:
            in_position = True
        elif a < exit_thresh and in_position:
            in_position = False

        signals_list.append(1 if in_position else 0)

    return pd.Series(signals_list, index=df.index)


# ══════════════════════════════════════════════════════════════════════════
# CROSS-TICKER RANKING (for portfolio selection)
# ══════════════════════════════════════════════════════════════════════════

def rank_tickers_by_alpha(
    ticker_dfs: Dict[str, pd.DataFrame],
    lookback_days: int = 20,
) -> pd.DataFrame:
    """
    Rank multiple tickers by their current composite alpha score.
    Used for portfolio allocation — replace simple Sharpe ranking.

    Returns DataFrame with ticker, alpha_score, momentum, trend, volume columns.
    """
    rows = []
    for ticker, df in ticker_dfs.items():
        if len(df) < lookback_days:
            continue
        recent = df.tail(lookback_days).copy()
        fe     = FactorEngine(recent)
        fe.compute_all()

        # Get latest factor values
        latest = {name: float(series.iloc[-1]) if len(series) > 0 else 0.0
                  for name, series in fe._factors.items()}
        alpha  = float(fe.composite_alpha().iloc[-1])

        rows.append({
            "ticker":        ticker,
            "alpha_score":   round(alpha, 3),
            "momentum":      round(latest.get("momentum", 0), 3),
            "trend":         round(latest.get("trend", 0), 3),
            "volume":        round(latest.get("volume", 0), 3),
            "volatility":    round(latest.get("volatility", 0), 3),
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("alpha_score", ascending=False).reset_index(drop=True)
