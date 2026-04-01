import yfinance as yf
from datetime import datetime


class NewsSkill:
    def __init__(self, ticker: str):
        self.ticker = ticker.strip().upper()

    def fetch_news(self, limit: int = 10):
        stock = yf.Ticker(self.ticker)

        try:
            raw_news = getattr(stock, "news", [])
        except Exception:
            raw_news = []

        normalized = []

        for item in raw_news[:limit]:
            title = item.get("title", "Untitled")
            publisher = item.get("publisher", "Unknown")
            link = item.get("link", "")
            summary = item.get("summary", "")
            provider_time = item.get("providerPublishTime")

            published = None
            if provider_time:
                try:
                    published = datetime.fromtimestamp(provider_time).isoformat()
                except Exception:
                    published = str(provider_time)

            normalized.append({
                "ticker": self.ticker,
                "title": title,
                "publisher": publisher,
                "published": published,
                "summary": summary if summary else title,
                "link": link
            })

        return normalized