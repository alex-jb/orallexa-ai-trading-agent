"""tests/test_markets_pnl.py
─────────────────────────────────────────────────────────────
Markdown decision parser + PnL math + ledger dedup tests.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from markets.pnl_tracker import (
    parse_decided_card, harvest_decided_dir, PositionLedger,
    Decision, compute_pnl, _pnl_for_binary,
)


SAMPLE_CARD = """# Will the US and Iran reach a deal by July 1, 2026?

| Field | Value |
|---|---|
| Platform | `polymarket` |
| Market | `iran-deal-by-july-2026` |
| Category | geopolitics |
| Resolves | 2026-07-01T23:59:59Z |
| Market YES price | **0.420** |
| Our p_yes | **0.610** |
| Edge | **+0.190** |
| Suggested side | BUY YES |
| Suggested position | $15.00 |
| Trade URL | https://polymarket.com/event/iran-deal-by-july-2026 |

## Judge reasoning

The bull cited two hard signals; the bear one.

## Evidence FOR YES
  - State Dept "constructive" readout
  - Futures curve flat

## Evidence AGAINST YES
  - IRGC escalatory statement

## Sizing notes

quarter-Kelly = 0.100

## Bull argument

Strong case.

## Bear argument

Weak case.

---

## Decision

- [ ] PASS — skip this market
- [ ] TRACK — paper-log decision, don't trade
- [x] PAPER-TRADE — paper position of size above, no real money
- [ ] REAL-TRADE — I placed this trade by hand on polymarket

Notes: confident on this one
"""


def _write_card(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ── parse_decided_card ─────────────────────────────────────────────


def test_parse_paper_trade_card(tmp_path: Path):
    path = _write_card(tmp_path / "card.md", SAMPLE_CARD)
    d = parse_decided_card(path)
    assert d is not None
    assert d.decision == "PAPER-TRADE"
    assert d.platform == "polymarket"
    assert d.market_id == "iran-deal-by-july-2026"
    assert d.side == "YES"
    assert d.position_usd == 15.0
    assert abs(d.p_yes - 0.610) < 1e-6
    assert abs(d.entry_price - 0.420) < 1e-6
    assert "confident" in d.notes


def test_parse_card_no_checkbox_returns_none(tmp_path: Path):
    # Strip the [x]
    md = SAMPLE_CARD.replace("- [x]", "- [ ]")
    path = _write_card(tmp_path / "u.md", md)
    assert parse_decided_card(path) is None


def test_parse_pass_card_has_zero_position(tmp_path: Path):
    md = SAMPLE_CARD.replace("- [x] PAPER-TRADE", "- [x] PASS")\
                    .replace("- [ ] PASS", "- [ ] PAPER-TRADE")
    path = _write_card(tmp_path / "pass.md", md)
    d = parse_decided_card(path)
    assert d is not None
    assert d.decision == "PASS"
    assert d.position_usd == 0.0   # PASS clears position


def test_harvest_decided_dir(tmp_path: Path):
    # Build a queue/decided/ dir with two cards
    decided = tmp_path / "decided"
    decided.mkdir()
    _write_card(decided / "a.md", SAMPLE_CARD)
    _write_card(decided / "b.md", SAMPLE_CARD.replace(
        "iran-deal-by-july-2026", "other-market"
    ))
    results = harvest_decided_dir(decided)
    assert len(results) == 2
    ids = {r.market_id for r in results}
    assert ids == {"iran-deal-by-july-2026", "other-market"}


# ── PositionLedger ──────────────────────────────────────────────────


def test_ledger_dedups_on_market_id(tmp_path: Path):
    ledger = PositionLedger(path=tmp_path / "positions.jsonl")
    d1 = Decision(
        market_id="m1", platform="kalshi", ticker="m1", question="?",
        decision="PAPER-TRADE", side="YES", position_usd=10.0,
        p_yes=0.6, entry_price=0.5, decided_at="2026-05-11T09:00:00+00:00",
    )
    d2 = Decision(
        market_id="m2", platform="kalshi", ticker="m2", question="?",
        decision="PAPER-TRADE", side="NO", position_usd=10.0,
        p_yes=0.3, entry_price=0.6, decided_at="2026-05-11T09:00:00+00:00",
    )
    assert ledger.append([d1, d2]) == 2
    assert ledger.append([d1, d2]) == 0  # dedup
    assert ledger.append([d2]) == 0
    assert len(ledger.load_all()) == 2


# ── PnL math ────────────────────────────────────────────────────────


def test_pnl_yes_wins():
    # Buy YES at 0.50 with $10 → 20 shares. YES wins → $20 - $10 = +$10
    pnl = _pnl_for_binary(side="YES", entry_price=0.50, outcome=1, position_usd=10.0)
    assert abs(pnl - 10.0) < 1e-6


def test_pnl_yes_loses():
    pnl = _pnl_for_binary(side="YES", entry_price=0.50, outcome=0, position_usd=10.0)
    assert abs(pnl - (-10.0)) < 1e-6


def test_pnl_no_wins():
    # Buy NO at (1-0.40)=0.60 with $12 → 20 shares. NO wins → $20 - $12 = +$8
    pnl = _pnl_for_binary(side="NO", entry_price=0.40, outcome=0, position_usd=12.0)
    assert abs(pnl - 8.0) < 1e-6


def test_pnl_no_loses():
    pnl = _pnl_for_binary(side="NO", entry_price=0.40, outcome=1, position_usd=12.0)
    assert abs(pnl - (-12.0)) < 1e-6


def test_pnl_zero_position():
    assert _pnl_for_binary(side="YES", entry_price=0.5, outcome=1, position_usd=0.0) == 0.0


# ── compute_pnl with mocked outcome_lookup ──────────────────────────


def test_compute_pnl_pass_decision_is_zero():
    d = Decision(
        market_id="x", platform="kalshi", ticker="x", question="?",
        decision="PASS", side="", position_usd=0.0,
        p_yes=0.5, entry_price=0.5, decided_at="2026-05-11T09:00:00+00:00",
    )
    rows = compute_pnl([d], outcome_lookup=lambda *a: 1)
    assert len(rows) == 1
    assert rows[0].realized_pnl_usd == 0.0
    assert rows[0].settled is False


def test_compute_pnl_settled_yes_winner_with_brier():
    d = Decision(
        market_id="x", platform="kalshi", ticker="x", question="?",
        decision="PAPER-TRADE", side="YES", position_usd=10.0,
        p_yes=0.7, entry_price=0.5, decided_at="2026-05-11T09:00:00+00:00",
    )
    rows = compute_pnl([d], outcome_lookup=lambda *a: 1)
    assert rows[0].settled is True
    assert abs(rows[0].realized_pnl_usd - 10.0) < 1e-6
    # Brier = (0.7 - 1)^2 = 0.09
    assert abs(rows[0].brier - 0.09) < 1e-6


def test_compute_pnl_unresolved_is_open():
    d = Decision(
        market_id="x", platform="kalshi", ticker="x", question="?",
        decision="PAPER-TRADE", side="YES", position_usd=10.0,
        p_yes=0.6, entry_price=0.5, decided_at="2026-05-11T09:00:00+00:00",
    )
    rows = compute_pnl([d], outcome_lookup=lambda *a: None)
    assert rows[0].settled is False
    assert rows[0].realized_pnl_usd == 0.0
    assert rows[0].brier is None
