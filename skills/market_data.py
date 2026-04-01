import yfinance as yf
import pandas as pd
from .base import BaseFinancialSkill


class MarketDataSkill(BaseFinancialSkill):
    def execute(self, period="6mo", interval="1d"):
        df = yf.download(
            self.ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False
        )

        if df is None or df.empty:
            raise ValueError(f"No data returned for {self.ticker}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        keep_cols = [col for col in ["Open", "High", "Low", "Close", "Adj Close", "Volume"] if col in df.columns]
        df = df[keep_cols].copy()

        return df