"""Morning HITL markdown queue — the only output that touches your eyes.

For each ranked market the writer produces a markdown card with:

- The market question + platform + URL to manually trade
- Current YES price + our debate p_yes + the resulting edge
- Bull argument / Bear argument / Judge reasoning
- Suggested position size (computed by markets.sizing, fed in here)
- Three checkboxes: PASS / TRACK / PAPER-TRADE-$X

The checkboxes are unticked by default. Alex picks one and (if it's
PAPER-TRADE) places the trade by hand on the platform's web app. There
is no auto-executor in v0.1 — the only writer is markdown.

File layout under MARKETS_HOME (defaults to ~/.orallexa/markets):

    queue/
      pending/<date>-<platform>-<market_id>.md   ← writer drops here
      decided/<date>-<platform>-<market_id>.md   ← Alex moves here after deciding
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from markets.market import BinaryMarket
from markets.event_debate import EventDebateOutput


def _default_root() -> Path:
    return Path(
        os.environ.get("ORALLEXA_MARKETS_HOME", Path.home() / ".orallexa" / "markets")
    )


_TRADE_URL_TEMPLATES = {
    "kalshi": "https://kalshi.com/markets/{ticker}",
    "polymarket": "https://polymarket.com/event/{ticker}",
}


def _trade_url(market: BinaryMarket) -> str:
    tmpl = _TRADE_URL_TEMPLATES.get(market.platform, "")
    return tmpl.format(ticker=market.ticker) if tmpl else ""


def _safe_slug(s: str, max_len: int = 60) -> str:
    out = []
    for ch in s.lower():
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        elif ch in (" ", "/", "."):
            out.append("-")
    return ("".join(out)).strip("-")[:max_len] or "market"


@dataclass
class QueueEntry:
    """One ranked market for today's queue. Sizing is fed in from caller."""
    market: BinaryMarket
    debate: EventDebateOutput
    suggested_position_usd: float = 0.0
    sizing_notes: str = ""

    @property
    def edge(self) -> Optional[float]:
        return self.debate.edge

    @property
    def edge_abs(self) -> float:
        e = self.edge
        return abs(e) if e is not None else 0.0


def render_entry(entry: QueueEntry) -> str:
    m = entry.market
    d = entry.debate
    edge = entry.edge

    mkt_price = (
        f"{m.yes_price:.3f}" if m.yes_price is not None else "—"
    )
    edge_str = f"{edge:+.3f}" if edge is not None else "—"
    side = "BUY YES" if (edge is not None and edge > 0) else "BUY NO"

    evidence_for = "\n".join(f"  - {e}" for e in d.evidence_for) or "  - (none)"
    evidence_against = (
        "\n".join(f"  - {e}" for e in d.evidence_against) or "  - (none)"
    )

    # Critic verdict surface — only render block when Critic exists.
    if d.critic is not None:
        c = d.critic
        verdict_emoji = {"OK": "✓", "CAVEAT": "⚠", "REJECT": "✗"}.get(c.verdict, "?")
        critic_summary_row = f"| Critic | **{verdict_emoji} {c.verdict}** — {c.summary or '(no summary)'} |"
        critic_section_parts: list[str] = []
        if c.verdict != "OK" or c.failure_modes or c.unverifiable_claims:
            critic_section_parts.append(f"\n## Critic audit ({verdict_emoji} {c.verdict})\n")
            if c.failure_modes:
                critic_section_parts.append("**Failure modes flagged:**")
                critic_section_parts.extend(f"  - {f}" for f in c.failure_modes)
            checks = []
            if c.same_source_overlap:
                checks.append("• same-source bias detected (Bull/Bear cite same source)")
            if c.missing_base_rate:
                checks.append("• missing historical base-rate anchor")
            if c.confirmation_drift:
                checks.append("• confirmation drift (Judge leaned toward more verbose argument)")
            if checks:
                critic_section_parts.append("\n**Structural flags:**")
                critic_section_parts.extend(f"  {c}" for c in checks)
            if c.unverifiable_claims:
                critic_section_parts.append("\n**Unverifiable claims in debate:**")
                critic_section_parts.extend(f"  - {u}" for u in c.unverifiable_claims)
            if c.summary:
                critic_section_parts.append(f"\n*{c.summary}*")
        critic_section = "\n".join(critic_section_parts)
    else:
        critic_summary_row = ""
        critic_section = ""

    field_table = (
        f"| Field | Value |\n"
        f"|---|---|\n"
        f"| Platform | `{m.platform}` |\n"
        f"| Market | `{m.ticker}` |\n"
        f"| Category | {m.category} |\n"
        f"| Resolves | {m.close_time or 'TBD'} |\n"
        f"| Market YES price | **{mkt_price}** |\n"
        f"| Our p_yes | **{d.p_yes:.3f}** |\n"
        f"| Edge | **{edge_str}** |\n"
        f"| Suggested side | {side} |\n"
        f"| Suggested position | ${entry.suggested_position_usd:.2f} |\n"
        f"| Trade URL | {_trade_url(m) or '(manual)'} |"
    )
    if critic_summary_row:
        field_table += "\n" + critic_summary_row

    return f"""# {m.question}

{field_table}
{critic_section}

## Judge reasoning

{d.judge_reasoning or '(no reasoning)'}

## Evidence FOR YES
{evidence_for}

## Evidence AGAINST YES
{evidence_against}

## Sizing notes

{entry.sizing_notes or '(none)'}

## Bull argument

{d.bull_argument or '(empty)'}

## Bear argument

{d.bear_argument or '(empty)'}

---

## Decision

- [ ] PASS — skip this market
- [ ] TRACK — paper-log decision, don't trade
- [ ] PAPER-TRADE — paper position of size above, no real money
- [ ] REAL-TRADE — I placed this trade by hand on {m.platform}

Notes:
"""


@dataclass
class QueueWriter:
    """Writes per-market markdown files into ~/.orallexa/markets/queue/pending/."""
    root: Path

    @classmethod
    def default(cls) -> "QueueWriter":
        root = _default_root() / "queue"
        (root / "pending").mkdir(parents=True, exist_ok=True)
        (root / "decided").mkdir(parents=True, exist_ok=True)
        return cls(root=root)

    def write(self, entry: QueueEntry, when: Optional[datetime] = None) -> Path:
        when = when or datetime.now(timezone.utc)
        date_str = when.strftime("%Y-%m-%d")
        slug = _safe_slug(entry.market.ticker)
        fname = f"{date_str}-{entry.market.platform}-{slug}.md"
        path = self.root / "pending" / fname
        path.write_text(render_entry(entry), encoding="utf-8")
        return path

    def write_batch(
        self, entries: list[QueueEntry], when: Optional[datetime] = None
    ) -> list[Path]:
        sorted_entries = sorted(entries, key=lambda e: e.edge_abs, reverse=True)
        return [self.write(e, when=when) for e in sorted_entries]
