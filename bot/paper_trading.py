"""
bot/paper_trading.py
──────────────────────────────────────────────────────────────────
Paper trading tracker — logs hypothetical trades from signals and
tracks cumulative P&L without real money.

Uses the existing BehaviorMemory trade log for storage.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

_PAPER_FILE = Path(__file__).parent.parent / "memory_data" / "paper_trades.json"


@dataclass
class PaperTrade:
    timestamp: str
    ticker: str
    direction: str       # "LONG" | "SHORT"
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float
    source: str
    status: str = "OPEN"  # "OPEN" | "WIN" | "LOSS" | "BREAKEVEN" | "CANCELLED"
    exit_price: float = 0.0
    exit_time: str = ""
    pnl_pct: float = 0.0
    pnl_dollar: float = 0.0
    position_size: float = 0.0


class PaperTrader:
    """Manages a paper trading journal."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _PAPER_FILE
        self._trades: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._trades = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._trades = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._trades, f, indent=2, ensure_ascii=False)

    def open_trade(self, trade: PaperTrade) -> int:
        """Open a new paper trade. Returns index."""
        self._trades.append(asdict(trade))
        self._save()
        return len(self._trades) - 1

    def close_trade(self, index: int, exit_price: float,
                    outcome: str = "") -> Optional[dict]:
        """Close an open trade with exit price."""
        if index < 0 or index >= len(self._trades):
            return None
        t = self._trades[index]
        if t["status"] != "OPEN":
            return None

        t["exit_price"] = exit_price
        t["exit_time"] = datetime.now().isoformat()

        if t["direction"] == "LONG":
            t["pnl_pct"] = round((exit_price / t["entry_price"] - 1) * 100, 2)
        else:
            t["pnl_pct"] = round((t["entry_price"] / exit_price - 1) * 100, 2)

        t["pnl_dollar"] = round(t["pnl_pct"] / 100 * t["position_size"] * t["entry_price"], 2)

        if not outcome:
            outcome = "WIN" if t["pnl_pct"] > 0 else "LOSS" if t["pnl_pct"] < 0 else "BREAKEVEN"
        t["status"] = outcome

        self._save()
        return t

    def get_open_trades(self) -> list[dict]:
        return [t for t in self._trades if t["status"] == "OPEN"]

    def get_closed_trades(self) -> list[dict]:
        return [t for t in self._trades if t["status"] != "OPEN"]

    def get_all_trades(self) -> list[dict]:
        return list(self._trades)

    def get_stats(self) -> dict:
        """Compute paper trading performance metrics."""
        closed = self.get_closed_trades()
        if not closed:
            return {
                "total_trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "total_pnl_pct": 0.0,
                "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
                "best_trade": 0.0, "worst_trade": 0.0,
                "profit_factor": 0.0,
            }

        wins = [t for t in closed if t["pnl_pct"] > 0]
        losses = [t for t in closed if t["pnl_pct"] < 0]
        pnls = [t["pnl_pct"] for t in closed]

        total_win = sum(t["pnl_pct"] for t in wins) if wins else 0
        total_loss = abs(sum(t["pnl_pct"] for t in losses)) if losses else 0

        return {
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
            "total_pnl_pct": round(sum(pnls), 2),
            "avg_win_pct": round(total_win / len(wins), 2) if wins else 0,
            "avg_loss_pct": round(-total_loss / len(losses), 2) if losses else 0,
            "best_trade": round(max(pnls), 2) if pnls else 0,
            "worst_trade": round(min(pnls), 2) if pnls else 0,
            "profit_factor": round(total_win / total_loss, 2) if total_loss > 0 else 0,
        }
