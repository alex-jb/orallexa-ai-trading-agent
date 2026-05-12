"""Position ledger + PnL tracking for binary-event markets.

A "position" is created when the user moves a queue card from
`~/.orallexa/markets/queue/pending/` to `~/.orallexa/markets/queue/decided/`
AFTER checking a decision box. We parse the markdown to extract:

- Which box was checked (PASS / TRACK / PAPER-TRADE / REAL-TRADE)
- Position size in USD (from the card's "Suggested position" row, or a
  manual override in the "Notes:" section)
- Market + side + entry price

Positions are stored as JSONL at `~/.orallexa/markets/positions.jsonl`,
append-only. Each row is a Position dataclass. To close a position:
look up the market by `market_id`, fetch current outcome (if settled)
or current price (if open), and compute PnL.

We do NOT auto-fetch positions from Kalshi/Polymarket — v0.1 is read-only
and the user places every trade by hand. PnL is derived from what they
self-reported in the markdown card.

This is deliberate: the markdown card is the source of truth for decisions,
not the exchange. If the user clicks REAL-TRADE in the card but never
places it on kalshi.com, the ledger thinks they have the position. That
asymmetry is fine for the v0.1 educational loop — Brier-score validation
on `p_yes` vs `outcome` only needs decision-time + settlement-time data,
which we have from the card + the platform clients.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


def _default_root() -> Path:
    return Path(
        os.environ.get("ORALLEXA_MARKETS_HOME", Path.home() / ".orallexa" / "markets")
    )


DECISIONS = ("PASS", "TRACK", "PAPER-TRADE", "REAL-TRADE")


@dataclass
class Decision:
    """One decision extracted from a decided card."""
    market_id: str
    platform: str
    ticker: str
    question: str
    decision: str        # one of DECISIONS
    side: str            # "YES" or "NO" or ""
    position_usd: float  # 0.0 for PASS/TRACK
    p_yes: float
    entry_price: float
    decided_at: str      # ISO 8601
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ────────────────────────────────────────────────────────────────────
# MARKDOWN CARD PARSER
# ────────────────────────────────────────────────────────────────────


_FIELD_LINE = re.compile(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")


def _parse_field_table(md: str) -> dict[str, str]:
    """Parse the leading `| Field | Value |` table; returns dict of
    field_name → raw value string (markdown removed).
    """
    fields: dict[str, str] = {}
    lines = md.splitlines()
    # Find the table block at top of card
    in_table = False
    for line in lines:
        if line.startswith("# "):
            continue
        if line.startswith("|"):
            in_table = True
            m = _FIELD_LINE.match(line)
            if m:
                k = m.group(1).strip()
                v = m.group(2).strip()
                # Skip header / divider rows
                if k.lower() in ("field", "---"):
                    continue
                if v.startswith("---"):
                    continue
                # Strip backticks + bold markers
                v = v.replace("`", "").replace("**", "").strip()
                fields[k.lower()] = v
        elif in_table:
            # Table ended
            break
    return fields


def _extract_decision_choice(md: str) -> Optional[str]:
    """Find the first checked `- [x]` line in the Decision section."""
    in_decision = False
    for line in md.splitlines():
        if line.strip().startswith("## Decision"):
            in_decision = True
            continue
        if not in_decision:
            continue
        m = re.match(r"^- \[(x|X)\]\s+(\S+)", line.strip())
        if m:
            token = m.group(2).rstrip(" —")
            # Normalize: card uses "PAPER-TRADE" etc.
            return token.upper()
    return None


def _extract_notes(md: str) -> str:
    """Pull the Notes: line content after Decision section, if any."""
    in_decision = False
    capture_next = False
    for line in md.splitlines():
        if line.strip().startswith("## Decision"):
            in_decision = True
            continue
        if not in_decision:
            continue
        if line.strip().startswith("Notes:"):
            return line.split("Notes:", 1)[1].strip()
        if capture_next:
            return line.strip()
    return ""


def _parse_float_or_zero(s: str) -> float:
    """Strip $/% and parse, returning 0.0 on failure."""
    s = (s or "").replace("$", "").replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def parse_decided_card(path: Path) -> Optional[Decision]:
    """Parse one decided markdown card → Decision. Returns None if no
    decision checkbox is checked (the card was moved without picking one).
    """
    md = Path(path).read_text(encoding="utf-8")
    choice = _extract_decision_choice(md)
    if choice is None:
        return None

    fields = _parse_field_table(md)
    question_match = re.search(r"^#\s+(.+?)$", md, re.MULTILINE)
    question = question_match.group(1).strip() if question_match else ""

    market_id = fields.get("market", "").strip()
    platform = fields.get("platform", "").strip()
    yes_price = _parse_float_or_zero(fields.get("market yes price", ""))
    our_p = _parse_float_or_zero(fields.get("our p_yes", ""))
    side = fields.get("suggested side", "").upper()
    side_clean = "YES" if "YES" in side else ("NO" if "NO" in side else "")
    pos_str = fields.get("suggested position", "0")
    position_usd = _parse_float_or_zero(pos_str)

    # If user overrode position size in notes (e.g. "Notes: bumped to $25"),
    # we accept the markdown value as-is and let them edit by hand. v0.1
    # doesn't try to re-parse free-text notes for numeric overrides.
    notes = _extract_notes(md)

    decided_at = datetime.now(timezone.utc).isoformat()
    return Decision(
        market_id=market_id,
        platform=platform,
        ticker=market_id,
        question=question,
        decision=choice,
        side=side_clean,
        position_usd=position_usd if choice in ("PAPER-TRADE", "REAL-TRADE") else 0.0,
        p_yes=our_p,
        entry_price=yes_price,
        decided_at=decided_at,
        notes=notes,
    )


# ────────────────────────────────────────────────────────────────────
# POSITION LEDGER
# ────────────────────────────────────────────────────────────────────


@dataclass
class PositionLedger:
    """JSONL ledger of decisions, append-only with dedup on market_id."""
    path: Path

    @classmethod
    def default(cls) -> "PositionLedger":
        root = _default_root()
        root.mkdir(parents=True, exist_ok=True)
        return cls(path=root / "positions.jsonl")

    def existing_market_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        out: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            mid = row.get("market_id")
            if mid:
                out.add(mid)
        return out

    def append(self, decisions: Iterable[Decision]) -> int:
        decisions = list(decisions)
        if not decisions:
            return 0
        seen = self.existing_market_ids()
        new_rows = [d for d in decisions if d.market_id not in seen]
        if not new_rows:
            return 0
        with self.path.open("a", encoding="utf-8") as f:
            for d in new_rows:
                f.write(json.dumps(d.to_dict(), ensure_ascii=False) + "\n")
        return len(new_rows)

    def load_all(self) -> list[Decision]:
        if not self.path.exists():
            return []
        out: list[Decision] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            out.append(Decision(**row))
        return out


def harvest_decided_dir(decided_dir: Optional[Path] = None) -> list[Decision]:
    """Scan ~/.orallexa/markets/queue/decided/ for checked cards and
    return their parsed Decisions. Idempotent — does not delete cards.
    """
    decided_dir = decided_dir or (_default_root() / "queue" / "decided")
    if not decided_dir.exists():
        return []
    out: list[Decision] = []
    for path in sorted(decided_dir.glob("*.md")):
        d = parse_decided_card(path)
        if d is not None:
            out.append(d)
    return out


# ────────────────────────────────────────────────────────────────────
# PnL COMPUTATION
# ────────────────────────────────────────────────────────────────────


@dataclass
class PnLRow:
    decision: Decision
    outcome: Optional[int]            # 1=YES, 0=NO, None=unresolved
    settled: bool
    realized_pnl_usd: float
    brier: Optional[float]            # (p_yes - outcome)^2 if settled

    def to_dict(self) -> dict:
        return {
            "market_id": self.decision.market_id,
            "ticker": self.decision.ticker,
            "decision": self.decision.decision,
            "side": self.decision.side,
            "position_usd": self.decision.position_usd,
            "p_yes": self.decision.p_yes,
            "entry_price": self.decision.entry_price,
            "outcome": self.outcome,
            "settled": self.settled,
            "realized_pnl_usd": self.realized_pnl_usd,
            "brier": self.brier,
        }


def _pnl_for_binary(
    side: str, entry_price: float, outcome: int, position_usd: float
) -> float:
    """Net PnL for a binary position held to resolution.

    YES bet: buy `position_usd / entry_price` YES shares at entry. Payout
    1.00 per share if YES, 0.00 if NO. PnL = shares * 1 - position_usd
    when YES wins; -position_usd when NO wins.

    NO bet: symmetric, buy NO shares at (1 - entry_price).
    """
    if position_usd <= 0:
        return 0.0
    if side == "YES":
        share_price = entry_price
    elif side == "NO":
        share_price = 1.0 - entry_price
    else:
        return 0.0
    if share_price <= 0:
        return 0.0
    shares = position_usd / share_price
    won = (side == "YES" and outcome == 1) or (side == "NO" and outcome == 0)
    return shares * 1.0 - position_usd if won else -position_usd


def compute_pnl(
    decisions: list[Decision],
    *,
    outcome_lookup,
) -> list[PnLRow]:
    """For each decision compute realized PnL via outcome_lookup callable.

    outcome_lookup(market_id, platform) → Optional[int]   (1=YES, 0=NO, None=open)
    """
    rows: list[PnLRow] = []
    for d in decisions:
        if d.decision in ("PASS", "TRACK"):
            rows.append(PnLRow(
                decision=d, outcome=None, settled=False,
                realized_pnl_usd=0.0, brier=None,
            ))
            continue
        outcome = outcome_lookup(d.market_id, d.platform)
        if outcome is None:
            rows.append(PnLRow(
                decision=d, outcome=None, settled=False,
                realized_pnl_usd=0.0, brier=None,
            ))
            continue
        pnl = _pnl_for_binary(d.side, d.entry_price, outcome, d.position_usd)
        brier = (d.p_yes - outcome) ** 2
        rows.append(PnLRow(
            decision=d, outcome=outcome, settled=True,
            realized_pnl_usd=pnl, brier=brier,
        ))
    return rows
