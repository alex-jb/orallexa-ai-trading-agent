class TechnicalAnalysisSkill:
    def __init__(self, df):
        self.df = df.copy()

    def add_indicators(self):
        close_col = "Close" if "Close" in self.df.columns else "Adj Close"

        self.df["MA20"] = self.df[close_col].rolling(20).mean()
        self.df["MA50"] = self.df[close_col].rolling(50).mean()

        delta = self.df[close_col].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        self.df["RSI"] = 100 - (100 / (1 + rs))

        return self.df