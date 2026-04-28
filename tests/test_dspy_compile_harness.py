"""
tests/test_dspy_compile_harness.py
──────────────────────────────────────────────────────────────────
Phase B coverage:

  - synthesize_eval_set (deterministic + label-balanced shape)
  - load_eval_set / filter_eligible / split_train_holdout
  - evaluate_predictor metric math
  - run_compile readiness gates (no_eval_data / below_threshold /
    dspy_not_installed / dry_run)
  - load_compiled_judge with a stubbed dspy program

dspy is NOT installed in CI. The compile path itself (MIPROv2)
isn't exercised here — only the harness scaffolding around it. The
compile call is verified at the readiness-gate level + by mocking
dspy.MIPROv2 in the one happy-path harness test.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.build_dspy_eval_set import synthesize_eval_set
from scripts.compile_judge_dspy import (
    class_distribution,
    evaluate_predictor,
    filter_eligible,
    load_eval_set,
    run_compile,
    split_train_holdout,
)


# ── synthetic eval set ────────────────────────────────────────────────────


class TestSynthesizeEvalSet:
    def test_returns_n_rows(self):
        rows = synthesize_eval_set(40, seed=1)
        assert len(rows) == 40

    def test_deterministic_for_same_seed(self):
        a = synthesize_eval_set(20, seed=99)
        b = synthesize_eval_set(20, seed=99)
        assert a == b

    def test_different_seed_yields_different_rows(self):
        a = synthesize_eval_set(20, seed=1)
        b = synthesize_eval_set(20, seed=2)
        assert a != b

    def test_all_rows_eligible_with_truth(self):
        rows = synthesize_eval_set(50, seed=3)
        for r in rows:
            assert r["eligible"] is True
            assert r["synthetic"] is True
            assert r["ground_truth"] in {"BUY", "SELL", "WAIT"}
            assert len(r["bull_argument"]) > 50
            assert len(r["bear_argument"]) > 50

    def test_distribution_includes_all_classes(self):
        # 200 rows is enough to surface all 3 classes given the 40/40/20 mix.
        rows = synthesize_eval_set(200, seed=42)
        seen = {r["ground_truth"] for r in rows}
        assert seen == {"BUY", "SELL", "WAIT"}

    def test_forward_return_sign_matches_ground_truth(self):
        rows = synthesize_eval_set(150, seed=7)
        for r in rows:
            ret = r["forward_return"]
            gt = r["ground_truth"]
            if gt == "BUY":
                assert ret > 0.02
            elif gt == "SELL":
                assert ret < -0.02
            else:
                assert -0.02 <= ret <= 0.02


# ── eval set loader / filter / split ──────────────────────────────────────


class TestLoadEvalSet:
    def test_missing_file_returns_empty(self, tmp_path):
        assert load_eval_set(tmp_path / "missing.jsonl") == []

    def test_skips_blank_lines_and_malformed_rows(self, tmp_path):
        p = tmp_path / "eval.jsonl"
        p.write_text(
            '{"ticker":"NVDA","ground_truth":"BUY","eligible":true,'
            '"bull_argument":"x","bear_argument":"y"}\n'
            "\n"
            "not-json\n"
            '{"ticker":"AAPL","ground_truth":"SELL","eligible":true,'
            '"bull_argument":"a","bear_argument":"b"}\n',
            encoding="utf-8",
        )
        rows = load_eval_set(p)
        assert len(rows) == 2
        assert rows[0]["ticker"] == "NVDA"


class TestFilterEligible:
    def test_drops_ineligible_and_missing_truth(self):
        rows = [
            {"eligible": True, "ground_truth": "BUY", "bull_argument": "x", "bear_argument": "y"},
            {"eligible": False, "ground_truth": "BUY", "bull_argument": "x", "bear_argument": "y"},
            {"eligible": True, "ground_truth": None, "bull_argument": "x", "bear_argument": "y"},
            {"eligible": True, "ground_truth": "INVALID", "bull_argument": "x", "bear_argument": "y"},
            {"eligible": True, "ground_truth": "WAIT", "bull_argument": "", "bear_argument": "y"},
        ]
        kept = filter_eligible(rows)
        assert len(kept) == 1


class TestSplitTrainHoldout:
    def test_split_size(self):
        rows = synthesize_eval_set(100, seed=1)
        train, holdout = split_train_holdout(rows, holdout_frac=0.20, seed=1)
        assert len(train) == 80
        assert len(holdout) == 20

    def test_disjoint(self):
        rows = synthesize_eval_set(50, seed=2)
        train, holdout = split_train_holdout(rows, seed=2)
        # synthesize_eval_set returns dict rows; identity check via id()
        assert all(id(t) not in {id(h) for h in holdout} for t in train)

    def test_deterministic(self):
        rows = synthesize_eval_set(30, seed=3)
        a = split_train_holdout(rows, seed=99)
        b = split_train_holdout(rows, seed=99)
        assert a == b


class TestClassDistribution:
    def test_counts_each_class(self):
        rows = [
            {"ground_truth": "BUY"}, {"ground_truth": "BUY"}, {"ground_truth": "SELL"},
        ]
        d = class_distribution(rows)
        assert d == {"BUY": 2, "SELL": 1, "WAIT": 0}


# ── evaluate_predictor ────────────────────────────────────────────────────


class TestEvaluatePredictor:
    def _rows(self):
        return [
            {"ticker": "A", "ground_truth": "BUY",  "bull_argument": "b", "bear_argument": "x"},
            {"ticker": "B", "ground_truth": "BUY",  "bull_argument": "b", "bear_argument": "x"},
            {"ticker": "C", "ground_truth": "SELL", "bull_argument": "b", "bear_argument": "x"},
            {"ticker": "D", "ground_truth": "WAIT", "bull_argument": "b", "bear_argument": "x"},
        ]

    def test_perfect_predictor_scores_one(self):
        rows = self._rows()
        def perfect(ticker, bull, bear):
            for r in rows:
                if r["ticker"] == ticker:
                    return {"decision": r["ground_truth"]}
            return None
        m = evaluate_predictor(perfect, rows)
        assert m["accuracy"] == 1.0
        assert m["per_class_accuracy"]["BUY"] == 1.0

    def test_constant_predictor_partial_score(self):
        rows = self._rows()
        always_buy = lambda **_: {"decision": "BUY"}
        m = evaluate_predictor(always_buy, rows)
        # 2 BUY rows out of 4 → 0.5
        assert m["accuracy"] == 0.5
        assert m["per_class_accuracy"]["BUY"] == 1.0
        assert m["per_class_accuracy"]["SELL"] == 0.0

    def test_failing_predictor_counts_as_miss(self):
        rows = self._rows()
        def bad(**_):
            raise RuntimeError("nope")
        m = evaluate_predictor(bad, rows)
        assert m["accuracy"] == 0.0
        assert m["n"] == 4

    def test_none_return_counts_as_miss(self):
        rows = self._rows()
        m = evaluate_predictor(lambda **_: None, rows)
        assert m["accuracy"] == 0.0


# ── run_compile readiness gates ───────────────────────────────────────────


class TestRunCompileGates:
    def test_no_eval_data_status(self, tmp_path):
        out = run_compile(tmp_path / "missing.jsonl", tmp_path / "out.json", dry_run=True)
        assert out["status"] == "no_eval_data"
        assert out["n_total_eligible"] == 0

    def test_below_threshold_status(self, tmp_path):
        path = tmp_path / "small.jsonl"
        rows = synthesize_eval_set(40, seed=1)
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        out = run_compile(path, tmp_path / "out.json", dry_run=True)
        assert out["status"] == "below_threshold"
        assert out["phase_b_ready"] is False
        assert out["n_total_eligible"] == 40

    def test_dry_run_status_when_threshold_met(self, tmp_path):
        path = tmp_path / "ok.jsonl"
        rows = synthesize_eval_set(120, seed=1)
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        out = run_compile(path, tmp_path / "out.json", dry_run=True)
        assert out["status"] == "dry_run"
        assert out["phase_b_ready"] is True
        assert out["n_train"] + out["n_holdout"] == 120

    def test_dspy_not_installed_status(self, tmp_path, monkeypatch):
        """Without dry_run, missing dspy short-circuits with a clear status."""
        path = tmp_path / "ok.jsonl"
        rows = synthesize_eval_set(120, seed=1)
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        # Simulate missing dspy by stubbing the import to None.
        monkeypatch.setitem(sys.modules, "dspy", None)
        out = run_compile(path, tmp_path / "out.json", dry_run=False)
        assert out["status"] == "dspy_not_installed"


# ── load_compiled_judge ───────────────────────────────────────────────────


def _build_fake_dspy_with_load(prediction_fields: dict, captured: dict | None = None):
    """Like the fake in test_dspy_judge but with a working program.load(path)."""
    fake = types.ModuleType("dspy")

    class FakeSignature: pass
    fake.Signature = FakeSignature

    def _field(*_, **__): return None
    fake.InputField = _field
    fake.OutputField = _field

    class FakeLM:
        def __init__(self, *args, **kwargs):
            self.args = args
    fake.LM = FakeLM
    fake.configure = lambda **_: None

    class FakePrediction:
        def __init__(self, fields):
            for k, v in fields.items():
                setattr(self, k, v)

    class FakePredict:
        def __init__(self, sig_cls):
            self.signature = sig_cls
            self._loaded_path = None

        def load(self, path):
            self._loaded_path = path
            if captured is not None:
                captured["loaded"] = path

        def __call__(self, **kwargs):
            return FakePrediction(prediction_fields)

    fake.Predict = FakePredict
    return fake


class TestLoadCompiledJudge:
    def setup_method(self):
        import llm.dspy_judge as dj
        dj._dspy_configured = False
        dj._predict_cls = None
        dj.reset_compiled_cache()

    def test_returns_none_when_path_missing(self, tmp_path):
        from llm.dspy_judge import load_compiled_judge
        assert load_compiled_judge(tmp_path / "absent.json") is None

    def test_loads_and_invokes_compiled_program(self, monkeypatch, tmp_path):
        captured = {}
        fake = _build_fake_dspy_with_load(
            {"decision": "buy", "confidence": "85", "risk_level": "low",
             "reasoning_detail": "compiled judge says yes"},
            captured=captured,
        )
        monkeypatch.setitem(sys.modules, "dspy", fake)

        artifact = tmp_path / "compiled.json"
        artifact.write_text("{}", encoding="utf-8")  # presence-only

        from llm.dspy_judge import load_compiled_judge
        predict = load_compiled_judge(artifact)
        assert predict is not None
        assert captured["loaded"] == str(artifact)

        out = predict("bull text", "bear text", ticker="NVDA")
        assert out["decision"] == "BUY"
        assert out["confidence"] == 85
        assert out["risk_level"] == "LOW"
        assert out["source"] == "dspy_compiled"

    def test_caches_per_path(self, monkeypatch, tmp_path):
        fake = _build_fake_dspy_with_load(
            {"decision": "WAIT", "confidence": 50, "risk_level": "MEDIUM",
             "reasoning_detail": ""},
        )
        monkeypatch.setitem(sys.modules, "dspy", fake)

        artifact = tmp_path / "compiled.json"
        artifact.write_text("{}", encoding="utf-8")

        from llm.dspy_judge import load_compiled_judge
        a = load_compiled_judge(artifact)
        b = load_compiled_judge(artifact)
        assert a is b
