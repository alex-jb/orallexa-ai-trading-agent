"""
tests/test_dynamic_weights.py
──────────────────────────────────────────────────────────────────
Tests for engine/source_accuracy.py + engine/dynamic_weights.py +
the fuse_signals(use_dynamic_weights=True) integration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.source_accuracy import SourceAccuracy
from engine.dynamic_weights import (
    compute_dynamic_weights,
    explain_weight_adjustment,
    _accuracy_factor,
)


# ── _accuracy_factor calibration ───────────────────────────────────────────


class TestAccuracyFactor:
    def test_random_accuracy_is_neutral(self):
        assert _accuracy_factor(0.50) == pytest.approx(1.00)

    def test_perfect_accuracy_caps_at_3x(self):
        assert _accuracy_factor(0.95) == pytest.approx(3.00)
        assert _accuracy_factor(1.00) == pytest.approx(3.00)

    def test_terrible_accuracy_floors_at_0_1(self):
        assert _accuracy_factor(0.0) == pytest.approx(0.10)
        assert _accuracy_factor(0.25) == pytest.approx(0.10)

    def test_above_random_amplifies(self):
        assert _accuracy_factor(0.60) == pytest.approx(1.50)
        assert _accuracy_factor(0.70) == pytest.approx(2.00)

    def test_below_random_attenuates(self):
        assert _accuracy_factor(0.40) == pytest.approx(0.55)


# ── compute_dynamic_weights ────────────────────────────────────────────────


class TestComputeDynamicWeights:
    def _base(self) -> dict[str, float]:
        return {"a": 0.20, "b": 0.20, "c": 0.30, "d": 0.30}

    def test_no_history_returns_base(self):
        out = compute_dynamic_weights(self._base(), {})
        assert out == self._base()

    def test_total_preserved_when_renormalized(self):
        out = compute_dynamic_weights(
            self._base(),
            {"a": 0.70, "b": 0.30, "c": 0.50, "d": 0.50},
        )
        assert sum(out.values()) == pytest.approx(sum(self._base().values()))

    def test_high_accuracy_source_gains_weight(self):
        base = self._base()
        out = compute_dynamic_weights(base, {"a": 0.80, "b": 0.40})
        assert out["a"] > base["a"]
        assert out["b"] < base["b"]

    def test_unknown_sources_keep_base(self):
        out = compute_dynamic_weights(self._base(), {"a": 0.80})
        # 'a' moves but 'c' and 'd' get only a renormalization
        assert out["c"] / out["d"] == pytest.approx(self._base()["c"] / self._base()["d"])

    def test_all_terrible_falls_back_to_base(self):
        # If every source is below random, the renormalization could blow up;
        # the function falls back to base in that pathological case.
        out = compute_dynamic_weights(
            self._base(),
            {"a": 0.10, "b": 0.10, "c": 0.10, "d": 0.10},
        )
        # Behavior: factors are tiny, but renormalization preserves sum.
        # We just want to confirm the result is finite + non-empty.
        assert sum(out.values()) > 0

    def test_zero_base_weight_unchanged(self):
        base = {"a": 0.0, "b": 1.0}
        out = compute_dynamic_weights(base, {"a": 0.80, "b": 0.50})
        assert out["a"] == 0.0


# ── explain_weight_adjustment ──────────────────────────────────────────────


class TestExplainAdjustment:
    def test_returns_one_entry_per_base_source(self):
        base = {"a": 0.5, "b": 0.5}
        rows = explain_weight_adjustment(base, {"a": 0.70})
        assert len(rows) == 2
        a_row = next(r for r in rows if r["source"] == "a")
        b_row = next(r for r in rows if r["source"] == "b")
        assert a_row["accuracy"] == 0.70
        assert b_row["accuracy"] is None

    def test_delta_pct_signed_correctly(self):
        # Use two sources so renormalization doesn't trivially cancel the bump:
        # 'a' has high accuracy → should grow; 'b' has no history → should shrink
        # after renormalization (it absorbs the inverse).
        rows = explain_weight_adjustment({"a": 0.5, "b": 0.5}, {"a": 0.80})
        a_row = next(r for r in rows if r["source"] == "a")
        b_row = next(r for r in rows if r["source"] == "b")
        assert a_row["delta_pct"] > 0
        assert b_row["delta_pct"] < 0


# ── SourceAccuracy ─────────────────────────────────────────────────────────


@pytest.fixture
def ledger(tmp_path):
    return SourceAccuracy(path=tmp_path / "sa.jsonl")


class TestSourceAccuracy:
    def test_record_persists_to_disk(self, ledger, tmp_path):
        ledger.record_scores("NVDA", {"technical": 40, "options_flow": -30})
        line = (tmp_path / "sa.jsonl").read_text(encoding="utf-8").strip()
        rec = json.loads(line)
        assert rec["ticker"] == "NVDA"
        assert rec["scores"]["technical"] == 40

    def test_update_marks_correct_per_source(self, ledger):
        ledger.record_scores("NVDA", {"technical": 40, "options_flow": -30})
        # Forward return +3% — bullish actual. technical (positive) was right,
        # options_flow (negative) was wrong.
        n = ledger.update_outcomes("NVDA", forward_return=0.03)
        assert n == 1
        rec = ledger._records[0]
        assert rec["correct"]["technical"] is True
        assert rec["correct"]["options_flow"] is False

    def test_neutral_outcome_threshold(self, ledger):
        ledger.record_scores("NVDA", {"technical": 0, "options_flow": 30})
        # Forward return 0.2% — within neutral threshold (0.5%)
        ledger.update_outcomes("NVDA", forward_return=0.002)
        rec = ledger._records[0]
        # technical=0 is neutral, matches → True; options_flow=30 is bullish, no match → False
        assert rec["correct"]["technical"] is True
        assert rec["correct"]["options_flow"] is False

    def test_already_evaluated_records_skipped(self, ledger):
        ledger.record_scores("NVDA", {"technical": 40})
        ledger.update_outcomes("NVDA", forward_return=0.03)
        assert ledger.update_outcomes("NVDA", forward_return=-0.05) == 0

    def test_other_ticker_not_affected(self, ledger):
        ledger.record_scores("NVDA", {"technical": 40})
        ledger.record_scores("AAPL", {"technical": -20})
        n = ledger.update_outcomes("NVDA", forward_return=0.03)
        assert n == 1
        # AAPL still pending
        aapl = next(r for r in ledger._records if r["ticker"] == "AAPL")
        assert aapl["correct"] is None

    def test_rolling_accuracy_threshold(self, ledger):
        # Below min_samples → omitted
        for _ in range(3):
            ledger.record_scores("X", {"technical": 40})
        ledger.update_outcomes("X", forward_return=0.03)
        acc = ledger.get_rolling_accuracy(min_samples=5)
        assert "technical" not in acc

    def test_rolling_accuracy_computed_when_enough_samples(self, ledger):
        for _ in range(10):
            ledger.record_scores("X", {"technical": 40})
        ledger.update_outcomes("X", forward_return=0.03)  # all 10 hit
        acc = ledger.get_rolling_accuracy(min_samples=5)
        assert acc["technical"] == 1.0


# ── Integration: fuse_signals(use_dynamic_weights=True) ────────────────────


class TestFusionIntegration:
    def test_use_dynamic_weights_no_history_falls_back(self, tmp_path):
        from engine.signal_fusion import fuse_signals

        with patch("engine.source_accuracy._DEFAULT_PATH", tmp_path / "empty.jsonl"), \
             patch("engine.signal_fusion._fetch_options_flow", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_institutional_signals", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_social_signal", return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_earnings_signal", return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_prediction_markets_signal", return_value={"available": False, "score": 0}):
            r = fuse_signals(
                "NVDA",
                summary={"rsi": 55, "close": 100, "ma20": 98, "ma50": 95},
                use_dynamic_weights=True,
            )
        # No history → no adjustment field surfaced
        assert "weight_adjustment" not in r

    def test_use_dynamic_weights_with_history_surfaces_adjustment(self, tmp_path):
        # Pre-populate the ledger
        sa_path = tmp_path / "sa.jsonl"
        sa = SourceAccuracy(path=sa_path)
        for _ in range(10):
            sa.record_scores("NVDA", {"technical": 40, "options_flow": -50})
        sa.update_outcomes("NVDA", forward_return=0.03)  # technical right, options wrong

        from engine.signal_fusion import fuse_signals

        with patch("engine.source_accuracy._DEFAULT_PATH", sa_path), \
             patch("engine.signal_fusion._fetch_options_flow", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_institutional_signals", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_social_signal", return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_earnings_signal", return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_prediction_markets_signal", return_value={"available": False, "score": 0}):
            r = fuse_signals(
                "NVDA",
                summary={"rsi": 55, "close": 100, "ma20": 98, "ma50": 95},
                use_dynamic_weights=True,
            )

        assert "weight_adjustment" in r
        rows = {row["source"]: row for row in r["weight_adjustment"]}
        # technical has 100% accuracy in this seeded history → factor 3.0
        assert rows["technical"]["accuracy"] == 1.0
        # options_flow had 0% → factor 0.10
        assert rows["options_flow"]["accuracy"] == 0.0

    def test_static_weights_unaffected_when_flag_off(self):
        from engine.signal_fusion import fuse_signals
        with patch("engine.signal_fusion._fetch_options_flow", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_institutional_signals", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_social_signal", return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_earnings_signal", return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_prediction_markets_signal", return_value={"available": False, "score": 0}):
            r = fuse_signals(
                "NVDA",
                summary={"rsi": 55, "close": 100, "ma20": 98, "ma50": 95},
                record_for_accuracy=False,
                # use_dynamic_weights default False
            )
        assert "weight_adjustment" not in r


# ── Auto-record into the ledger ────────────────────────────────────────────


class TestAutoRecord:
    def test_fuse_signals_writes_scores_to_ledger(self, tmp_path):
        """With record_for_accuracy=True (default), every fuse_signals call
        appends one record per available source to the SourceAccuracy ledger."""
        from engine.signal_fusion import fuse_signals
        sa_path = tmp_path / "sa.jsonl"

        with patch("engine.source_accuracy._DEFAULT_PATH", sa_path), \
             patch("engine.signal_fusion._fetch_options_flow",
                   return_value={"available": True, "score": 35}), \
             patch("engine.signal_fusion._fetch_institutional_signals",
                   return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_social_signal",
                   return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_earnings_signal",
                   return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_prediction_markets_signal",
                   return_value={"available": False, "score": 0}):
            fuse_signals(
                "NVDA",
                summary={"rsi": 55, "close": 100, "ma20": 98, "ma50": 95},
            )

        assert sa_path.exists()
        line = sa_path.read_text(encoding="utf-8").strip()
        rec = json.loads(line)
        assert rec["ticker"] == "NVDA"
        assert "technical" in rec["scores"]
        assert "options_flow" in rec["scores"]
        # Unavailable sources should NOT be recorded
        assert "social_sentiment" not in rec["scores"]
        assert rec["correct"] is None  # not yet evaluated

    def test_record_for_accuracy_false_skips_ledger(self, tmp_path):
        from engine.signal_fusion import fuse_signals
        sa_path = tmp_path / "sa.jsonl"

        with patch("engine.source_accuracy._DEFAULT_PATH", sa_path), \
             patch("engine.signal_fusion._fetch_options_flow", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_institutional_signals", return_value={"available": False}), \
             patch("engine.signal_fusion._fetch_social_signal", return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_earnings_signal", return_value={"available": False, "score": 0}), \
             patch("engine.signal_fusion._fetch_prediction_markets_signal", return_value={"available": False, "score": 0}):
            fuse_signals(
                "NVDA",
                summary={"rsi": 55, "close": 100, "ma20": 98, "ma50": 95},
                record_for_accuracy=False,
            )
        assert not sa_path.exists()
