"""
tests/test_multimodal_eval_harness.py
──────────────────────────────────────────────────────────────────
Day 7 multimodal eval harness — covers both
scripts/build_multimodal_eval_set.py and scripts/eval_multimodal_lift.py.

No yfinance / no LLM. Synthetic eval-set generator is exercised
directly; the lift evaluator is run on hand-built rows so the
math is easy to inspect.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.build_multimodal_eval_set import (
    extract_pairs_from_log,
    synthesize_eval_set,
)
from scripts.eval_multimodal_lift import (
    decide,
    evaluate,
    filter_eligible,
    load_eval_set,
)


# ── Synthesizer ──────────────────────────────────────────────────────────


class TestSynthesizeEvalSet:
    def test_returns_n_rows(self):
        rows = synthesize_eval_set(50, seed=1)
        assert len(rows) == 50

    def test_deterministic(self):
        a = synthesize_eval_set(40, seed=99)
        b = synthesize_eval_set(40, seed=99)
        assert a == b

    def test_different_seed_changes_rows(self):
        a = synthesize_eval_set(30, seed=1)
        b = synthesize_eval_set(30, seed=2)
        assert a != b

    def test_all_rows_eligible_with_truth(self):
        rows = synthesize_eval_set(60, seed=3)
        valid_truths = {"BUY", "SELL", "WAIT"}
        for r in rows:
            assert r["eligible"] is True
            assert r["synthetic"] is True
            assert r["ground_truth"] in valid_truths
            assert r["text_bias"] in {"BULLISH", "BEARISH", "NEUTRAL"}
            assert r["vision_bias"] in {"BULLISH", "BEARISH", "NEUTRAL"}
            assert r["role"] == "Quant Researcher"

    def test_distribution_includes_both_modes(self):
        # 200 rows: ~40% agree-correct, ~30% vision-only-correct,
        # ~30% text-only-correct. All three buckets must be present.
        rows = synthesize_eval_set(200, seed=7)
        agree_count = sum(1 for r in rows if r["text_bias"] == r["vision_bias"])
        disagree_count = len(rows) - agree_count
        assert agree_count > 0
        assert disagree_count > 0


# ── extract_pairs_from_log ───────────────────────────────────────────────


class TestExtractPairsFromLog:
    def _log_record(self, ticker, ts_iso, *, with_diff=True, n_pairs=1):
        rec = {"ticker": ticker, "timestamp": ts_iso, "extra": {}}
        if with_diff:
            rec["extra"]["multimodal_diff"] = {
                "pairs": [
                    {
                        "role": f"Role{i}",
                        "text":   {"bias": "BULLISH", "score": 30, "conviction": 60,
                                   "reasoning": ""},
                        "vision": {"bias": "BEARISH", "score": -20, "conviction": 55,
                                   "reasoning": ""},
                        "agree": False, "score_delta": -50, "conviction_delta": -5,
                    }
                    for i in range(n_pairs)
                ],
                "n_pairs": n_pairs,
            }
        return rec

    def test_extracts_one_row_per_pair(self):
        records = [
            self._log_record("NVDA", "2026-04-01T10:00:00", n_pairs=2),
            self._log_record("AAPL", "2026-04-02T10:00:00", n_pairs=1),
        ]
        cutoff = datetime(2026, 4, 27)
        pairs = extract_pairs_from_log(records, cutoff)
        # 2 pairs from NVDA + 1 from AAPL
        assert len(pairs) == 3
        tickers = [p["ticker"] for p in pairs]
        assert tickers.count("NVDA") == 2
        assert tickers.count("AAPL") == 1

    def test_skips_records_without_multimodal_diff(self):
        records = [self._log_record("NVDA", "2026-04-01T10:00:00", with_diff=False)]
        pairs = extract_pairs_from_log(records, datetime(2026, 4, 27))
        assert pairs == []

    def test_skips_records_past_cutoff(self):
        # Cutoff 2026-04-01 — record from 2026-04-15 is too recent.
        records = [self._log_record("NVDA", "2026-04-15T10:00:00", n_pairs=1)]
        pairs = extract_pairs_from_log(records, datetime(2026, 4, 1))
        assert pairs == []

    def test_handles_malformed_extra(self):
        records = [
            {"ticker": "X", "timestamp": "2026-04-01T10:00:00", "extra": "not a dict"},
            {"ticker": "Y", "timestamp": "2026-04-01T10:00:00",
             "extra": {"multimodal_diff": "not a dict"}},
        ]
        pairs = extract_pairs_from_log(records, datetime(2026, 4, 27))
        assert pairs == []

    def test_handles_missing_text_or_vision(self):
        rec = {
            "ticker": "X", "timestamp": "2026-04-01T10:00:00",
            "extra": {"multimodal_diff": {"pairs": [
                {"role": "Quant", "text": {}, "vision": {}}  # both empty
            ]}},
        }
        pairs = extract_pairs_from_log([rec], datetime(2026, 4, 27))
        assert pairs == []


# ── load + filter eligible ───────────────────────────────────────────────


class TestLoadAndFilter:
    def test_load_skips_blank_and_malformed_lines(self, tmp_path):
        p = tmp_path / "x.jsonl"
        p.write_text(
            '{"text_bias":"BULLISH","vision_bias":"BEARISH",'
            '"ground_truth":"BUY","eligible":true}\n'
            "\n"
            "garbage-not-json\n"
            '{"text_bias":"NEUTRAL","vision_bias":"NEUTRAL",'
            '"ground_truth":"WAIT","eligible":true}\n',
            encoding="utf-8",
        )
        rows = load_eval_set(p)
        assert len(rows) == 2

    def test_filter_drops_ineligible_or_missing_fields(self):
        rows = [
            {"text_bias": "BULLISH", "vision_bias": "BEARISH",
             "ground_truth": "BUY", "eligible": True},
            {"text_bias": "BULLISH", "vision_bias": "BEARISH",
             "ground_truth": "BUY", "eligible": False},
            {"text_bias": "BULLISH", "vision_bias": "BEARISH",
             "ground_truth": None, "eligible": True},
            {"text_bias": None, "vision_bias": "BEARISH",
             "ground_truth": "BUY", "eligible": True},
            {"text_bias": "NEUTRAL", "vision_bias": "NEUTRAL",
             "ground_truth": "INVALID", "eligible": True},
        ]
        kept = filter_eligible(rows)
        assert len(kept) == 1


# ── evaluate (the math) ──────────────────────────────────────────────────


class TestEvaluate:
    def _row(self, text, vision, truth):
        return {"text_bias": text, "vision_bias": vision, "ground_truth": truth,
                "eligible": True}

    def test_empty_returns_zero_shape(self):
        m = evaluate([])
        assert m["n"] == 0
        assert m["text_accuracy"] == 0.0
        assert m["vision_accuracy"] == 0.0
        assert m["absolute_lift"] == 0.0

    def test_all_correct_both_modalities(self):
        rows = [
            self._row("BULLISH", "BULLISH", "BUY"),
            self._row("BEARISH", "BEARISH", "SELL"),
            self._row("NEUTRAL", "NEUTRAL", "WAIT"),
        ]
        m = evaluate(rows)
        assert m["text_accuracy"] == 1.0
        assert m["vision_accuracy"] == 1.0
        assert m["absolute_lift"] == 0.0
        assert m["agreement_rate"] == 1.0

    def test_vision_wins_when_text_wrong(self):
        rows = [
            self._row("BULLISH", "BEARISH", "SELL"),    # vision right
            self._row("BULLISH", "BEARISH", "SELL"),    # vision right
            self._row("BULLISH", "BULLISH", "BUY"),     # both right
        ]
        m = evaluate(rows)
        assert m["text_accuracy"] == round(1 / 3, 4)
        assert m["vision_accuracy"] == 1.0
        assert m["absolute_lift"] > 0.5

    def test_per_class_breakdown(self):
        rows = [
            self._row("BULLISH", "BULLISH", "BUY"),
            self._row("BULLISH", "BEARISH", "BUY"),  # vision wrong on BUY class
            self._row("BEARISH", "BEARISH", "SELL"),
        ]
        m = evaluate(rows)
        per = m["per_class"]
        assert per["BUY"]["n"] == 2
        assert per["BUY"]["text_accuracy"] == 1.0
        assert per["BUY"]["vision_accuracy"] == 0.5
        assert per["SELL"]["n"] == 1
        assert per["WAIT"]["n"] == 0


# ── decide (verdict logic) ───────────────────────────────────────────────


class TestDecide:
    def _metrics(self, *, n, text_acc, vision_acc):
        return {
            "n": n, "text_accuracy": text_acc, "vision_accuracy": vision_acc,
            "absolute_lift": vision_acc - text_acc,
        }

    def test_no_data(self):
        assert decide(self._metrics(n=0, text_acc=0, vision_acc=0),
                      ship_threshold=0.05, min_n=50) == "no_eval_data"

    def test_below_min_n(self):
        m = self._metrics(n=20, text_acc=0.5, vision_acc=0.7)
        assert decide(m, ship_threshold=0.05, min_n=50) == "below_threshold"

    def test_text_better_rejects(self):
        m = self._metrics(n=80, text_acc=0.7, vision_acc=0.6)
        assert decide(m, ship_threshold=0.05, min_n=50) == "reject_text_better"

    def test_lift_below_gate_rejects(self):
        m = self._metrics(n=80, text_acc=0.65, vision_acc=0.68)
        assert decide(m, ship_threshold=0.05, min_n=50) == "reject_no_lift"

    def test_clears_gate_ships(self):
        m = self._metrics(n=80, text_acc=0.60, vision_acc=0.72)
        assert decide(m, ship_threshold=0.05, min_n=50) == "ship"

    def test_threshold_is_inclusive(self):
        # Lift exactly equal to threshold should ship.
        m = self._metrics(n=80, text_acc=0.60, vision_acc=0.65)
        assert decide(m, ship_threshold=0.05, min_n=50) == "ship"


# ── End-to-end synthetic flow ────────────────────────────────────────────


class TestEndToEnd:
    def test_synthesizer_flows_to_evaluate(self):
        rows = synthesize_eval_set(150, seed=7)
        kept = filter_eligible(rows)
        assert len(kept) == 150
        m = evaluate(kept)
        # Synthesizer is rigged so vision wins ~30% extra → lift > 0.
        assert m["absolute_lift"] > 0
        # And the verdict at default thresholds should be ship.
        assert decide(m, ship_threshold=0.05, min_n=50) == "ship"
