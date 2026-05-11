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

    return f"""# {m.question}

| Field | Value |
|---|---|
| Platform | `{m.platform}` |
| Market | `{m.ticker}` |
| Category | {m.category} |
| Resolves | {m.close_time or 'TBD'} |
| Market YES price | **{mkt_price}** |
| Our p_yes | **{d.p_yes:.3f}** |
| Edge | **{edge_str}** |
| Suggested side | {side} |
| Suggested position | ${entry.suggested_position_usd:.2f} |
| Trade URL | {_trade_url(m) or '(manual)'} |

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
