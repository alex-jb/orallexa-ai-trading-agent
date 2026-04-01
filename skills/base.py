class BaseFinancialSkill:
    def __init__(self, ticker: str):
        self.ticker = ticker

    def execute(self, *args, **kwargs):
        raise NotImplementedError("Subclasses must implement execute().")