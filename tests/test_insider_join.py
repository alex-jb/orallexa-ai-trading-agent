"""Tests for markets/auto/insider_join.py — adapter wiring
engine.insider_signal into the SpaceX-tracker daily pipeline."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import pytest  # noqa: E402

from markets.auto.insider_join import (  # noqa: E402
    append_insider_history,
    enrich_decision_with_insider,
    render_insider_inline,
    render_insider_section,
)


TODAY = date(2026, 6, 22)


def _ev(ticker, ago_days, position, direction, value, insider=""):
    return {
        "ticker": ticker,
        "date": (TODAY - timedelta(days=ago_days)).isoformat(),
        "position": position,
        "direction": direction,
        "shares": int(value / 100),
        "value_usd": value,
        "insider": insider,
    }


def _baseline_decision(ticker="ASTS", p_up=0.55, p_down=0.30):
    """Mimic the per-ticker decision payload spacex-daily emits."""
    return {
        "ticker": ticker,
        "signal_label": "BUY",
        "conviction_pct": 49.2,
        "up_probability": p_up,
        "down_probability": p_down,
    }


# ──────────────────────────────────────────────────────────────────
# enrich_decision_with_insider — core integration
# ──────────────────────────────────────────────────────────────────

class TestEnrichDecision:

    def test_no_events_passes_zero_fields(self):
        out = enrich_decision_with_insider(
            ticker="ASTS",
            decision=_baseline_decision(),
            insider_events=[],
            today=TODAY,
        )
        assert out["insider_events_n"] == 0
        assert out["insider_p_up_delta"] == 0.0
        assert out["insider_cluster"] is False
        # Original p_up should be preserved
        assert out["up_probability"] == 0.55

    def test_cfo_sale_shifts_p_up_down(self):
        events = [_ev("ASTS", 11, "Chief Financial Officer",
                      "sale", 430_000, "Andrew Johnson")]
        out = enrich_decision_with_insider(
            ticker="ASTS",
            decision=_baseline_decision("ASTS", 0.55, 0.30),
            insider_events=events,
            today=TODAY,
        )
        assert out["insider_events_n"] == 1
        assert out["insider_p_up_delta"] < 0
        # Mass conservation: pre + post should sum to same total
        assert (
            abs(
                (out["up_probability"] + out["down_probability"])
                - (out["p_up_pre_insider"] + out["p_down_pre_insider"])
            ) < 1e-6
        )
        # p_up should have dropped
        assert out["up_probability"] < out["p_up_pre_insider"]

    def test_cluster_flag_propagates(self):
        events = [
            _ev("BKSY", 12, "Chief Executive Officer",
                "sale", 500_000, "Brian O'Toole"),
            _ev("BKSY", 12, "Chief Financial Officer",
                "sale", 500_000, "Henry DuBois"),
        ]
        out = enrich_decision_with_insider(
            ticker="BKSY",
            decision=_baseline_decision("BKSY"),
            insider_events=events,
            today=TODAY,
        )
        assert out["insider_cluster"] is True
        assert out["insider_events_n"] == 2

    def test_rationale_bullets_propagate(self):
        events = [_ev("ASTS", 11, "Chief Financial Officer",
                      "sale", 430_000, "Andrew Johnson")]
        out = enrich_decision_with_insider(
            ticker="ASTS",
            decision=_baseline_decision("ASTS"),
            insider_events=events,
            today=TODAY,
        )
        assert isinstance(out["insider_rationale"], list)
        assert len(out["insider_rationale"]) >= 1

    def test_does_not_mutate_input(self):
        events = [_ev("ASTS", 11, "CFO", "sale", 430_000)]
        base = _baseline_decision("ASTS")
        base_copy = dict(base)
        enrich_decision_with_insider(
            ticker="ASTS",
            decision=base,
            insider_events=events,
            today=TODAY,
        )
        assert base == base_copy

    def test_apply_to_p_up_false_skips_mass_shift(self):
        events = [_ev("ASTS", 11, "CFO", "sale", 430_000)]
        out = enrich_decision_with_insider(
            ticker="ASTS",
            decision=_baseline_decision("ASTS", 0.55, 0.30),
            insider_events=events,
            today=TODAY,
            apply_to_p_up=False,
        )
        # insider fields still added, but p_up untouched
        assert out["insider_p_up_delta"] < 0
        assert out["up_probability"] == 0.55
        assert "p_up_pre_insider" not in out


# ──────────────────────────────────────────────────────────────────
# Markdown rendering
# ──────────────────────────────────────────────────────────────────

class TestRendering:

    def test_render_inline_empty_for_zero_events(self):
        d = _baseline_decision()
        d.update({"insider_events_n": 0, "insider_p_up_delta": 0.0,
                  "insider_cluster": False})
        assert render_insider_inline(d) == ""

    def test_render_inline_negative_delta(self):
        d = _baseline_decision()
        d.update({"insider_events_n": 1, "insider_p_up_delta": -0.04,
                  "insider_cluster": False})
        s = render_insider_inline(d)
        assert "Δp(up) -0.040" in s
        assert "n=1" in s
        assert "🚨" not in s

    def test_render_inline_cluster_emoji(self):
        d = _baseline_decision()
        d.update({"insider_events_n": 2, "insider_p_up_delta": -0.13,
                  "insider_cluster": True})
        s = render_insider_inline(d)
        assert "🚨" in s

    def test_render_section_omits_zero_event_tickers(self):
        ds = [
            ("ASTS", {"insider_events_n": 1, "insider_p_up_delta": -0.04,
                      "insider_cluster": False, "insider_rationale": ["CFO sale"]}),
            ("LIN",  {"insider_events_n": 0, "insider_p_up_delta": 0.0,
                      "insider_cluster": False, "insider_rationale": []}),
        ]
        s = render_insider_section(ds)
        assert "ASTS" in s
        assert "LIN" not in s

    def test_render_section_empty_when_no_flagged(self):
        ds = [("LIN", {"insider_events_n": 0})]
        s = render_insider_section(ds)
        assert s == ""


# ──────────────────────────────────────────────────────────────────
# Sidecar JSONL
# ──────────────────────────────────────────────────────────────────

class TestHistoryAppend:

    def test_append_creates_file_and_writes_row(self, tmp_path):
        path = tmp_path / "subdir" / "insider_history.jsonl"
        enriched = {
            "p_up_pre_insider": 0.55,
            "up_probability": 0.51,
            "insider_p_up_delta": -0.04,
            "insider_events_n": 1,
            "insider_cluster": False,
        }
        append_insider_history(
            path,
            date_str="2026-06-22",
            ticker="ASTS",
            enriched_decision=enriched,
        )
        assert path.exists()
        line = path.read_text().strip()
        rec = json.loads(line)
        assert rec["ticker"] == "ASTS"
        assert rec["date"] == "2026-06-22"
        assert rec["decision_id"] == "2026-06-22-ASTS"
        assert rec["insider_p_up_delta"] == -0.04

    def test_append_appends_not_overwrites(self, tmp_path):
        path = tmp_path / "h.jsonl"
        for i, ticker in enumerate(["ASTS", "BKSY", "TSLA"]):
            append_insider_history(
                path,
                date_str="2026-06-22",
                ticker=ticker,
                enriched_decision={"insider_p_up_delta": -0.01 * (i + 1)},
            )
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 3
        tickers = [json.loads(l)["ticker"] for l in lines]
        assert tickers == ["ASTS", "BKSY", "TSLA"]
