"""Broker execution contract. All implementations in this repository are paper only."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class BrokerAdapter(ABC):
    """Common execution API used by the paper-trading routes and pilot."""

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether a paper broker connection is available."""

    @abstractmethod
    def get_account(self) -> Optional[dict]:
        """Return paper account information, or None if unavailable."""

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """Return open paper positions."""

    @abstractmethod
    def get_recent_orders(self, limit: int = 10) -> list[dict]:
        """Return recent paper orders."""

    @abstractmethod
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
        """Process a signal using the adapter's paper-only capability."""

    @abstractmethod
    def close_position(self, ticker: str) -> dict:
        """Close a paper position if the adapter supports execution."""

    @abstractmethod
    def close_all(self) -> dict:
        """Close paper positions if the adapter supports execution."""


def create_broker_adapter(broker: str = "alpaca") -> BrokerAdapter:
    """Create only an Alpaca paper executor or a Robinhood dry-run preview.

    Broker selection is explicit. No environment variable can enable live orders.
    """
    if broker == "alpaca":
        from bot.alpaca_executor import AlpacaExecutor
        return AlpacaExecutor()
    if broker == "robinhood_dry_run":
        from bot.robinhood_dry_run import RobinhoodDryRunAdapter
        return RobinhoodDryRunAdapter()
    raise ValueError(f"Unsupported paper broker adapter: {broker!r}")
