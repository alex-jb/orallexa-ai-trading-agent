"""
engine/kelly_sizing.py
──────────────────────────────────────────────────────────────────
Kelly-criterion-based position sizing for Orallexa.

Ships 2026-07-02 Tier-2 upgrade #11 from the deep-research roadmap.

Why
---
Current sizing (trade_intel.py:setup_to_sizing_notional) uses fixed
buckets: Full = 25× risk_per_trade capped at 20% account, Half = 15×
capped at 10%, Short-half = 12× capped at 8%. Buckets don't adapt to
edge magnitude — a 2% mispricing gets the same notional as a 20%
mispricing on the same setup.

Roadmap finding: "paper -$1015 partly because of fixed-bucket sizing.
Half-Kelly is the professional-trader consensus default." (Ref:
wdm0006/keeks, Robot Wealth 2026, Ed Miller "Logic of Sports Betting").

This module ships the Kelly primitives Alex can layer on top of the
fixed-bucket setup logic. Vendored (not `pip install`) per the
we-dont-do rule against dependency ballooning.

Contract
--------
Pure functions, no state, no LLM. Take win_prob + win_pct + loss_pct
+ account. Return a fraction (0-1) of the account to bet or a dollar
notional. Never > 1, never < 0. Never NaN.

Half-Kelly is the default fraction because full Kelly is famously
too aggressive under uncertainty about the true win probability —
if you're off by even 5% on p_win, full Kelly can compound to ruin
inside a few dozen trades. Half-Kelly gives you most of the growth
rate with dramatically lower ruin risk. This is why every serious
professional trader is at ≤ 0.5f* not 1.0f*.

Ref: Thorp (1997) "The Kelly Criterion in Blackjack Sports Betting
and the Stock Market", Ed Miller (2018) "The Logic of Sports Betting"
Ch. 12, Kris Longmore (Robot Wealth 2026) — all converge on 0.5f*.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

# Professional-trader consensus default. Full Kelly (1.0) is
# mathematically optimal ONLY when p_win is known exactly; under
# uncertainty it courts ruin. 0.5f* gives ~75% of the growth rate
# at dramatically lower drawdown risk.
DEFAULT_KELLY_FRACTION = 0.5

# Absolute upper bound on any Kelly recommendation regardless of what
# the math says. A single trade should never risk more than 25% of
# the account in a paper stack that hasn't graduated to real money.
# If the math wants more, treat it as a signal that either p_win is
# overstated or win/loss magnitudes are miscalibrated.
MAX_KELLY_FRACTION_CAP = 0.25


# ═══════════════════════════════════════════════════════════════
# Core Kelly math
# ═══════════════════════════════════════════════════════════════

def full_kelly_fraction(p_win: float,
                        avg_win_pct: float,
                        avg_loss_pct: float) -> float:
    """Return the FULL Kelly fraction f* for a bet with win prob p_win,
    average profit-on-win = avg_win_pct, average loss-on-loss = avg_loss_pct.

    Both percentages expressed as positive fractions (0.05 = 5% up move
    on win, 0.03 = 3% down move on loss).

    f* = (p * b - q) / b, where b = avg_win / avg_loss, q = 1 - p.

    Returns 0 when the edge is negative or nonexistent (never a short
    bet — Orallexa handles long/short via `side`, not via sign of f*).
    Returns 0 when inputs are degenerate (NaN, negative, zero loss).
    """
    # Degenerate-input guard. Kelly math on garbage inputs produces
    # infinities that cascade into position sizing — fail closed.
    if not (0 < p_win < 1):
        return 0.0
    if avg_win_pct <= 0 or avg_loss_pct <= 0:
        return 0.0
    if any(math.isnan(x) or math.isinf(x)
           for x in (p_win, avg_win_pct, avg_loss_pct)):
        return 0.0

    b = avg_win_pct / avg_loss_pct
    q = 1.0 - p_win
    f_star = (p_win * b - q) / b
    if f_star <= 0:
        return 0.0
    return f_star


def fractional_kelly(p_win: float,
                     avg_win_pct: float,
                     avg_loss_pct: float,
                     *,
                     fraction: float = DEFAULT_KELLY_FRACTION,
                     max_cap: float = MAX_KELLY_FRACTION_CAP) -> float:
    """Return f = fraction × f*, capped at max_cap.

    Default fraction = 0.5 (Half-Kelly) per the professional consensus.
    Default cap = 0.25 (25% account) as absolute safety.
    """
    if fraction < 0:
        raise ValueError(f"fraction must be >= 0, got {fraction}")
    f_star = full_kelly_fraction(p_win, avg_win_pct, avg_loss_pct)
    return min(fraction * f_star, max_cap)


def drawdown_adjusted_kelly(p_win: float,
                            avg_win_pct: float,
                            avg_loss_pct: float,
                            *,
                            current_drawdown_pct: float,
                            max_tolerable_drawdown_pct: float = 15.0,
                            fraction: float = DEFAULT_KELLY_FRACTION,
                            max_cap: float = MAX_KELLY_FRACTION_CAP) -> float:
    """Half-Kelly scaled down by proximity to max tolerable drawdown.

    Rationale: when the portfolio is in drawdown, further losses
    approach ruin faster than the raw Kelly math anticipates. Scale
    the recommended fraction linearly from full at 0% DD to zero at
    max_tolerable_drawdown_pct.

    Ref: kill_conditions.MAX_DRAWDOWN_PCT (2026-07-02 upgrade #10)
    gates trading at 15% DD — this module ramps the sizing down
    smoothly on the way to that gate rather than trading at the same
    size right up to the wall.

    Parameters
    ----------
    current_drawdown_pct : positive percent (5.0 = 5% peak-to-trough)
    max_tolerable_drawdown_pct : hits zero here; default matches
        kill_conditions.MAX_DRAWDOWN_PCT (15%).
    """
    if current_drawdown_pct < 0:
        current_drawdown_pct = 0.0
    if max_tolerable_drawdown_pct <= 0:
        return 0.0

    ratio = current_drawdown_pct / max_tolerable_drawdown_pct
    if ratio >= 1.0:
        return 0.0
    dd_scale = 1.0 - ratio

    base = fractional_kelly(
        p_win, avg_win_pct, avg_loss_pct,
        fraction=fraction, max_cap=max_cap,
    )
    return base * dd_scale


# ═══════════════════════════════════════════════════════════════
# Applied — dollar notional
# ═══════════════════════════════════════════════════════════════

@dataclass
class KellyTicket:
    """Result of kelly_notional. Fields all present even when
    fraction == 0.0 (no-trade case) so downstream code has one shape."""
    account_usd: float
    fraction: float
    notional_usd: float
    method: str                   # "full_kelly" | "half_kelly" | "dd_adj_kelly"


def kelly_notional(account_usd: float,
                   p_win: float,
                   avg_win_pct: float,
                   avg_loss_pct: float,
                   *,
                   fraction: float = DEFAULT_KELLY_FRACTION,
                   max_cap: float = MAX_KELLY_FRACTION_CAP,
                   current_drawdown_pct: float | None = None,
                   max_tolerable_drawdown_pct: float = 15.0) -> KellyTicket:
    """Compute the dollar notional to allocate given account size and
    the Kelly parameters.

    If `current_drawdown_pct` is provided, uses drawdown-adjusted
    Kelly (scales down as DD grows). Otherwise plain fractional-Kelly.

    Method label is written into the ticket so downstream (portfolio
    reports, brier audit) can bucket by sizing method.
    """
    if account_usd <= 0:
        return KellyTicket(
            account_usd=account_usd, fraction=0.0,
            notional_usd=0.0, method="disabled_zero_account",
        )

    if current_drawdown_pct is not None:
        f = drawdown_adjusted_kelly(
            p_win, avg_win_pct, avg_loss_pct,
            current_drawdown_pct=current_drawdown_pct,
            max_tolerable_drawdown_pct=max_tolerable_drawdown_pct,
            fraction=fraction, max_cap=max_cap,
        )
        method = "dd_adj_kelly"
    else:
        f = fractional_kelly(
            p_win, avg_win_pct, avg_loss_pct,
            fraction=fraction, max_cap=max_cap,
        )
        method = "half_kelly" if fraction == 0.5 else (
            "full_kelly" if fraction == 1.0 else f"kelly_x{fraction:.2f}"
        )

    return KellyTicket(
        account_usd=account_usd, fraction=f,
        notional_usd=account_usd * f, method=method,
    )
