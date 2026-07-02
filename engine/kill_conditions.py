"""
engine/kill_conditions.py
──────────────────────────────────────────────────────────────────
Kill conditions + real-money gate for Orallexa.

Ships 2026-07-02 Tier-1 upgrade #10 from the deep-research roadmap.

Why this exists
---------------
The 2026-06-30 audit found this as the single most dangerous
architecture pattern on the whole stack:

    "No kill condition on paper loss — if real money were $300,
    system keeps emitting BUY signals through -$1,015 paper drawdown
    with no explicit stop. Potentially $1-5K burn before auto-stop."

Before this module, "when do we stop trading" lived only in Alex's
head. Now it lives here, verifiable, testable, callable from any
entry-point (portfolio_paper, live trading, brier_audit) that
matters.

Contract
--------
A single pure function `check_kill_conditions(state) -> KillDecision`
takes a `PortfolioState` and returns a `KillDecision` with:
  - `can_trade: bool` — is the system allowed to open new positions?
  - `state: str` — "OK" | "WAIT" | "GATED"
  - `trigger_reason: str | None` — what specifically tripped
  - `cooldown_until_utc: str | None` — ISO 8601 when GATED lifts

Four gates, evaluated in order. Any one gate `WAIT` short-circuits.

  1. MAX_CUMULATIVE_LOSS_USD ($500 default) — hard dollar loss cap.
     Hit → WAIT 7 days.
  2. MIN_SHARPE_ROLLING_14D (0.0 default) — 14-day rolling Sharpe
     must be > 0. Below → WAIT 3 days.
  3. MAX_DRAWDOWN_PCT (15% default) — peak-to-trough intraday.
     Hit → WAIT 7 days.
  4. MIN_BRIER_ROLLING_30D (0.20 default) — required to ENTER real
     money in the first place. Above → GATED (not "wait"). Never
     released without operator override.

Real-money gate
---------------
`is_ready_for_real_money(state)` is the stricter check specifically
for the paper → real transition. Requires ALL of: min-30d-Brier under
threshold, positive rolling Sharpe, no active kill, and >= 30 days
of paper trade history.

Threshold constants
-------------------
Constants live at module top-level so tests can monkeypatch to exercise
the boundaries. Real values were chosen from the roadmap conservatively:
we prefer false-negative (system stays in WAIT slightly too long) over
false-positive (system trades through danger). If Alex wants to relax
these he does it in code with a review, not by env var — the whole
point is that these are the load-bearing invariants.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════
# Threshold constants — the numbers that actually stop the system
# ═══════════════════════════════════════════════════════════════

# Hard dollar cap on cumulative loss. Once hit, system enters WAIT
# for MAX_LOSS_COOLDOWN_DAYS regardless of subsequent signals. Chosen
# to be a survivable-lesson amount for a solo founder — big enough
# to be painful (so we notice), small enough not to be a catastrophe.
MAX_CUMULATIVE_LOSS_USD = 500.0
MAX_LOSS_COOLDOWN_DAYS = 7

# 14-day rolling Sharpe. Zero is the neutral bar — negative rolling
# Sharpe means we're not just losing money, we're losing it faster
# than random.
MIN_SHARPE_ROLLING_14D = 0.0
MIN_SHARPE_COOLDOWN_DAYS = 3

# Peak-to-trough drawdown percent. 15% is aggressive but sub-total-loss.
# A drawdown that crosses this bar is not an edge doing its job.
MAX_DRAWDOWN_PCT = 15.0
MAX_DRAWDOWN_COOLDOWN_DAYS = 7

# Brier score threshold required to move from paper into real money.
# Prophet Arena's top model (GPT-5R) scores Brier ~0.184; Kalshi
# aggregate scores ~0.19. Getting under 0.20 says "we're at least
# in the same neighborhood as SOTA." Above 0.20 means we shouldn't
# even be considering real money.
MIN_BRIER_ROLLING_30D_FOR_REAL_MONEY = 0.20

# Minimum paper-trade history to consider the real-money gate. Prevents
# a lucky first-week paper streak from flipping the switch prematurely.
MIN_PAPER_DAYS_FOR_REAL_MONEY = 30


# ═══════════════════════════════════════════════════════════════
# State + decision types
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PortfolioState:
    """Rolling snapshot of the portfolio for kill-condition evaluation.

    Passed to check_kill_conditions() by whichever caller has the
    freshest numbers — this module doesn't fetch state, it evaluates it.
    """
    cumulative_pnl_usd: float
    rolling_14d_sharpe: float | None       # None = insufficient history
    max_drawdown_pct: float
    rolling_30d_brier: float | None        # None = insufficient history
    paper_trade_days: int                  # days since paper mode started
    real_money_mode: bool = False          # True once real money is on


@dataclass
class KillDecision:
    """Result of check_kill_conditions."""
    can_trade: bool
    state: str                             # "OK" | "WAIT" | "GATED"
    trigger_reason: str | None = None
    cooldown_until_utc: str | None = None
    triggered_gates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
# Gate check
# ═══════════════════════════════════════════════════════════════

def check_kill_conditions(state: PortfolioState) -> KillDecision:
    """Evaluate the four gates and return a decision.

    Gates evaluated in order; first WAIT short-circuits. This is
    important — we DON'T want to report five reasons the system
    should stop, we want to report the first one that tripped so
    Alex can fix that and re-check.

    Sharpe / Brier None values mean "insufficient history" — we
    treat that as OK (the gate is not applicable yet), not as a
    failure. Kill conditions bite once you have data, not before.
    """
    now_utc = datetime.now(timezone.utc)
    triggered: list[str] = []

    # Gate 1: cumulative loss cap
    if state.cumulative_pnl_usd <= -abs(MAX_CUMULATIVE_LOSS_USD):
        reason = (
            f"cumulative_loss ${state.cumulative_pnl_usd:.2f} "
            f"≤ -${MAX_CUMULATIVE_LOSS_USD:.2f} threshold"
        )
        triggered.append("max_cumulative_loss")
        return KillDecision(
            can_trade=False,
            state="WAIT",
            trigger_reason=reason,
            cooldown_until_utc=(now_utc + timedelta(days=MAX_LOSS_COOLDOWN_DAYS)).isoformat(),
            triggered_gates=triggered,
        )

    # Gate 2: 14d rolling Sharpe. Skip if we don't have it yet.
    if state.rolling_14d_sharpe is not None:
        # NaN protection — if backend produced NaN, fail closed.
        sharpe = state.rolling_14d_sharpe
        # Note: `<=` not `<` here. If Sharpe is exactly 0 (break-even
        # randomness), we're not compensating for the risk we're taking
        # — better to sit out. Kill conditions err safe.
        if math.isnan(sharpe) or sharpe <= MIN_SHARPE_ROLLING_14D:
            reason = (
                f"rolling_14d_sharpe {sharpe:.3f} "
                f"< {MIN_SHARPE_ROLLING_14D} threshold"
            )
            triggered.append("min_sharpe_14d")
            return KillDecision(
                can_trade=False,
                state="WAIT",
                trigger_reason=reason,
                cooldown_until_utc=(now_utc + timedelta(days=MIN_SHARPE_COOLDOWN_DAYS)).isoformat(),
                triggered_gates=triggered,
            )

    # Gate 3: max drawdown %
    if state.max_drawdown_pct >= MAX_DRAWDOWN_PCT:
        reason = (
            f"max_drawdown_pct {state.max_drawdown_pct:.2f}% "
            f"≥ {MAX_DRAWDOWN_PCT}% threshold"
        )
        triggered.append("max_drawdown")
        return KillDecision(
            can_trade=False,
            state="WAIT",
            trigger_reason=reason,
            cooldown_until_utc=(now_utc + timedelta(days=MAX_DRAWDOWN_COOLDOWN_DAYS)).isoformat(),
            triggered_gates=triggered,
        )

    # Gate 4: Brier gate — only applies while in real money mode. In
    # paper mode a bad Brier isn't a kill condition, it's the data
    # you're producing to figure out whether you're ready. GATED state
    # says "you shouldn't even be here." Non-recoverable without
    # operator override.
    if state.real_money_mode and state.rolling_30d_brier is not None:
        if state.rolling_30d_brier > MIN_BRIER_ROLLING_30D_FOR_REAL_MONEY:
            reason = (
                f"rolling_30d_brier {state.rolling_30d_brier:.3f} "
                f"> {MIN_BRIER_ROLLING_30D_FOR_REAL_MONEY} — "
                f"gate closed"
            )
            triggered.append("brier_gate")
            return KillDecision(
                can_trade=False,
                state="GATED",
                trigger_reason=reason,
                cooldown_until_utc=None,  # no auto-recovery
                triggered_gates=triggered,
            )

    return KillDecision(can_trade=True, state="OK", triggered_gates=[])


def is_ready_for_real_money(state: PortfolioState) -> tuple[bool, str]:
    """Stricter check for the paper → real-money transition.

    Returns (ready, reason). Requires ALL of:
      - Not currently in a WAIT / GATED state
      - >= MIN_PAPER_DAYS_FOR_REAL_MONEY days of paper history
      - rolling_30d_brier is set AND under MIN_BRIER_ROLLING_30D_FOR_REAL_MONEY
      - rolling_14d_sharpe is set AND > 0
      - cumulative_pnl_usd >= 0 (i.e. currently at breakeven or up)

    This is intentionally paranoid. Real money is a one-way trap: once
    you're in you can lose real dollars in minutes.
    """
    if state.real_money_mode:
        return False, "already in real money mode — this check is for the transition"

    kill = check_kill_conditions(state)
    if not kill.can_trade:
        return False, f"active kill state: {kill.state} ({kill.trigger_reason})"

    if state.paper_trade_days < MIN_PAPER_DAYS_FOR_REAL_MONEY:
        return False, (
            f"paper_trade_days {state.paper_trade_days} < "
            f"{MIN_PAPER_DAYS_FOR_REAL_MONEY} required"
        )

    if state.rolling_30d_brier is None:
        return False, "rolling_30d_brier not yet computable"
    if state.rolling_30d_brier > MIN_BRIER_ROLLING_30D_FOR_REAL_MONEY:
        return False, (
            f"rolling_30d_brier {state.rolling_30d_brier:.3f} > "
            f"{MIN_BRIER_ROLLING_30D_FOR_REAL_MONEY}"
        )

    if state.rolling_14d_sharpe is None:
        return False, "rolling_14d_sharpe not yet computable"
    if state.rolling_14d_sharpe <= 0:
        return False, f"rolling_14d_sharpe {state.rolling_14d_sharpe:.3f} <= 0"

    if state.cumulative_pnl_usd < 0:
        return False, f"cumulative_pnl_usd ${state.cumulative_pnl_usd:.2f} < 0"

    return True, "all gates clear"


# ═══════════════════════════════════════════════════════════════
# On-disk kill state (durable cooldown tracking across restarts)
# ═══════════════════════════════════════════════════════════════

_KILL_STATE_PATH = Path.home() / ".orallexa" / "markets" / "kill_state.json"


def read_persisted_kill_state(path: Path = _KILL_STATE_PATH) -> dict[str, Any] | None:
    """Return the last persisted KillDecision dict, or None."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def persist_kill_state(decision: KillDecision,
                       path: Path = _KILL_STATE_PATH) -> None:
    """Write the current KillDecision to disk. Callers that want
    durable cooldown across cron restarts should call this at the
    end of every check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **decision.to_dict(),
        "persisted_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2))


def cooldown_still_active(path: Path = _KILL_STATE_PATH) -> bool:
    """True if a previously-persisted decision's cooldown window
    hasn't yet lapsed. Meant for a caller that wants to short-circuit
    without redoing the full evaluation."""
    persisted = read_persisted_kill_state(path)
    if not persisted:
        return False
    cool_until = persisted.get("cooldown_until_utc")
    if not cool_until:
        return False
    try:
        cool_dt = datetime.fromisoformat(cool_until.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    return datetime.now(timezone.utc) < cool_dt
