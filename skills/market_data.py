import yfinance as yf
import pandas as pd
from .base import BaseFinancialSkill


class MarketDataSkill(BaseFinancialSkill):
    def execute(self, period="6mo", interval="1d"):
        # Cache-aware path for daily bars when ORALLEXA_USE_CACHE=1.
        # Intraday intervals (5m, 1m, 15m, 1h, etc.) skip the cache —
        # those are real-time-sensitive and not worth a 24h freshness gate.
        df = None
        if interval == "1d":
            try:
                from engine.historical_cache import get_default_cache, cache_enabled
                if cache_enabled():
                    df = get_default_cache().get_prices_by_period(self.ticker, period=period)
            except Exception:
                df = None

        if df is None or df.empty:
            df = yf.download(
                self.ticker,
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
            )

        if df is None or df.empty:
            raise ValueError(f"No data returned for {self.ticker}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        keep_cols = [col for col in ["Open", "High", "Low", "Close", "Adj Close", "Volume"] if col in df.columns]
        df = df[keep_cols].copy()

        return df