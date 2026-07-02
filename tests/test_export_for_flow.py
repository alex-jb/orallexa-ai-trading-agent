"""Tests for markets/auto/export_for_flow.py — covers brief parsing,
sector lookup, p_up translation, insider-signal join, sidecar JSON."""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import pytest  # noqa: E402

from markets.auto.export_for_flow import (  # noqa: E402
    BRIEF_ROW_RE,
    CSV_COLUMNS,
    SCHEMA_VERSION,
    SECTOR_LOOKUP,
    _conv_to_p_up,
    build_rows,
    load_insider_events,
    parse_brief,
    write_csv,
    write_sidecar_json,
)


# ────────────────────────────────────────────────────────────────────
# Fixture brief content — mirrors the actual spacex-daily/*.md table
# ────────────────────────────────────────────────────────────────────

FIXTURE_BRIEF = """---
date: 2026-06-22
---
# Daily SpaceX Tracker — 2026-06-22

Some narrative text above.

## §3 SpaceX 跟踪

| Rank | Sector | Ticker | Decision | Conf | Δ probs | RSI |
|---|---|---|---|---|---|---|
| 1 | 🛰 | LIN | BUY | 49.2% | +0.38 | 61.0 |
| 2 | 🛰 | LMT | WAIT | 42.6% | -0.05 | 42.0 |
| 3 | 🤖 | TSLA | SELL | 47.6% | -0.28 | 38.6 |
| 4 | 🧠 | NVDA | SELL | 45.1% | -0.20 | 49.7 |
| 5 | 🚁 | KTOS | SELL | 50.8% | -0.42 | 32.1 |

Some footer text.
"""


@pytest.fixture
def tmp_brief(tmp_path):
    p = tmp_path / "2026-06-22.md"
    p.write_text(FIXTURE_BRIEF, encoding="utf-8")
    return p


# ────────────────────────────────────────────────────────────────────
# Row regex + parse_brief
# ────────────────────────────────────────────────────────────────────

class TestBriefParse:

    def test_regex_matches_basic_row(self):
        m = BRIEF_ROW_RE.match("| 1 | 🛰 | LIN | BUY | 49.2% | +0.38 | 61.0 |")
        assert m is not None
        d = m.groupdict()
        assert d["ticker"] == "LIN"
        assert d["decision"] == "BUY"
        assert float(d["conv"]) == 49.2
        assert float(d["delta"]) == 0.38

    def test_regex_handles_negative_delta(self):
        m = BRIEF_ROW_RE.match("| 3 | 🤖 | TSLA | SELL | 47.6% | -0.28 | 38.6 |")
        assert m is not None
        assert float(m.group("delta")) == -0.28

    def test_parse_brief_returns_date_and_rows(self, tmp_brief):
        brief_date, rows = parse_brief(tmp_brief)
        assert brief_date == date(2026, 6, 22)
        assert len(rows) == 5
        assert rows[0]["ticker"] == "LIN"
        assert rows[0]["decision"] == "BUY"
        assert rows[2]["ticker"] == "TSLA"

    def test_parse_brief_handles_no_table(self, tmp_path):
        p = tmp_path / "2026-05-01.md"
        p.write_text("just plain text, no table", encoding="utf-8")
        brief_date, rows = parse_brief(p)
        assert brief_date == date(2026, 5, 1)
        assert rows == []


# ────────────────────────────────────────────────────────────────────
# Sector lookup
# ────────────────────────────────────────────────────────────────────

class TestSectorLookup:

    def test_all_14_tickers_have_sector(self):
        watchlist = ["RKLB", "ASTS", "LUNR", "BKSY", "PL", "RDW", "LMT", "LIN",
                     "TSLA", "SYM", "NVDA", "AVGO", "AVAV", "KTOS"]
        for t in watchlist:
            assert t in SECTOR_LOOKUP

    def test_unknown_ticker_lookup_returns_none_emoji(self):
        # Not in dict — caller should default to "❓ Unknown"
        assert "FOO" not in SECTOR_LOOKUP


# ────────────────────────────────────────────────────────────────────
# Decision → p_up translation
# ────────────────────────────────────────────────────────────────────

class TestConvToProb:

    def test_buy_high_conv_tilts_up(self):
        assert _conv_to_p_up("BUY", 80.0) > 0.85

    def test_sell_high_conv_tilts_down(self):
        assert _conv_to_p_up("SELL", 80.0) < 0.15

    def test_wait_stays_near_neutral(self):
        assert 0.45 < _conv_to_p_up("WAIT", 50.0) < 0.55

    def test_buy_zero_conv_is_neutral(self):
        assert _conv_to_p_up("BUY", 0.0) == 0.5

    def test_clamps_high_conv(self):
        assert 0 <= _conv_to_p_up("BUY", 150.0) <= 1


# ────────────────────────────────────────────────────────────────────
# Insider join
# ────────────────────────────────────────────────────────────────────

class TestInsiderJoin:

    def test_load_insider_events_groups_by_ticker(self, tmp_path):
        p = tmp_path / "insider.jsonl"
        p.write_text(
            '{"ticker": "ASTS", "date": "2026-06-11", "position": "CFO", "direction": "sale", "value_usd": 430000}\n'
            '{"ticker": "BKSY", "date": "2026-06-10", "position": "CEO", "direction": "sale", "value_usd": 500000}\n'
            '{"ticker": "ASTS", "date": "2026-06-09", "position": "Director", "direction": "sale", "value_usd": 100000}\n',
            encoding="utf-8",
        )
        grouped = load_insider_events(p)
        assert "ASTS" in grouped and len(grouped["ASTS"]) == 2
        assert "BKSY" in grouped and len(grouped["BKSY"]) == 1

    def test_load_insider_events_empty_when_missing(self):
        assert load_insider_events(None) == {}

    def test_load_insider_events_handles_corrupt_lines(self, tmp_path):
        p = tmp_path / "insider.jsonl"
        p.write_text(
            '{"ticker": "X", "date": "2026-06-11"}\n'
            'NOT JSON AT ALL\n'
            '{"ticker": "Y", "date": "2026-06-12"}\n',
            encoding="utf-8",
        )
        grouped = load_insider_events(p)
        assert set(grouped.keys()) == {"X", "Y"}


# ────────────────────────────────────────────────────────────────────
# End-to-end build_rows + CSV/JSON writers
# ────────────────────────────────────────────────────────────────────

class TestEndToEnd:

    def test_build_rows_emits_one_per_table_row(self, tmp_brief):
        rows = list(build_rows(
            briefs_dir=tmp_brief.parent,
            since=None,
            insider_jsonl=None,
            price_jsonl=None,
        ))
        assert len(rows) == 5
        tickers = [r["ticker"] for r in rows]
        assert "LIN" in tickers
        assert "TSLA" in tickers

    def test_build_rows_respects_since(self, tmp_brief):
        rows = list(build_rows(
            briefs_dir=tmp_brief.parent,
            since=date(2026, 6, 23),  # AFTER fixture brief date
            insider_jsonl=None,
            price_jsonl=None,
        ))
        assert rows == []

    def test_csv_written_with_expected_columns(self, tmp_brief, tmp_path):
        rows = list(build_rows(
            briefs_dir=tmp_brief.parent,
            since=None,
            insider_jsonl=None,
            price_jsonl=None,
        ))
        out = tmp_path / "out.csv"
        n = write_csv(rows, out)
        assert n == 5
        # Re-read + verify schema
        with out.open() as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == CSV_COLUMNS
            data = list(reader)
        assert len(data) == 5
        assert data[0]["ticker"] == "LIN"
        assert data[0]["sector_emoji"] == "🛰"
        assert data[0]["decision_id"] == "2026-06-22-LIN"

    def test_sidecar_json_carries_schema_and_render_hints(self, tmp_brief, tmp_path):
        rows = list(build_rows(
            briefs_dir=tmp_brief.parent,
            since=None,
            insider_jsonl=None,
            price_jsonl=None,
        ))
        out = tmp_path / "out.sidecar.json"
        write_sidecar_json(rows, out)
        payload = json.loads(out.read_text())
        assert payload["schema_version"] == SCHEMA_VERSION
        assert payload["render_hints"]["x_axis"] == "date"
        assert payload["render_hints"]["color_by"] == "sector_emoji"
        assert len(payload["rows"]) == 5

    def test_insider_join_zeroes_when_no_events(self, tmp_brief, tmp_path):
        rows = list(build_rows(
            briefs_dir=tmp_brief.parent,
            since=None,
            insider_jsonl=None,
            price_jsonl=None,
        ))
        for r in rows:
            assert r["insider_p_up_delta"] == 0.0
            assert r["insider_events_n"] == 0
            assert r["insider_cluster"] == 0

    def test_insider_join_applies_signal(self, tmp_brief, tmp_path):
        # Fixture brief has TSLA SELL — give it an insider sale event
        # and verify the join flips through with a non-zero p_up_delta
        insider = tmp_path / "insider.jsonl"
        insider.write_text(
            '{"ticker": "TSLA", "date": "2026-06-18", "position": "Chief Executive Officer", "direction": "sale", "value_usd": 1000000, "insider": "Elon"}\n',
            encoding="utf-8",
        )
        rows = list(build_rows(
            briefs_dir=tmp_brief.parent,
            since=None,
            insider_jsonl=insider,
            price_jsonl=None,
        ))
        tsla = next(r for r in rows if r["ticker"] == "TSLA")
        # CEO sale → negative p_up_delta
        assert tsla["insider_p_up_delta"] < 0
        assert tsla["insider_events_n"] == 1
