"""
bot/arena.py
──────────────────────────────────────────────────────────────────────────────
Bot Arena: compare 3 preset bot configs on the same DecisionOutput.

Configs differ in aggressiveness, risk tolerance, and confidence thresholds.
Each receives the same base decision but applies different position sizing
and acceptance rules. Useful for seeing how conservative vs aggressive
setups would handle the same signal.
"""

from dataclasses import dataclass

from models.decision import DecisionOutput
from skills.risk_management import RiskManagementSkill, RiskParams, RiskOutput


BOT_CONFIGS: dict[str, dict] = {
    "Conservative": {
        "risk_pct":           0.005,  # 0.5% account risk per trade
        "max_trades_per_day": 3,
        "min_confidence":     70,     # only takes high-confidence signals
        "aggressiveness":     0.2,
        "description":        "Low risk. Only high-confidence setups. Small position sizes.",
    },
    "Moderate": {
        "risk_pct":           0.010,  # 1% account risk per trade
        "max_trades_per_day": 5,
        "min_confidence":     55,
        "aggressiveness":     0.5,
        "description":        "Balanced. Standard risk sizing. Accepts medium+ confidence.",
    },
    "Aggressive": {
        "risk_pct":           0.020,  # 2% account risk per trade
        "max_trades_per_day": 8,
        "min_confidence":     40,     # accepts lower-confidence signals
        "aggressiveness":     0.8,
        "description":        "High risk. Larger positions. Accepts most signals.",
    },
}


@dataclass
class BotArenaResult:
    name: str
    config: dict
    risk_output: RiskOutput
    approved: bool   # True if config accepts this signal
    reason: str      # approval/rejection explanation


class BotArena:
    """
    Run a single DecisionOutput through all BOT_CONFIGS and return
    one BotArenaResult per config.
    """

    def run(
        self,
        decision: DecisionOutput,
        entry_price: float,
        account_size: float,
        atr: float | None = None,
        trades_today: int = 0,
    ) -> list[BotArenaResult]:
        """
        Args:
            decision:     The shared DecisionOutput from scalp/predict analysis
            entry_price:  Current price (0 = unavailable)
            account_size: Total capital in dollars
            atr:          ATR value for stop-loss calculation (optional)
            trades_today: Trades already taken today (shared across configs)

        Returns:
            List of BotArenaResult, one per config (Conservative/Moderate/Aggressive)
        """
        results = []

        for name, config in BOT_CONFIGS.items():
            result = self._evaluate(
                name=name,
                config=config,
                decision=decision,
                entry_price=entry_price,
                account_size=account_size,
                atr=atr,
                trades_today=trades_today,
            )
            results.append(result)

        return results

    def _evaluate(
        self,
        name: str,
        config: dict,
        decision: DecisionOutput,
        entry_price: float,
        account_size: float,
        atr: float | None,
        trades_today: int,
    ) -> BotArenaResult:
        # Confidence gate: reject if signal confidence is below this config's minimum
        if decision.decision != "WAIT" and decision.confidence < config["min_confidence"]:
            rejected_risk = self._zero_risk(entry_price)
            return BotArenaResult(
                name=name,
                config=config,
                risk_output=rejected_risk,
                approved=False,
                reason=(
                    f"Confidence {decision.confidence:.0f}% below minimum "
                    f"{config['min_confidence']}% for {name} config"
                ),
            )

        # Delegate to RiskManagementSkill for position sizing + R:R check
        params = RiskParams(
            account_size=account_size,
            risk_pct=config["risk_pct"],
            entry_price=entry_price,
            atr=atr,
            max_trades_per_day=config["max_trades_per_day"],
        )
        risk_out = RiskManagementSkill().compute(
            decision=decision,
            params=params,
            trades_today=trades_today,
        )

        if risk_out.approved:
            reason = f"Signal accepted | {config['description']}"
        else:
            reason = risk_out.rejection_reason

        return BotArenaResult(
            name=name,
            config=config,
            risk_output=risk_out,
            approved=risk_out.approved,
            reason=reason,
        )

    def _zero_risk(self, entry_price: float) -> RiskOutput:
        return RiskOutput(
            position_size=0.0,
            position_value=0.0,
            stop_loss_price=entry_price,
            take_profit_price=entry_price,
            risk_amount=0.0,
            risk_reward_ratio=0.0,
            approved=False,
            rejection_reason="",
        )
