from __future__ import annotations

import pandas as pd


def ma_crossover_signals(
    df: pd.DataFrame,
    short_window: int = 20,
    long_window: int = 50,
    price_col: str = "Close",
) -> pd.DataFrame:
    """
    Create moving-average crossover signals.
    signal = 1 when short MA > long MA, else 0
    """
    if price_col not in df.columns:
        raise ValueError(f"Missing column: {price_col}")

    if short_window >= long_window:
        raise ValueError("short_window must be smaller than long_window")

    data = df.copy()
    data["ma_short"] = data[price_col].rolling(short_window).mean()
    data["ma_long"] = data[price_col].rolling(long_window).mean()
    data["signal"] = (data["ma_short"] > data["ma_long"]).astype(int)

    return data