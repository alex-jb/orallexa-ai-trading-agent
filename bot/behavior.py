"""
bot/behavior.py
──────────────────────────────────────────────────────────────────────────────
Discipline / behavior learning system.
Tracks trade outcomes and adaptively updates bot aggressiveness.

State is stored in bot/memory.json.
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime


MEMORY_PATH = os.path.join(os.path.dirname(__file__), "memory.json")

_DEFAULT_STATE = {
    "aggressiveness": 0.5,   # 0.0 = very conservative, 1.0 = aggressive
    "trades": [],
    "win_streak": 0,
    "loss_streak": 0,
    "trades_today": 0,
    "last_trade_date": None,
    "total_trades": 0,
    "total_wins": 0,
    "total_losses": 0,
}


@dataclass
class TradeRecord:
    timestamp: str
    ticker: str
    decision: str        # BUY / SELL / WAIT
    confidence: float
    risk_level: str
    source: str
    entry_price: float
    outcome: str         # "win" | "loss" | "breakeven" | "pending"
    pnl_pct: float       # actual % gain/loss (0.0 if pending)
    reflection: str = "" # AI-generated post-trade reflection


class BehaviorMemory:
    """
    Persistent trade memory with adaptive aggressiveness tuning.

    Usage:
        mem = BehaviorMemory()
        mem.record_trade(TradeRecord(..., outcome="pending", pnl_pct=0.0))
        mem.update_outcome(timestamp, "win", 0.025)
        aggressiveness = mem.get_aggressiveness()   # used by PredictionSkill
    """

    def __init__(self, memory_path: str = MEMORY_PATH):
        self.memory_path = memory_path
        self._data = self._load()

    # ──────────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Backfill any missing keys from the default
                for k, v in _DEFAULT_STATE.items():
                    data.setdefault(k, v)
                return data
            except (json.JSONDecodeError, OSError):
                pass
        return dict(_DEFAULT_STATE)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    # ──────────────────────────────────────────────────────────────────────
    # Trade recording
    # ──────────────────────────────────────────────────────────────────────

    def record_trade(self, record: TradeRecord) -> None:
        """Append a new trade (outcome may be 'pending')."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Reset daily count if new day
        if self._data.get("last_trade_date") != today:
            self._data["trades_today"] = 0
            self._data["last_trade_date"] = today

        self._data["trades"].append(asdict(record))
        self._data["total_trades"] = self._data.get("total_trades", 0) + 1
        self._data["trades_today"] = self._data.get("trades_today", 0) + 1
        self._save()

    def update_outcome(self, timestamp: str, outcome: str, pnl_pct: float) -> None:
        """Update a pending trade with its final outcome, then reflect."""
        for trade in self._data["trades"]:
            if trade.get("timestamp") == timestamp:
                trade["outcome"] = outcome
                trade["pnl_pct"] = pnl_pct
                break

        self._update_streaks(outcome)
        self._update_aggressiveness()
        self._save()

        # AI reflection on the completed trade (non-blocking)
        try:
            self.reflect_on_trade(timestamp)
        except Exception:
            pass

    def reflect_on_trade(self, timestamp: str) -> str:
        """
        Call Haiku to reflect on a completed trade.
        Stores the reflection text in the trade record and returns it.
        """
        trade = None
        for t in self._data["trades"]:
            if t.get("timestamp") == timestamp:
                trade = t
                break
        if not trade:
            return ""
        if trade.get("outcome") == "pending" or trade.get("reflection", "").strip():
            return trade.get("reflection", "")

        # Gather past reflections for this ticker for continuity
        ticker = trade.get("ticker", "")
        past = self.get_relevant_reflections(ticker, n=3)
        past_block = "\n---\n".join(past) if past else "No prior reflections."

        prompt = f"""You are a trading coach reviewing a completed trade.

Trade Details:
- Ticker: {ticker}
- Decision: {trade.get('decision')}
- Confidence: {trade.get('confidence')}%
- Risk Level: {trade.get('risk_level')}
- Entry Price: {trade.get('entry_price')}
- Outcome: {trade.get('outcome')}
- PnL: {trade.get('pnl_pct', 0):.2%}

Prior Reflections for {ticker}:
{past_block}

Provide a concise reflection (under 100 words):
1. What went right or wrong in this trade?
2. What pattern should I watch for next time?
3. One-line lesson learned."""

        try:
            from llm.claude_client import get_client, _extract_text, FAST_MODEL
            client = get_client()
            response = client.messages.create(
                model=FAST_MODEL,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            reflection = _extract_text(response)
            trade["reflection"] = reflection
            self._save()
            return reflection
        except Exception:
            return ""

    def get_relevant_reflections(self, ticker: str, n: int = 3) -> list:
        """Return the N most recent reflections for the given ticker."""
        ticker_trades = [
            t for t in reversed(self._data.get("trades", []))
            if t.get("ticker", "").upper() == ticker.upper()
            and t.get("reflection", "").strip()
        ]
        return [t["reflection"] for t in ticker_trades[:n]]

    # ──────────────────────────────────────────────────────────────────────
    # Adaptive logic
    # ──────────────────────────────────────────────────────────────────────

    def _update_streaks(self, outcome: str) -> None:
        if outcome == "win":
            self._data["total_wins"] = self._data.get("total_wins", 0) + 1
            self._data["win_streak"]  = self._data.get("win_streak", 0) + 1
            self._data["loss_streak"] = 0
        elif outcome == "loss":
            self._data["total_losses"] = self._data.get("total_losses", 0) + 1
            self._data["loss_streak"]  = self._data.get("loss_streak", 0) + 1
            self._data["win_streak"]   = 0

    def _update_aggressiveness(self) -> None:
        """
        Adaptive rules:
        - 3+ win streak  → +0.05 aggressiveness (max 0.90)
        - 2+ loss streak → -0.10 aggressiveness (min 0.20)
        - 5+ trades today → -0.05 overtrading penalty
        """
        agg = float(self._data.get("aggressiveness", 0.5))

        win_streak  = self._data.get("win_streak", 0)
        loss_streak = self._data.get("loss_streak", 0)
        trades_today = self._data.get("trades_today", 0)

        if win_streak >= 3:
            agg = min(0.90, agg + 0.05)
        if loss_streak >= 2:
            agg = max(0.20, agg - 0.10)
        if trades_today >= 5:
            agg = max(0.20, agg - 0.05)

        self._data["aggressiveness"] = round(agg, 3)

    # ──────────────────────────────────────────────────────────────────────
    # Getters
    # ──────────────────────────────────────────────────────────────────────

    def get_aggressiveness(self) -> float:
        return float(self._data.get("aggressiveness", 0.5))

    def get_trades_today(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        if self._data.get("last_trade_date") != today:
            return 0
        return int(self._data.get("trades_today", 0))

    def get_summary(self) -> dict:
        total = self._data.get("total_trades", 0)
        wins  = self._data.get("total_wins", 0)
        losses = self._data.get("total_losses", 0)
        win_rate = round(wins / total * 100, 1) if total > 0 else 0.0
        return {
            "aggressiveness":  self.get_aggressiveness(),
            "total_trades":    total,
            "wins":            wins,
            "losses":          losses,
            "win_rate_pct":    win_rate,
            "win_streak":      self._data.get("win_streak", 0),
            "loss_streak":     self._data.get("loss_streak", 0),
            "trades_today":    self.get_trades_today(),
        }

    def get_recent_trades(self, n: int = 10) -> list:
        return self._data.get("trades", [])[-n:]

    def detect_patterns(self) -> list:
        """
        Detect behavioral patterns based on trade history.
        Returns a list of human-readable warning strings.
        """
        patterns = []
        loss_streak  = self._data.get("loss_streak", 0)
        win_streak   = self._data.get("win_streak", 0)
        trades_today = self.get_trades_today()
        total        = self._data.get("total_trades", 0)
        wins         = self._data.get("total_wins", 0)
        win_rate     = (wins / total * 100) if total > 0 else 0.0

        if loss_streak >= 3:
            patterns.append(f"Loss streak ({loss_streak}) — consider pausing and reviewing")
        if loss_streak >= 2:
            patterns.append("2 consecutive losses — reduce position size")

        if trades_today >= 7:
            patterns.append(f"Overtrading: {trades_today} trades today — risk of emotional trading")
        elif trades_today >= 5:
            patterns.append(f"High activity: {trades_today} trades today")

        if win_streak >= 5:
            patterns.append(f"Hot streak ({win_streak} wins) — watch for overconfidence")

        if total >= 10 and win_rate < 35:
            patterns.append(f"Low win rate ({win_rate:.0f}%) — review entry criteria")

        # Detect recent loss cluster (last 5 trades)
        recent = self.get_recent_trades(5)
        if len(recent) >= 5:
            recent_losses = sum(1 for t in recent if t.get("outcome") == "loss")
            if recent_losses >= 4:
                patterns.append("4 of last 5 trades were losses — take a break")

        return patterns

    def get_behavior_insights(self) -> dict:
        """
        Full behavior summary for the right panel UI display.
        """
        summary  = self.get_summary()
        patterns = self.detect_patterns()
        recent   = self.get_recent_trades(10)

        # Win rate trend: last 10 trades
        if recent:
            wins_recent = sum(1 for t in recent if t.get("outcome") == "win")
            win_rate_recent = round(wins_recent / len(recent) * 100, 1)
        else:
            win_rate_recent = 0.0

        # Recommended aggressiveness adjustment
        agg = self.get_aggressiveness()
        if agg < 0.3:
            recommended = "Be patient — current conservative mode suits your recent results"
        elif agg > 0.75:
            recommended = "High aggressiveness — ensure setups meet minimum quality before entry"
        else:
            recommended = "Balanced approach — maintain current discipline"

        return {
            "aggressiveness":        agg,
            "win_rate_overall":      summary["win_rate_pct"],
            "win_rate_recent_10":    win_rate_recent,
            "win_streak":            summary["win_streak"],
            "loss_streak":           summary["loss_streak"],
            "trades_today":          summary["trades_today"],
            "total_trades":          summary["total_trades"],
            "patterns":              patterns,
            "recommended_adjustment": recommended,
        }
