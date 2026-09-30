"""Offline Robinhood execution preview; deliberately contains no broker client."""
from __future__ import annotations

from typing import Optional

from bot.broker_adapter import BrokerAdapter


class RobinhoodDryRunAdapter(BrokerAdapter):
    """Preview only. It never authenticates, fetches positions, or submits orders."""

    @property
    def connected(self) -> bool:
        return False

    def get_account(self) -> Optional[dict]:
        return None

    def get_positions(self) -> list[dict]:
        return []

    def get_recent_orders(self, limit: int = 10) -> list[dict]:
        return []

    def execute_signal(
        self,
        ticker: str,
        decision: str,
        confidence: float = 50.0,
        entry_price: float = 0.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        position_pct: float = 5.0,
    ) -> dict:
        return {
            "status": "dry_run",
            "broker": "robinhood",
            "order_submitted": False,
            "bracket_supported": False,
            "reason": "Robinhood adapter is an offline preview only",
            "ticker": ticker,
            "decision": decision,
            "confidence": confidence,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "position_pct": position_pct,
        }

    def close_position(self, ticker: str) -> dict:
        return {"status": "dry_run", "broker": "robinhood", "order_submitted": False, "ticker": ticker}

    def close_all(self) -> dict:
        return {"status": "dry_run", "broker": "robinhood", "order_submitted": False}
