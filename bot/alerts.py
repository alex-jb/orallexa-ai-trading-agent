"""
bot/alerts.py
──────────────────────────────────────────────────────────────────
Price alert system — stores target prices and checks them against
live market data. Triggers notifications when conditions are met.

Usage:
    from bot.alerts import AlertManager, PriceAlert
    mgr = AlertManager()
    mgr.add(PriceAlert(ticker="NVDA", target=150.0, direction="above", note="breakout"))
    triggered = mgr.check_all()
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.logger import get_logger

logger = get_logger("alerts")

_ALERTS_FILE = Path(__file__).parent.parent / "memory_data" / "price_alerts.json"


@dataclass
class PriceAlert:
    ticker: str
    target: float
    direction: str          # "above" | "below"
    note: str = ""
    created: str = ""
    triggered: bool = False
    triggered_at: str = ""
    triggered_price: float = 0.0

    def __post_init__(self) -> None:
        if not self.created:
            self.created = datetime.now().isoformat()

    def check(self, current_price: float) -> bool:
        """Return True if alert condition is met."""
        if self.triggered:
            return False
        if self.direction == "above" and current_price >= self.target:
            return True
        if self.direction == "below" and current_price <= self.target:
            return True
        return False


class AlertManager:
    """Persistent price alert manager."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _ALERTS_FILE
        self._alerts: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._alerts = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._alerts = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._alerts, f, indent=2, ensure_ascii=False)

    def add(self, alert: PriceAlert) -> int:
        """Add an alert. Returns its index."""
        self._alerts.append(asdict(alert))
        self._save()
        logger.info("Alert added: %s %s $%.2f", alert.ticker, alert.direction, alert.target)
        return len(self._alerts) - 1

    def remove(self, index: int) -> None:
        """Remove alert by index."""
        if 0 <= index < len(self._alerts):
            self._alerts.pop(index)
            self._save()

    def get_active(self) -> list[dict]:
        """Return alerts that have not yet triggered."""
        return [a for a in self._alerts if not a.get("triggered", False)]

    def get_triggered(self) -> list[dict]:
        """Return triggered alerts."""
        return [a for a in self._alerts if a.get("triggered", False)]

    def get_all(self) -> list[dict]:
        return list(self._alerts)

    def check_all(self) -> list[dict]:
        """
        Check all active alerts against live prices.
        Returns list of newly triggered alerts.
        """
        active = [a for a in self._alerts if not a.get("triggered", False)]
        if not active:
            return []

        # Group by ticker to minimize API calls
        tickers = set(a["ticker"] for a in active)
        prices = _fetch_prices(tickers)

        newly_triggered = []
        for a in self._alerts:
            if a.get("triggered", False):
                continue
            price = prices.get(a["ticker"])
            if price is None:
                continue

            alert_obj = PriceAlert(**{k: v for k, v in a.items()
                                     if k in PriceAlert.__dataclass_fields__})
            if alert_obj.check(price):
                a["triggered"] = True
                a["triggered_at"] = datetime.now().isoformat()
                a["triggered_price"] = price
                newly_triggered.append(dict(a))
                logger.info("ALERT TRIGGERED: %s %s $%.2f (price=$%.2f)",
                            a["ticker"], a["direction"], a["target"], price)

        if newly_triggered:
            self._save()

        return newly_triggered

    def clear_triggered(self) -> int:
        """Remove all triggered alerts. Returns count removed."""
        before = len(self._alerts)
        self._alerts = [a for a in self._alerts if not a.get("triggered", False)]
        self._save()
        return before - len(self._alerts)


def _fetch_prices(tickers: set[str]) -> dict[str, float]:
    """Fetch latest prices for multiple tickers via yfinance."""
    prices = {}
    try:
        import yfinance as yf
        for tk in tickers:
            try:
                t = yf.Ticker(tk)
                hist = t.history(period="1d", interval="1m")
                if not hist.empty:
                    prices[tk] = float(hist["Close"].iloc[-1])
            except Exception:
                continue
    except ImportError:
        logger.warning("yfinance not available for alert price checking")
    return prices
