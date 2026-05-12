"""Evening retrospective — daily PnL + Brier journal.

Run after market close (or whenever you check in for the day). Pulls all
decisions out of the ledger, resolves outcomes via platform clients on
settled markets, then writes a markdown journal to
`~/.orallexa/markets/retro/YYYY-MM-DD.md`.

Sections of the journal:

  1. PnL summary (today's realized + cumulative)
  2. Brier table (settled markets — LLM p_yes vs reality)
  3. Open positions (unresolved)
  4. Circuit breaker check + tomorrow's status
  5. Kill-condition status (Brier baseline, monthly drawdown, ToS)

This module does NOT make trading decisions — it's a journal writer.
The kill conditions are surfaced as red text; you decide what to do.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable, Optional

from markets.pnl_tracker import (
    PositionLedger, PnLRow, Decision, compute_pnl, harvest_decided_dir,
)


def _default_root() -> Path:
    return Path(
        os.environ.get("ORALLEXA_MARKETS_HOME", Path.home() / ".orallexa" / "markets")
    )


@dataclass
class RetroSummary:
    """Aggregate stats for one day's retro."""
    date: str
    n_decisions_today: int
    n_settled: int
    n_open: int
    realized_pnl_today: float
    realized_pnl_cumulative: float
    brier_mean: Optional[float]            # mean Brier across settled markets
    brier_market_baseline: Optional[float] # mean Brier of using market price as p
    bankroll_start: float
    daily_drawdown_pct: float
    monthly_drawdown_pct: float
    kill_conditions_tripped: list[str]


def make_lookup_from_clients(kalshi_client=None, polymarket_client=None) -> Callable:
    """Returns outcome_lookup(market_id, platform) -> Optional[int] backed by
    the platform clients. Caches results in a closure to avoid re-fetching
    the same market within one retro run.
    """
    cache: dict[tuple[str, str], Optional[int]] = {}

    def lookup(market_id: str, platform: str) -> Optional[int]:
        key = (platform, market_id)
        if key in cache:
            return cache[key]
        outcome: Optional[int] = None
        try:
            if platform == "kalshi" and kalshi_client is not None:
                m = kalshi_client.get_market(market_id)
                outcome = m.outcome
            elif platform == "polymarket" and polymarket_client is not None:
                m = polymarket_client.get_market(market_id)
                outcome = m.outcome
        except Exception:  # noqa: BLE001 — network errors / 404 etc.
            outcome = None
        cache[key] = outcome
        return outcome

    return lookup


def _aggregate(
    rows: list[PnLRow],
    *,
    date: str,
    bankroll_start: float,
    bankroll_kill_pct: float = 0.15,
    daily_kill_pct: float = 0.10,
) -> RetroSummary:
    settled = [r for r in rows if r.settled]
    open_pos = [r for r in rows if not r.settled and r.decision.decision != "PASS"]
    today_realized = sum(
        r.realized_pnl_usd for r in settled
        if r.decision.decided_at.startswith(date)
    )
    cumulative = sum(r.realized_pnl_usd for r in settled)

    brier_mean: Optional[float] = None
    brier_baseline: Optional[float] = None
    if settled:
        briers = [r.brier for r in settled if r.brier is not None]
        if briers:
            brier_mean = sum(briers) / len(briers)
            # baseline: using market entry_price as p instead of LLM p_yes
            baseline_briers = []
            for r in settled:
                if r.outcome is None:
                    continue
                baseline_briers.append((r.decision.entry_price - r.outcome) ** 2)
            if baseline_briers:
                brier_baseline = sum(baseline_briers) / len(baseline_briers)

    daily_dd_pct = -today_realized / bankroll_start if bankroll_start else 0
    monthly_dd_pct = max(0, -cumulative / bankroll_start) if bankroll_start else 0

    tripped: list[str] = []
    if daily_dd_pct > daily_kill_pct:
        tripped.append(
            f"DAILY_DRAWDOWN: {daily_dd_pct:.1%} > {daily_kill_pct:.1%} — pause trading until tomorrow"
        )
    if monthly_dd_pct > bankroll_kill_pct:
        tripped.append(
            f"MONTHLY_DRAWDOWN: {monthly_dd_pct:.1%} > {bankroll_kill_pct:.1%} — 30-day pause + manual review"
        )
    if brier_mean is not None and brier_baseline is not None and len(settled) >= 100:
        if brier_mean >= brier_baseline:
            tripped.append(
                f"BRIER_NOT_BEATING_MARKET: ours={brier_mean:.4f} >= baseline={brier_baseline:.4f} on n={len(settled)} — archive signal"
            )

    return RetroSummary(
        date=date,
        n_decisions_today=sum(1 for r in rows if r.decision.decided_at.startswith(date)),
        n_settled=len(settled),
        n_open=len(open_pos),
        realized_pnl_today=today_realized,
        realized_pnl_cumulative=cumulative,
        brier_mean=brier_mean,
        brier_market_baseline=brier_baseline,
        bankroll_start=bankroll_start,
        daily_drawdown_pct=daily_dd_pct,
        monthly_drawdown_pct=monthly_dd_pct,
        kill_conditions_tripped=tripped,
    )


def render_retro(summary: RetroSummary, rows: list[PnLRow]) -> str:
    settled = [r for r in rows if r.settled]
    open_rows = [
        r for r in rows
        if not r.settled and r.decision.decision in ("PAPER-TRADE", "REAL-TRADE")
    ]

    def _money(x: float) -> str:
        sign = "+" if x >= 0 else ""
        return f"{sign}${x:,.2f}"

    def _pct(x: float) -> str:
        return f"{x:.1%}"

    lines: list[str] = []
    lines.append(f"# Retro — {summary.date}\n")
    lines.append("## Summary\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Bankroll baseline | ${summary.bankroll_start:,.2f} |")
    lines.append(f"| Decisions today | {summary.n_decisions_today} |")
    lines.append(f"| Settled / Open | {summary.n_settled} / {summary.n_open} |")
    lines.append(f"| Realized PnL today | **{_money(summary.realized_pnl_today)}** |")
    lines.append(f"| Realized PnL cumulative | **{_money(summary.realized_pnl_cumulative)}** |")
    lines.append(f"| Daily drawdown % | {_pct(summary.daily_drawdown_pct)} |")
    lines.append(f"| Monthly drawdown % | {_pct(summary.monthly_drawdown_pct)} |")
    if summary.brier_mean is not None:
        baseline = (
            f"{summary.brier_market_baseline:.4f}"
            if summary.brier_market_baseline is not None else "—"
        )
        lines.append(f"| Brier mean (LLM) | **{summary.brier_mean:.4f}** |")
        lines.append(f"| Brier baseline (market) | {baseline} |")
        if summary.brier_market_baseline is not None:
            delta = summary.brier_market_baseline - summary.brier_mean
            verdict = "✅ beating market" if delta > 0 else "❌ market wins"
            lines.append(f"| Brier delta | {delta:+.4f}  {verdict} |")

    if summary.kill_conditions_tripped:
        lines.append("\n## ⚠️ Kill conditions tripped\n")
        for k in summary.kill_conditions_tripped:
            lines.append(f"- **{k}**")
    else:
        lines.append("\n## Kill conditions\n")
        lines.append("- (none tripped — green to continue tomorrow)")

    if settled:
        lines.append("\n## Settled today\n")
        lines.append("| Market | Side | $ | p_yes | entry | outcome | PnL | Brier |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in settled:
            d = r.decision
            outcome_str = "YES" if r.outcome == 1 else ("NO" if r.outcome == 0 else "—")
            brier_str = f"{r.brier:.3f}" if r.brier is not None else "—"
            lines.append(
                f"| `{d.ticker[:40]}` | {d.side} | ${d.position_usd:.2f} | "
                f"{d.p_yes:.3f} | {d.entry_price:.3f} | {outcome_str} | "
                f"{_money(r.realized_pnl_usd)} | {brier_str} |"
            )

    if open_rows:
        lines.append("\n## Open positions\n")
        lines.append("| Market | Side | $ | p_yes | entry | days open |")
        lines.append("|---|---|---|---|---|---|")
        now = datetime.now(timezone.utc)
        for r in open_rows:
            d = r.decision
            try:
                dt = datetime.fromisoformat(d.decided_at.replace("Z", "+00:00"))
                days = (now - dt).days
            except ValueError:
                days = -1
            lines.append(
                f"| `{d.ticker[:40]}` | {d.side} | ${d.position_usd:.2f} | "
                f"{d.p_yes:.3f} | {d.entry_price:.3f} | {days} |"
            )

    lines.append("\n## Notes\n")
    lines.append(
        "- Sample size for Brier validation: need n=100 settled markets "
        "for ~95% CI on whether LLM beats market baseline."
    )
    lines.append(
        "- 1 σ on n=100 Brier delta = 0.01-0.02. Be careful concluding too "
        "early."
    )
    return "\n".join(lines) + "\n"


@dataclass
class RetroWriter:
    """Writes evening retro markdown to ~/.orallexa/markets/retro/."""
    root: Path

    @classmethod
    def default(cls) -> "RetroWriter":
        root = _default_root() / "retro"
        root.mkdir(parents=True, exist_ok=True)
        return cls(root=root)

    def write(self, summary: RetroSummary, rows: list[PnLRow]) -> Path:
        body = render_retro(summary, rows)
        path = self.root / f"{summary.date}.md"
        path.write_text(body, encoding="utf-8")
        return path


def run_retro(
    *,
    bankroll_start: float,
    outcome_lookup: Callable,
    date: Optional[str] = None,
) -> tuple[Path, RetroSummary]:
    """End-to-end: harvest decided cards → ledger → PnL → retro markdown."""
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Harvest any newly-decided cards into the ledger (idempotent dedup)
    decisions_in_dir = harvest_decided_dir()
    ledger = PositionLedger.default()
    ledger.append(decisions_in_dir)

    all_decisions = ledger.load_all()
    rows = compute_pnl(all_decisions, outcome_lookup=outcome_lookup)
    summary = _aggregate(rows, date=date, bankroll_start=bankroll_start)
    path = RetroWriter.default().write(summary, rows)
    return path, summary
