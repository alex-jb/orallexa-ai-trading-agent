"""
engine/insider_signal.py
──────────────────────────────────────────────────────────────────
Insider-transaction signal for Orallexa p(up) adjustment.

Surfaced by 2026-06-20 daily-brief §5: markets scan already pulls
SEC EDGAR Form-4 insider transactions (`markets/auto/news_morning.py`
fetch_insider_transactions, line 258), but the data only renders into
the daily brief — it never feeds back into the decision pipeline.

This module is the bridge. Pure-function, no LLM, deterministic
score adjustment so an existing engine call (e.g. earnings.py's
decision aggregator or daily_intel.py's signal compositor) can
apply it as a per-ticker p(up) tilt without rewriting the upstream
fetcher.

Core observations from the brief's named cases:
  - ASTS CFO Andrew Johnson 2026-06-11 sold 45,809 shares for ~$430k.
    Stock $80, was already softening. C-suite material sale during
    weakness = significant negative signal.
  - BKSY CEO + CFO same-day 2026-06-10 sold ~15k shares each, ~$500k
    each. Same-day C-suite paired sales are a rare and stronger
    negative signal than independent sales.

The score adjustment honors three thresholds:
  - Position seniority (CEO/CFO/President > Director > 10% Owner)
  - Direction (sale negative, purchase positive)
  - Clustering (same-day paired sales by 2+ C-suite officers add a
    multiplier — paired sales surprised the market historically)

Out of scope (deliberately):
  - LLM rationale generation. The signal is a number; rationale belongs
    in the daily brief layer.
  - Multi-ticker portfolio rebalancing. Per-ticker p(up) only.
  - Forward-looking earnings-window classification. A separate cooldown
    primitive may stack on top.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

# ────────────────────────────────────────────────────────────────────
# Tunables — calibrate against historical data once we have N≥30
# resolved insider-trade events with known forward returns.
# ────────────────────────────────────────────────────────────────────

# Position-weight: how heavy a specific role's trade counts.
POSITION_WEIGHT: dict[str, float] = {
    "ceo": 1.00,
    "chief executive": 1.00,
    "cfo": 0.95,
    "chief financial": 0.95,
    "president": 0.85,
    "coo": 0.80,
    "chief operating": 0.80,
    "director": 0.55,
    "10% owner": 0.45,
    "beneficial owner": 0.45,
    "vp": 0.40,
    "vice president": 0.40,
    "general counsel": 0.40,
}

# Direction sign — sale lowers p(up), purchase raises it.
DIRECTION_SIGN: dict[str, int] = {
    "sale": -1,
    "sell": -1,
    "purchase": +1,
    "buy": +1,
}

# Per-event base magnitude expressed as a p(up) delta in [0, 1].
# E.g. a single C-suite sale within window contributes a -0.04 tilt
# at full weight. Tunable; conservative until backtest validates.
PER_EVENT_BASE_DELTA = 0.04

# Cap on cumulative delta from this signal alone — prevents runaway
# adjustment from a noisy bunch of small trades.
ABS_DELTA_CAP = 0.15

# Multiplier when 2+ C-suite officers transact same direction on the
# same calendar date — empirical observation that paired same-day
# sales lead reported moves more reliably than single sales.
CSUITE_CLUSTER_MULTIPLIER = 1.6

# Minimum trade value (USD) to count. Below this is noise (small grants,
# vested options, etc.).
MIN_VALUE_USD = 50_000

# Default lookback window. Brief §5 implicitly used 14 days.
DEFAULT_WINDOW_DAYS = 14


# ────────────────────────────────────────────────────────────────────
# Data shape — mirrors what news_morning.fetch_insider_transactions
# returns, so the integration point is a list-of-dicts handoff.
# ────────────────────────────────────────────────────────────────────

@dataclass
class InsiderEvent:
    """One Form-4 row, normalized."""
    ticker: str
    date: date
    position: str          # e.g. "Chief Financial Officer"
    direction: str         # "sale" | "purchase" | other
    shares: int
    value_usd: float
    insider_name: str = ""

    @classmethod
    def from_dict(cls, row: dict) -> Optional["InsiderEvent"]:
        """Coerce one fetch_insider_transactions row. Returns None if
        unparseable so the caller can keep iterating."""
        try:
            d = row.get("date")
            if isinstance(d, str):
                d = date.fromisoformat(d[:10])
            elif isinstance(d, datetime):
                d = d.date()
            elif not isinstance(d, date):
                return None
            # Direction comes in as text e.g. "🔴 SELL" / "Sale at price"
            raw_dir = (row.get("direction") or row.get("text") or "").lower()
            if "sale" in raw_dir or "sell" in raw_dir:
                direction = "sale"
            elif "purchase" in raw_dir or "buy" in raw_dir:
                direction = "purchase"
            else:
                direction = "other"
            return cls(
                ticker=str(row["ticker"]).upper(),
                date=d,
                position=str(row.get("position", "")),
                direction=direction,
                shares=int(row.get("shares") or 0),
                value_usd=float(row.get("value_usd") or 0.0),
                insider_name=str(row.get("insider", "")),
            )
        except (KeyError, ValueError, TypeError):
            return None


@dataclass
class InsiderSignal:
    """Per-ticker signal result."""
    ticker: str
    p_up_delta: float        # signed adjustment to add to baseline p(up)
    events_considered: int   # how many qualifying events in window
    cluster_bonus_applied: bool   # was the C-suite same-day multiplier hit
    rationale: list[str] = field(default_factory=list)  # human-readable bullets


# ────────────────────────────────────────────────────────────────────
# Core scoring
# ────────────────────────────────────────────────────────────────────

def _position_weight(position: str) -> float:
    """Lookup the heaviest position-keyword match. Director < CEO etc."""
    p = (position or "").lower()
    best = 0.0
    for key, w in POSITION_WEIGHT.items():
        if key in p and w > best:
            best = w
    return best


def _direction_sign(direction: str) -> int:
    return DIRECTION_SIGN.get((direction or "").lower(), 0)


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def compute_insider_signal(
    ticker: str,
    events: Iterable[dict | InsiderEvent],
    window_days: int = DEFAULT_WINDOW_DAYS,
    today: Optional[date] = None,
) -> InsiderSignal:
    """Compute a per-ticker p(up) adjustment from a list of insider events.

    `events` accepts either raw dicts (as fetch_insider_transactions
    returns) or pre-coerced InsiderEvent instances — the function
    normalizes either way.

    The returned `p_up_delta` should be added to whatever baseline
    p(up) the caller produces. It's signed:
      negative → reduce p(up) (insiders are selling)
      positive → raise p(up) (insiders are buying)
      zero     → no qualifying activity in window

    `events_considered` is the count of qualifying events (passed
    position-seniority + min-value + window cutoffs). Useful for
    callers that want to gate on signal strength independently.
    """
    today = today or _today_utc()
    cutoff = today - timedelta(days=window_days)
    upper_ticker = ticker.upper()

    qualifying: list[InsiderEvent] = []
    for raw in events:
        if isinstance(raw, InsiderEvent):
            ev = raw
        else:
            ev = InsiderEvent.from_dict(raw)
            if ev is None:
                continue
        if ev.ticker.upper() != upper_ticker:
            continue
        if ev.date < cutoff or ev.date > today:
            continue
        if ev.value_usd < MIN_VALUE_USD:
            continue
        if _position_weight(ev.position) == 0:
            continue  # position not in seniority table
        if _direction_sign(ev.direction) == 0:
            continue
        qualifying.append(ev)

    delta = 0.0
    rationale: list[str] = []
    for ev in qualifying:
        pos_w = _position_weight(ev.position)
        dir_s = _direction_sign(ev.direction)
        contrib = dir_s * pos_w * PER_EVENT_BASE_DELTA
        delta += contrib
        rationale.append(
            f"{ev.date.isoformat()} {ev.position} {ev.direction} "
            f"${ev.value_usd:,.0f} → Δp(up) {contrib:+.3f}"
        )

    # Same-day C-suite cluster check
    csuite_keys = ("ceo", "chief executive", "cfo", "chief financial",
                   "president", "coo", "chief operating")
    cluster_bonus = False
    by_day: dict[tuple[date, str], list[InsiderEvent]] = {}
    for ev in qualifying:
        for ck in csuite_keys:
            if ck in ev.position.lower():
                by_day.setdefault((ev.date, ev.direction), []).append(ev)
                break
    for (day, direction), bundle in by_day.items():
        # Different insiders, same day, same direction — paired action
        names = {e.insider_name.lower() for e in bundle if e.insider_name}
        if len(names) >= 2:
            cluster_bonus = True
            extra = delta * (CSUITE_CLUSTER_MULTIPLIER - 1.0)
            delta += extra
            rationale.append(
                f"⚠️ same-day C-suite cluster on {day.isoformat()} "
                f"({direction}, {len(names)} officers) → ×{CSUITE_CLUSTER_MULTIPLIER} "
                f"multiplier applied (+{extra:+.3f})"
            )
            break  # apply at most one cluster bonus

    # Cap absolute magnitude
    if delta > ABS_DELTA_CAP:
        rationale.append(f"capped to +{ABS_DELTA_CAP:.2f}")
        delta = ABS_DELTA_CAP
    elif delta < -ABS_DELTA_CAP:
        rationale.append(f"capped to {-ABS_DELTA_CAP:.2f}")
        delta = -ABS_DELTA_CAP

    return InsiderSignal(
        ticker=upper_ticker,
        p_up_delta=round(delta, 4),
        events_considered=len(qualifying),
        cluster_bonus_applied=cluster_bonus,
        rationale=rationale,
    )


def apply_insider_adjustment(
    p_up_baseline: float,
    signal: InsiderSignal,
    clamp_to_unit: bool = True,
) -> float:
    """Convenience: add signal.p_up_delta to a baseline p(up), clamped
    to [0, 1] by default. Callers that want unclamped output (e.g. for
    logging the raw nudge) pass clamp_to_unit=False."""
    p = p_up_baseline + signal.p_up_delta
    if clamp_to_unit:
        p = max(0.0, min(1.0, p))
    return p
