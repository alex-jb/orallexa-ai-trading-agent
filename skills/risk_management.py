"""
skills/risk_management.py
──────────────────────────────────────────────────────────────────────────────
Risk management: position sizing, stop-loss, overtrading detection.
Stateless per call — trade state is owned by BehaviorMemory (bot/behavior.py).
"""

from dataclasses import dataclass
from models.decision import DecisionOutput


@dataclass
class RiskParams:
    account_size: float        # total capital in dollars
    risk_pct: float            # fraction to risk per trade (e.g. 0.01 = 1%)
    entry_price: float         # current/expected entry price
    atr: float | None = None   # ATR value for ATR-based stop (optional)
    max_trades_per_day: int = 5


@dataclass
class RiskOutput:
    position_size: float       # number of shares to trade
    position_value: float      # dollar value of position
    stop_loss_price: float
    take_profit_price: float
    risk_amount: float         # max dollar loss if stop hit
    risk_reward_ratio: float
    approved: bool             # False if overtrading or risk too high
    rejection_reason: str      # empty string if approved

    def to_dict(self) -> dict:
        return {
            "position_size":    round(self.position_size, 2),
            "position_value":   round(self.position_value, 2),
            "stop_loss_price":  round(self.stop_loss_price, 4),
            "take_profit_price": round(self.take_profit_price, 4),
            "risk_amount":      round(self.risk_amount, 2),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "approved":         self.approved,
            "rejection_reason": self.rejection_reason,
        }


class RiskManagementSkill:
    """
    Computes position sizing and stop-loss given a DecisionOutput + RiskParams.
    Call compute() once per trade decision.
    """

    # Risk/reward targets per risk level
    _STOP_PCT   = {"LOW": 0.015, "MEDIUM": 0.025, "HIGH": 0.040}
    _TARGET_PCT = {"LOW": 0.030, "MEDIUM": 0.050, "HIGH": 0.080}

    def compute(
        self,
        decision: DecisionOutput,
        params: RiskParams,
        trades_today: int = 0,
    ) -> RiskOutput:
        # Overtrading guard
        if trades_today >= params.max_trades_per_day:
            return self._rejected(
                params,
                f"Max trades/day reached ({trades_today}/{params.max_trades_per_day})",
            )

        # Only size into BUY or SELL, not WAIT
        if decision.decision == "WAIT":
            return self._rejected(params, "Decision is WAIT — no position to size")

        entry = params.entry_price
        risk_level = decision.risk_level

        # Stop-loss: use ATR if available, else fixed percentage
        if params.atr is not None and params.atr > 0:
            stop_distance = params.atr * 1.5
            stop_loss = entry - stop_distance if decision.decision == "BUY" else entry + stop_distance
        else:
            stop_pct  = self._STOP_PCT[risk_level]
            stop_loss = entry * (1 - stop_pct) if decision.decision == "BUY" else entry * (1 + stop_pct)

        stop_distance = abs(entry - stop_loss)

        # Take-profit
        tp_pct = self._TARGET_PCT[risk_level]
        take_profit = (
            entry * (1 + tp_pct) if decision.decision == "BUY"
            else entry * (1 - tp_pct)
        )

        # Position sizing: risk a fixed dollar amount
        risk_dollars = params.account_size * params.risk_pct
        if stop_distance < 1e-6:
            return self._rejected(params, "Stop distance too small to size position safely")

        position_size  = risk_dollars / stop_distance
        position_value = position_size * entry

        # Hard cap: don't exceed 20% of account in a single position
        max_value = params.account_size * 0.20
        if position_value > max_value:
            position_size  = max_value / entry
            position_value = max_value

        risk_reward = abs(take_profit - entry) / stop_distance if stop_distance > 0 else 0.0

        # Reject if risk/reward is poor (< 1.5:1)
        if risk_reward < 1.5:
            return self._rejected(
                params,
                f"Risk/reward ratio {risk_reward:.2f} is below minimum 1.5:1",
            )

        return RiskOutput(
            position_size=round(position_size, 2),
            position_value=round(position_value, 2),
            stop_loss_price=round(stop_loss, 4),
            take_profit_price=round(take_profit, 4),
            risk_amount=round(risk_dollars, 2),
            risk_reward_ratio=round(risk_reward, 2),
            approved=True,
            rejection_reason="",
        )

    def _rejected(self, params: RiskParams, reason: str) -> RiskOutput:
        entry = params.entry_price
        return RiskOutput(
            position_size=0.0,
            position_value=0.0,
            stop_loss_price=entry,
            take_profit_price=entry,
            risk_amount=0.0,
            risk_reward_ratio=0.0,
            approved=False,
            rejection_reason=reason,
        )
