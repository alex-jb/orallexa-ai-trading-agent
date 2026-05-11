"""Position sizing for binary YES/NO markets.

We use the Kelly formula for binary outcomes, then take a fraction of it
("quarter-Kelly") because:

1. Full Kelly is variance-optimal but assumes you know `p` perfectly. We
   don't — our p_yes comes from an LLM debate that may be miscalibrated.
2. Quarter-Kelly historically captures ~75% of Kelly's growth at <25% of
   the drawdown. Strong literature backing (Thorp, MacLean).
3. We further cap by `max_position_pct` (default 5% of bankroll) so a
   single LLM hallucination can't blow up the account.

Daily loss circuit breaker:
- If cumulative PnL today is below `-daily_loss_pct` * bankroll, the
  queue.py writer flags every entry as PAUSED until tomorrow.

We do NOT auto-disable real trading from this module — that's the human's
job. We just refuse to suggest a position size > 0 when the breaker is
tripped. The writer surfaces the reason in `sizing_notes`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SizingConfig:
    bankroll_usd: float = 300.0          # starting bankroll
    kelly_fraction: float = 0.25         # quarter-Kelly
    max_position_pct: float = 0.05       # 5% bankroll = $15 on $300
    min_edge: float = 0.05               # below 5pp edge, don't trade
    min_position_usd: float = 1.0        # don't bother with sub-dollar bets
    daily_loss_pct: float = 0.10         # -10% bankroll triggers daily pause
    consecutive_loss_days_pause: int = 3 # 3 down days → manual review

    def max_position_usd(self) -> float:
        return self.bankroll_usd * self.max_position_pct


@dataclass
class SizingResult:
    """Output of one sizing call."""
    position_usd: float
    side: str                 # "YES" or "NO" or ""
    kelly_full: float         # uncapped Kelly fraction in [0, 1]
    kelly_quarter: float
    capped_at_max: bool
    skip_reason: Optional[str] = None
    notes: str = ""

    @property
    def skipped(self) -> bool:
        return self.position_usd <= 0.0 or bool(self.skip_reason)


def _kelly_binary(p: float, b: float) -> float:
    """Kelly fraction for a binary bet at decimal odds `b` (net win per $1
    risked) with success probability `p`. Negative → no bet.

    Formula: f* = (p*(b+1) - 1) / b = (b*p - q) / b where q = 1-p.
    """
    if b <= 0:
        return 0.0
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, f)


def size_position(
    p_yes: float,
    market_price: float,
    config: SizingConfig,
    *,
    pnl_today_usd: float = 0.0,
) -> SizingResult:
    """Compute position size for one binary market.

    Strategy:
    - If market_price < p_yes (we think YES is underpriced), bet YES.
      Net odds b = (1 - market_price) / market_price.
    - If market_price > p_yes (we think YES is overpriced, i.e. NO is
      underpriced), bet NO at no_price = 1 - market_price. Net odds
      b = (1 - no_price) / no_price = market_price / (1 - market_price).
    - If |edge| < min_edge, skip.
    - If daily-loss circuit breaker tripped, skip with reason.
    """
    # Daily circuit breaker
    breaker_threshold = -config.daily_loss_pct * config.bankroll_usd
    if pnl_today_usd <= breaker_threshold:
        return SizingResult(
            position_usd=0.0,
            side="",
            kelly_full=0.0,
            kelly_quarter=0.0,
            capped_at_max=False,
            skip_reason="DAILY_LOSS_BREAKER_TRIPPED",
            notes=(
                f"PnL today ${pnl_today_usd:.2f} ≤ breaker "
                f"${breaker_threshold:.2f}; queue paused until tomorrow."
            ),
        )

    # Clamp inputs
    p_yes = max(0.001, min(0.999, p_yes))
    market_price = max(0.001, min(0.999, market_price))
    edge = p_yes - market_price

    if abs(edge) < config.min_edge:
        return SizingResult(
            position_usd=0.0,
            side="",
            kelly_full=0.0,
            kelly_quarter=0.0,
            capped_at_max=False,
            skip_reason="EDGE_TOO_SMALL",
            notes=(
                f"|edge|={abs(edge):.3f} < min_edge={config.min_edge:.3f}"
            ),
        )

    if edge > 0:
        # Bet YES. Buying YES at market_price, payout 1.0 if YES wins.
        side = "YES"
        p_win = p_yes
        b = (1.0 - market_price) / market_price
    else:
        # Bet NO. Buying NO at no_price = 1 - market_price.
        side = "NO"
        p_win = 1.0 - p_yes
        no_price = 1.0 - market_price
        b = (1.0 - no_price) / no_price

    k_full = _kelly_binary(p_win, b)
    k_quarter = k_full * config.kelly_fraction
    raw_usd = k_quarter * config.bankroll_usd
    cap_usd = config.max_position_usd()
    position = min(raw_usd, cap_usd)
    capped = raw_usd > cap_usd

    if position < config.min_position_usd:
        return SizingResult(
            position_usd=0.0,
            side=side,
            kelly_full=k_full,
            kelly_quarter=k_quarter,
            capped_at_max=False,
            skip_reason="POSITION_TOO_SMALL",
            notes=(
                f"raw Kelly suggests ${raw_usd:.2f} which is below the "
                f"${config.min_position_usd:.2f} floor."
            ),
        )

    return SizingResult(
        position_usd=round(position, 2),
        side=side,
        kelly_full=k_full,
        kelly_quarter=k_quarter,
        capped_at_max=capped,
        skip_reason=None,
        notes=(
            f"quarter-Kelly = {k_quarter:.3f} × ${config.bankroll_usd:.0f} "
            f"= ${raw_usd:.2f}"
            + (f"  (capped at ${cap_usd:.2f})" if capped else "")
        ),
    )
