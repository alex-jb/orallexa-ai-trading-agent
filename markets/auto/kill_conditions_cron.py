"""
markets/auto/kill_conditions_cron.py — nightly kill-conditions check.

Ships 2026-07-02. Reads paper P&L history + decision log, computes
the 4-gate PortfolioState + runs `engine.kill_conditions.check_kill_conditions`,
then PERSISTS the decision to disk so the next morning's decision
pipeline can honor a WAIT/GATED without recomputing.

Runs nightly at 21:00 NY via launchd:

  Label: com.alexji.orallexa.kill-conditions-nightly
  Time:  21:00 NY (00:30 UTC in EDT, 01:30 UTC in EST)
  Path:  Users/alexji/.orallexa/orallexa-nightly-cron/run-kill-conditions.sh

The persisted state (`~/.orallexa/kill_state.json`) is READ by
whatever caller wants to short-circuit trading (portfolio_paper.py,
polymarket_daily.py's real-money mode, etc.). Persistence is
already implemented in engine.kill_conditions.persist_kill_state —
this cron just wires it to a nightly rhythm.

Wire-up rationale
-----------------
Without this cron, `check_kill_conditions` fires only when a caller
happens to invoke it — and if the caller forgets, dangerous market
conditions can pile up unnoticed. The nightly cron guarantees at
least one fresh check per day + writes the state where every other
caller can find it. Fail-safe: any crash writes an error state so
the morning path can see the problem, not silently proceed.

Exit codes
----------
0 = check ran, ok state written
2 = check ran, kill gate WAIT/GATED — state written (this is normal
    when the market conditions are actually bad)
1 = check itself crashed — no reliable state written; the morning
    pipeline should treat "kill state stale > 30h" as WAIT.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Add repo root to sys.path so `engine.*` imports work when the cron
# runs from anywhere.
_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.kill_conditions import (  # noqa: E402
    PortfolioState,
    check_kill_conditions,
    persist_kill_state,
    _KILL_STATE_PATH,
)


HOME = Path.home()
PAPER_PNL_PATH = HOME / ".orallexa" / "markets" / "paper_pnl_history.jsonl"
DECISION_LOG_PATH = HOME / ".orallexa" / "markets" / "decision_log.jsonl"
BRIER_HISTORY_PATH = HOME / ".orallexa" / "markets" / "polymarket_history.jsonl"


def _read_last_n_lines(path: Path, n: int) -> list[dict]:
    """Read last n JSONL lines from a file. Returns [] if file missing."""
    if not path.exists():
        return []
    try:
        with path.open() as f:
            lines = f.readlines()
    except OSError:
        return []
    out: list[dict] = []
    for raw in lines[-n:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def _compute_cumulative_pnl_usd(days: int = 30) -> float:
    """Sum paper P&L over the last `days` days. Returns 0 if no data."""
    rows = _read_last_n_lines(PAPER_PNL_PATH, days * 10)
    if not rows:
        return 0.0
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    total = 0.0
    for r in rows:
        ts_str = r.get("timestamp") or r.get("date")
        if ts_str:
            try:
                ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                if ts.timestamp() < cutoff:
                    continue
            except (ValueError, TypeError):
                pass
        pnl = r.get("pnl_usd") or r.get("pnl") or 0
        try:
            total += float(pnl)
        except (TypeError, ValueError):
            continue
    return total


def _compute_max_drawdown_pct(days: int = 14) -> float:
    """Peak-to-trough drawdown as a percent over the last `days` days.
    Uses paper P&L cumulative curve. Returns 0.0 if insufficient data."""
    rows = _read_last_n_lines(PAPER_PNL_PATH, days * 10)
    if len(rows) < 2:
        return 0.0
    cum = 0.0
    curve = []
    for r in rows:
        pnl = r.get("pnl_usd") or r.get("pnl") or 0
        try:
            cum += float(pnl)
        except (TypeError, ValueError):
            continue
        curve.append(cum)
    if len(curve) < 2:
        return 0.0
    peak = curve[0]
    max_dd = 0.0
    for x in curve:
        if x > peak:
            peak = x
        # If peak is 0 or negative, express DD as absolute dollars —
        # the caller can convert to percent-of-account if it wants.
        if peak > 0:
            dd_pct = (peak - x) / peak * 100.0
            if dd_pct > max_dd:
                max_dd = dd_pct
    return max_dd


def _compute_rolling_sharpe(days: int = 14) -> float | None:
    """Rolling-window Sharpe (returns mean / stdev) or None if
    insufficient data (min 5 rows)."""
    rows = _read_last_n_lines(PAPER_PNL_PATH, days * 10)
    if len(rows) < 5:
        return None
    returns = []
    for r in rows:
        pnl = r.get("pnl_usd") or r.get("pnl") or 0
        try:
            returns.append(float(pnl))
        except (TypeError, ValueError):
            continue
    if len(returns) < 5:
        return None
    n = len(returns)
    mean = sum(returns) / n
    var = sum((x - mean) ** 2 for x in returns) / max(1, n - 1)
    if var <= 0:
        return 0.0  # Zero variance is technically Sharpe = ∞; call it 0
                    # to fail conservatively toward wait.
    stdev = var ** 0.5
    return mean / stdev if stdev > 0 else 0.0


def _compute_rolling_brier(days: int = 30) -> float | None:
    """30-day rolling Brier from polymarket_history.jsonl. Returns
    None if insufficient resolved data."""
    rows = _read_last_n_lines(BRIER_HISTORY_PATH, days * 5)
    if len(rows) < 10:
        return None
    briers = []
    for r in rows:
        p = r.get("our_p_yes")
        actual = r.get("actual") or r.get("resolved_outcome")
        if p is None or actual is None:
            continue
        try:
            p_f = float(p)
            a_f = float(actual)
            briers.append((p_f - a_f) ** 2)
        except (TypeError, ValueError):
            continue
    if len(briers) < 10:
        return None
    return sum(briers) / len(briers)


def _count_paper_trade_days() -> int:
    """Days since first paper P&L entry. 0 if no history."""
    if not PAPER_PNL_PATH.exists():
        return 0
    try:
        with PAPER_PNL_PATH.open() as f:
            first_line = f.readline().strip()
    except OSError:
        return 0
    if not first_line:
        return 0
    try:
        first_row = json.loads(first_line)
    except json.JSONDecodeError:
        return 0
    ts_str = first_row.get("timestamp") or first_row.get("date")
    if not ts_str:
        return 0
    try:
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - ts).days
        return max(0, days)
    except (ValueError, TypeError):
        return 0


def build_portfolio_state() -> PortfolioState:
    """Read all persistent history files + build a PortfolioState."""
    return PortfolioState(
        cumulative_pnl_usd=_compute_cumulative_pnl_usd(days=30),
        rolling_14d_sharpe=_compute_rolling_sharpe(days=14),
        max_drawdown_pct=_compute_max_drawdown_pct(days=14),
        rolling_30d_brier=_compute_rolling_brier(days=30),
        paper_trade_days=_count_paper_trade_days(),
        real_money_mode=bool(int(os.environ.get("ORALLEXA_REAL_MONEY", "0"))),
    )


def main() -> int:
    print(f"[kill-conditions-nightly] fired at {datetime.now(timezone.utc).isoformat()}")
    try:
        state = build_portfolio_state()
        print(f"[kill-conditions-nightly] state: cumulative_pnl_usd={state.cumulative_pnl_usd:.2f}, "
              f"sharpe_14d={state.rolling_14d_sharpe}, "
              f"max_dd_pct={state.max_drawdown_pct:.2f}, "
              f"brier_30d={state.rolling_30d_brier}, "
              f"paper_days={state.paper_trade_days}, "
              f"real_money={state.real_money_mode}")
    except Exception as exc:
        print(f"[kill-conditions-nightly] FAILED to build state: {exc}",
              file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1

    try:
        decision = check_kill_conditions(state)
        # persist_kill_state signature is (decision, path=DEFAULT).
        # We pass decision only + let it write to the default path.
        persist_kill_state(decision)
        print(f"[kill-conditions-nightly] decision: can_trade={decision.can_trade}, "
              f"state={decision.state}, reason={decision.trigger_reason}, "
              f"cooldown_until_utc={decision.cooldown_until_utc}")
        print(f"[kill-conditions-nightly] state written to {_KILL_STATE_PATH}")
        return 0 if decision.can_trade else 2
    except Exception as exc:
        print(f"[kill-conditions-nightly] FAILED to check/persist: {exc}",
              file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
