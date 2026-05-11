"""Platform-agnostic binary event market.

A `BinaryMarket` represents one YES/NO market on a CFTC-regulated venue
(Kalshi DCM) or a CFTC-licensed entity (Polymarket via QCEX). v0.1 targets
Kalshi because it's the only US-legal venue with a public demo API today
(2026-05-11). Polymarket port is v0.2 — same dataclass, different client.

Multi-outcome markets ("Which team wins?") are out of scope for v0.1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


Platform = Literal["kalshi", "polymarket"]
MarketStatus = Literal["open", "closed", "settled", "finalized"]


@dataclass
class PriceTick:
    """One (timestamp, yes-price) point from a price-history endpoint."""
    t: int          # unix seconds
    yes: float      # YES price in [0, 1]


@dataclass
class BinaryMarket:
    """One YES/NO market on Kalshi or Polymarket.

    `outcome` is the ground-truth resolution: 1 if YES resolved true,
    0 if NO resolved true, None if still open. We never derive this
    from price — it must come from the platform's settlement status.
    """
    # ── identity ─────────────────────────────────────────────
    platform: Platform
    market_id: str             # platform-canonical id (Kalshi ticker / Polymarket condition_id)
    ticker: str                # human-readable handle (same as market_id on Kalshi)
    question: str              # the resolution question, verbatim

    # ── classification ───────────────────────────────────────
    category: str = ""         # "politics" / "geopolitics" / "economics" / "sports" / "crypto"
    status: MarketStatus = "open"

    # ── lifecycle (ISO 8601 strings — convert from platform native shape) ──
    open_time: Optional[str] = None        # market opens (trading enabled)
    close_time: Optional[str] = None       # market closes (no more trading)
    expiration_time: Optional[str] = None  # expected settlement deadline
    settled_at: Optional[str] = None       # actual settlement timestamp

    # ── live state ───────────────────────────────────────────
    yes_price: Optional[float] = None      # current YES mid in [0, 1]
    yes_bid: Optional[float] = None
    yes_ask: Optional[float] = None
    volume: float = 0.0                    # all-time contracts traded (or $ depending on platform)
    open_interest: float = 0.0

    # ── resolution truth ─────────────────────────────────────
    # Set ONLY after status in {settled, finalized}. None = unresolved.
    outcome: Optional[int] = None          # 1 if YES won, 0 if NO won

    # ── price snapshot at "decision time" (e.g. T-24h before close) ──
    # Filled in by backtest harness; not from platform directly.
    price_at_decision: Optional[float] = None

    # ── extras ──────────────────────────────────────────────
    description: str = ""
    raw: dict = field(default_factory=dict)  # full platform payload for forensics

    # ── derived ─────────────────────────────────────────────
    @property
    def is_closed(self) -> bool:
        return self.status in ("closed", "settled", "finalized")

    @property
    def is_resolved(self) -> bool:
        return self.outcome is not None and self.status in ("settled", "finalized")

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "market_id": self.market_id,
            "ticker": self.ticker,
            "question": self.question,
            "category": self.category,
            "status": self.status,
            "open_time": self.open_time,
            "close_time": self.close_time,
            "expiration_time": self.expiration_time,
            "settled_at": self.settled_at,
            "yes_price": self.yes_price,
            "yes_bid": self.yes_bid,
            "yes_ask": self.yes_ask,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "outcome": self.outcome,
            "price_at_decision": self.price_at_decision,
            "description": self.description,
        }
