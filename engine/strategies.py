"""
engine/strategies.py
────────────────────────────────────────────────────────────────────────────
Multi-strategy library for Orallexa.
Inspired by ai_quant_trade vanilla and alpha strategy patterns.

Each strategy is a pure function:
    strategy_fn(df, params) -> pd.Series of signals {-1, 0, 1}

Signal convention:
    +1  = long / enter
     0  = hold / flat
    -1  = exit / avoid

Strategies included:
    1. double_ma          — Double Moving Average crossover (ai_quant_trade classic)
    2. macd_crossover     — MACD line crosses signal line
    3. bollinger_breakout — Price breaks out of Bollinger Band squeeze
    4. rsi_reversal       — RSI oversold/overbought mean-reversion
    5. trend_momentum     — Combined MA trend + MACD momentum + Volume confirmation
    6. dual_thrust        — Opening range breakout (high-frequency classic)
    7. alpha_combo        — Multi-factor composite signal
"""

import numpy as np
import pandas as pd
from typing import Dict, Any


# ══════════════════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════════════════

def _check_columns(df: pd.DataFrame, required: list, strategy: str):
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"[{strategy}] Missing columns: {missing}. Run TechnicalAnalysisSkillV2 first.")


def _apply_position_rules(signal: pd.Series, max_hold: int = None) -> pd.Series:
    """Optional: cap maximum holding period to force position turnover."""
    if max_hold is None:
        return signal
    result = signal.copy()
    hold_count = 0
    for i in range(len(result)):
        if result.iloc[i] == 1:
            hold_count += 1
            if hold_count > max_hold:
                result.iloc[i] = 0
        else:
            hold_count = 0
    return result


# ══════════════════════════════════════════════════════════════════════════
# STRATEGY 1 — Double Moving Average (from ai_quant_trade)
# ══════════════════════════════════════════════════════════════════════════

def double_ma(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Classic double moving average crossover.
    Buy when fast MA crosses above slow MA.
    Sell when fast MA crosses below slow MA.

    params:
        fast_period (int): fast MA window, default 20
        slow_period (int): slow MA window, default 50
        use_volume  (bool): require volume confirmation, default False
    """
    fast = params.get("fast_period", 20)
    slow = params.get("slow_period", 50)
    use_vol = params.get("use_volume", False)

    fast_ma = df["Close"].rolling(window=fast, min_periods=1).mean()
    slow_ma = df["Close"].rolling(window=slow, min_periods=1).mean()

    signal = pd.Series(0, index=df.index)

    # Long when fast crosses above slow
    cross_up   = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))
    cross_down = (fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1))

    in_position = False
    signals_list = []
    for i in range(len(df)):
        if cross_up.iloc[i]:
            vol_ok = (not use_vol) or (df["Volume_Ratio"].iloc[i] > 1.2 if "Volume_Ratio" in df.columns else True)
            in_position = vol_ok
        elif cross_down.iloc[i]:
            in_position = False
        signals_list.append(1 if in_position else 0)

    return pd.Series(signals_list, index=df.index)


# ══════════════════════════════════════════════════════════════════════════
# STRATEGY 2 — MACD Crossover
# ══════════════════════════════════════════════════════════════════════════

def macd_crossover(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Trade on MACD line crossing the signal line.
    Optional: require MACD histogram to be positive/negative for N bars.

    params:
        confirm_bars (int): bars MACD must stay crossed, default 1
        use_trend_filter (bool): only long above MA50, default True
        hist_threshold (float): minimum histogram value, default 0
    """
    _check_columns(df, ["MACD", "MACD_Signal", "MACD_Hist"], "macd_crossover")

    confirm    = params.get("confirm_bars", 1)
    use_trend  = params.get("use_trend_filter", True)
    hist_thresh= params.get("hist_threshold", 0.0)

    in_position = False
    signals_list = []

    for i in range(len(df)):
        macd_val   = df["MACD"].iloc[i]
        signal_val = df["MACD_Signal"].iloc[i]
        hist_val   = df["MACD_Hist"].iloc[i]

        # Trend filter: only long when above MA50
        trend_ok = True
        if use_trend and "MA50" in df.columns:
            trend_ok = df["Close"].iloc[i] > df["MA50"].iloc[i]

        if macd_val > signal_val and hist_val > hist_thresh and trend_ok:
            in_position = True
        elif macd_val < signal_val:
            in_position = False

        signals_list.append(1 if in_position else 0)

    return pd.Series(signals_list, index=df.index)


# ══════════════════════════════════════════════════════════════════════════
# STRATEGY 3 — Bollinger Band Breakout
# ══════════════════════════════════════════════════════════════════════════

def bollinger_breakout(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Enter long when price breaks above upper Bollinger Band after a squeeze.
    Exit when price crosses back below middle band.

    params:
        require_squeeze (bool): only enter after BB squeeze, default True
        exit_at_upper   (bool): exit when price reaches upper band, default False
        rsi_filter_max  (int):  don't enter if RSI > this, default 75
    """
    _check_columns(df, ["BB_Upper", "BB_Lower", "BB_Mid", "BB_Pct"], "bollinger_breakout")

    req_squeeze   = params.get("require_squeeze", True)
    rsi_max       = params.get("rsi_filter_max", 75)

    in_position = False
    signals_list = []

    for i in range(len(df)):
        close     = df["Close"].iloc[i]
        bb_upper  = df["BB_Upper"].iloc[i]
        bb_mid    = df["BB_Mid"].iloc[i]
        bb_pct    = df["BB_Pct"].iloc[i]
        squeeze   = df["BB_Squeeze"].iloc[i] if "BB_Squeeze" in df.columns else 0
        rsi       = df["RSI"].iloc[i] if "RSI" in df.columns else 50

        # Entry: close > upper band, after squeeze (if required), RSI not overbought
        entry_ok = (close > bb_upper) and (rsi < rsi_max)
        if req_squeeze:
            # Look back 5 bars for recent squeeze
            start = max(0, i - 5)
            recent_squeeze = df["BB_Squeeze"].iloc[start:i].sum() if "BB_Squeeze" in df.columns else 1
            entry_ok = entry_ok and (recent_squeeze > 0)

        if entry_ok and not in_position:
            in_position = True
        elif in_position and close < bb_mid:
            in_position = False

        signals_list.append(1 if in_position else 0)

    return pd.Series(signals_list, index=df.index)


# ══════════════════════════════════════════════════════════════════════════
# STRATEGY 4 — RSI Reversal (Mean Reversion)
# ══════════════════════════════════════════════════════════════════════════

def rsi_reversal(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Mean reversion: buy oversold RSI, sell overbought.
    Works best in range-bound markets.

    params:
        oversold  (int): RSI level to buy, default 30
        overbought(int): RSI level to sell, default 70
        exit_rsi  (int): RSI level to exit long, default 50
        use_adx_filter (bool): only trade when ADX < 25 (not trending), default True
    """
    _check_columns(df, ["RSI"], "rsi_reversal")

    oversold   = params.get("oversold", 30)
    overbought = params.get("overbought", 70)
    exit_rsi   = params.get("exit_rsi", 55)
    adx_filter = params.get("use_adx_filter", True)

    in_position = False
    signals_list = []

    for i in range(len(df)):
        rsi = df["RSI"].iloc[i]
        adx = df["ADX"].iloc[i] if "ADX" in df.columns else 20

        # ADX filter: only trade mean-reversion when market isn't strongly trending
        range_market = (not adx_filter) or (adx < 25)

        if rsi < oversold and range_market and not in_position:
            in_position = True
        elif in_position and (rsi > exit_rsi or rsi > overbought):
            in_position = False

        signals_list.append(1 if in_position else 0)

    return pd.Series(signals_list, index=df.index)


# ══════════════════════════════════════════════════════════════════════════
# STRATEGY 5 — Trend + Momentum Combo (Orallexa Enhanced)
# ══════════════════════════════════════════════════════════════════════════

def trend_momentum(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Multi-signal trend following:
      - Price above MA20 and MA50 (trend confirmed)
      - MACD histogram positive (momentum)
      - RSI in healthy zone (not overbought)
      - Optional: volume confirmation

    This is the enhanced version of Orallexa's original strategy.

    params:
        rsi_min  (int): minimum RSI, default 40
        rsi_max  (int): maximum RSI, default 70
        use_macd (bool): require positive MACD hist, default True
        use_volume (bool): require volume > MA, default True
        stop_loss (float): trailing stop %, default 0.05
    """
    rsi_min    = params.get("rsi_min", 40)
    rsi_max    = params.get("rsi_max", 70)
    use_macd   = params.get("use_macd", True)
    use_volume = params.get("use_volume", True)
    stop_loss  = params.get("stop_loss", 0.05)

    in_position  = False
    entry_price  = 0.0
    signals_list = []

    for i in range(len(df)):
        close = df["Close"].iloc[i]
        rsi   = df["RSI"].iloc[i] if "RSI" in df.columns else 50

        # Trend: above both MAs
        above_ma20 = close > df["MA20"].iloc[i] if "MA20" in df.columns else True
        above_ma50 = close > df["MA50"].iloc[i] if "MA50" in df.columns else True
        trend_ok   = above_ma20 and above_ma50

        # Momentum: MACD positive
        macd_ok = True
        if use_macd and "MACD_Hist" in df.columns:
            macd_ok = df["MACD_Hist"].iloc[i] > 0

        # Volume
        vol_ok = True
        if use_volume and "Volume_Ratio" in df.columns:
            vol_ok = df["Volume_Ratio"].iloc[i] > 0.8

        # RSI zone
        rsi_ok = rsi_min < rsi < rsi_max

        # Stop loss
        stop_hit = in_position and (close < entry_price * (1 - stop_loss))

        if stop_hit:
            in_position = False
        elif trend_ok and macd_ok and vol_ok and rsi_ok and not in_position:
            in_position = True
            entry_price = close
        elif in_position and not trend_ok:
            in_position = False

        signals_list.append(1 if in_position else 0)

    return pd.Series(signals_list, index=df.index)


# ══════════════════════════════════════════════════════════════════════════
# STRATEGY 6 — Alpha Combo (Factor-Based)
# ══════════════════════════════════════════════════════════════════════════

def alpha_combo(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Multi-factor alpha signal combining:
      - Momentum factor (ROC)
      - Trend factor (above VWAP)
      - Volatility factor (ATR-normalized position sizing hint)
      - Volume factor (OBV trend)

    Each factor contributes a score. Enter when composite score >= threshold.

    params:
        score_threshold (float): minimum score to enter, default 3.0
        momentum_period (int): ROC period for momentum, default 10
    """
    threshold = params.get("score_threshold", 3.0)

    in_position = False
    signals_list = []

    for i in range(len(df)):
        score = 0.0
        close = df["Close"].iloc[i]

        # Factor 1: Momentum (ROC > 0)
        if "ROC" in df.columns:
            score += 1.0 if df["ROC"].iloc[i] > 0 else 0.0

        # Factor 2: Trend (above MA20 and MA50)
        if "MA20" in df.columns and "MA50" in df.columns:
            score += 1.0 if (close > df["MA20"].iloc[i]) else 0.0
            score += 1.0 if (close > df["MA50"].iloc[i]) else 0.0

        # Factor 3: Volume (OBV rising)
        if "OBV" in df.columns and i >= 5:
            obv_rising = df["OBV"].iloc[i] > df["OBV"].iloc[i-5]
            score += 1.0 if obv_rising else 0.0

        # Factor 4: Price above VWAP
        if "VWAP" in df.columns:
            score += 1.0 if close > df["VWAP"].iloc[i] else 0.0

        # Factor 5: MACD positive
        if "MACD_Hist" in df.columns:
            score += 1.0 if df["MACD_Hist"].iloc[i] > 0 else 0.0

        # Factor 6: RSI healthy
        if "RSI" in df.columns:
            rsi = df["RSI"].iloc[i]
            score += 1.0 if (40 < rsi < 65) else 0.0

        if score >= threshold and not in_position:
            in_position = True
        elif score < (threshold - 1.5) and in_position:
            in_position = False

        signals_list.append(1 if in_position else 0)

    return pd.Series(signals_list, index=df.index)


# ══════════════════════════════════════════════════════════════════════════
# STRATEGY 7 — Dual Thrust (Opening Range Breakout)
# ══════════════════════════════════════════════════════════════════════════

def dual_thrust(df: pd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """
    Opening range breakout strategy (high-frequency classic).

    Computes an upper/lower trigger from the previous N days' range,
    then enters long when price breaks above the upper trigger.

    params:
        lookback (int): days to compute range, default 4
        k_up (float): upper trigger multiplier, default 0.5
        k_down (float): lower trigger multiplier, default 0.5
    """
    lookback = params.get("lookback", 4)
    k_up = params.get("k_up", 0.5)
    k_down = params.get("k_down", 0.5)

    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    open_price = df["Open"] if "Open" in df.columns else close

    # Rolling range components
    hh = high.rolling(window=lookback, min_periods=1).max()   # Highest high
    lc = close.rolling(window=lookback, min_periods=1).min()   # Lowest close
    hc = close.rolling(window=lookback, min_periods=1).max()   # Highest close
    ll = low.rolling(window=lookback, min_periods=1).min()     # Lowest low

    range_val = np.maximum(hh - lc, hc - ll)

    upper_trigger = open_price + k_up * range_val.shift(1)
    lower_trigger = open_price - k_down * range_val.shift(1)

    in_position = False
    signals_list = []
    for i in range(len(df)):
        if pd.isna(upper_trigger.iloc[i]) or pd.isna(lower_trigger.iloc[i]):
            signals_list.append(0)
            continue

        if close.iloc[i] > upper_trigger.iloc[i] and not in_position:
            in_position = True
        elif close.iloc[i] < lower_trigger.iloc[i] and in_position:
            in_position = False

        signals_list.append(1 if in_position else 0)

    return pd.Series(signals_list, index=df.index)


# ══════════════════════════════════════════════════════════════════════════
# STRATEGY REGISTRY
# ══════════════════════════════════════════════════════════════════════════

STRATEGY_REGISTRY = {
    "double_ma":          double_ma,
    "macd_crossover":     macd_crossover,
    "bollinger_breakout": bollinger_breakout,
    "rsi_reversal":       rsi_reversal,
    "trend_momentum":     trend_momentum,
    "alpha_combo":        alpha_combo,
    "dual_thrust":        dual_thrust,
}

STRATEGY_DEFAULT_PARAMS = {
    "double_ma": {
        "fast_period": 20, "slow_period": 50, "use_volume": False
    },
    "macd_crossover": {
        "confirm_bars": 1, "use_trend_filter": True, "hist_threshold": 0.0
    },
    "bollinger_breakout": {
        "require_squeeze": True, "rsi_filter_max": 75
    },
    "rsi_reversal": {
        "oversold": 30, "overbought": 70, "exit_rsi": 55, "use_adx_filter": True
    },
    "trend_momentum": {
        "rsi_min": 40, "rsi_max": 70, "use_macd": True,
        "use_volume": True, "stop_loss": 0.05
    },
    "alpha_combo": {
        "score_threshold": 3.0, "momentum_period": 10
    },
    "dual_thrust": {
        "lookback": 4, "k_up": 0.5, "k_down": 0.5
    },
}

STRATEGY_DESCRIPTIONS = {
    "double_ma":          "Double Moving Average crossover — classic trend following",
    "macd_crossover":     "MACD line crosses signal line — momentum trend entry",
    "bollinger_breakout": "Price breaks out of Bollinger Band squeeze — volatility breakout",
    "rsi_reversal":       "RSI oversold/overbought — mean reversion in range markets",
    "trend_momentum":     "MA trend + MACD momentum + Volume — Orallexa enhanced strategy",
    "alpha_combo":        "Multi-factor alpha composite — 6 independent signals combined",
    "dual_thrust":        "Opening range breakout — high-frequency classic using N-day range triggers",
}


def get_strategy(name: str):
    """Return strategy function by name."""
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy '{name}'. Available: {list(STRATEGY_REGISTRY.keys())}")
    return STRATEGY_REGISTRY[name]


def get_default_params(name: str) -> Dict[str, Any]:
    return STRATEGY_DEFAULT_PARAMS.get(name, {})
