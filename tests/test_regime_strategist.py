"""
tests/test_regime_strategist.py
──────────────────────────────────────────────────────────────────
Tests for engine/regime_strategist.py — recipe selection + LLM validation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.regime_strategist import (
    propose_regime_strategy,
    _validate_llm_proposal,
    _RECIPES,
)


def _ta_df(n: int = 100, adx: float = 25.0, atr_pct: float = 0.02) -> pd.DataFrame:
    close = pd.Series(100 + np.cumsum(np.random.randn(n) * 0.5), name="Close")
    atr = close * atr_pct
    return pd.DataFrame({
        "Close": close,
        "ADX": [adx] * n,
        "ATR": atr,
    })


# ── Base recipes ───────────────────────────────────────────────────────────


class TestRecipes:
    @pytest.mark.parametrize("regime,expected_strat", [
        ("trending", "trend_momentum"),
        ("ranging", "rsi_reversal"),
        ("volatile", "dual_thrust"),
    ])
    def test_each_regime_has_recipe(self, regime, expected_strat):
        p = propose_regime_strategy("NVDA", regime=regime)
        assert p["strategy"] == expected_strat
        assert p["source"] == "heuristic"
        assert "stop_loss" in p["params"]

    def test_unknown_regime_returns_none_strategy(self):
        p = propose_regime_strategy("NVDA", regime="banana")
        assert p["strategy"] is None
        assert p["source"] == "none"

    def test_case_insensitive_regime(self):
        p = propose_regime_strategy("NVDA", regime="TRENDING")
        assert p["strategy"] == "trend_momentum"


# ── Feature tuning ─────────────────────────────────────────────────────────


class TestFeatureTuning:
    def test_strong_adx_widens_take_profit(self):
        df = _ta_df(adx=40.0)
        p = propose_regime_strategy("NVDA", regime="trending", df=df)
        assert p["params"]["take_profit"] >= 0.10

    def test_normal_adx_keeps_default(self):
        df = _ta_df(adx=22.0)
        p = propose_regime_strategy("NVDA", regime="trending", df=df)
        # default trending take_profit from _RECIPES is 0.10
        assert p["params"]["take_profit"] == _RECIPES["trending"]["params"]["take_profit"]

    def test_high_vol_widens_stop(self):
        df = _ta_df(atr_pct=0.05)  # 5% ATR/Close
        p = propose_regime_strategy("NVDA", regime="ranging", df=df)
        assert p["params"]["stop_loss"] > _RECIPES["ranging"]["params"]["stop_loss"]

    def test_short_df_skips_tuning(self):
        df = _ta_df(n=20)
        p = propose_regime_strategy("NVDA", regime="trending", df=df)
        assert p["params"]["stop_loss"] == _RECIPES["trending"]["params"]["stop_loss"]


# ── LLM path ───────────────────────────────────────────────────────────────


class TestLLMPath:
    def test_llm_proposal_accepted_when_valid(self):
        def fake_llm(*, ticker, regime, base, df):
            return {
                "strategy": "trend_momentum",
                "params": {"rsi_min": 35, "take_profit": 0.15},
                "reasoning": "Tighter entry on trend continuation.",
            }
        p = propose_regime_strategy(
            "NVDA", regime="trending", df=_ta_df(), use_llm=True, llm_fn=fake_llm,
        )
        assert p["source"] == "llm"
        assert p["params"]["rsi_min"] == 35
        # Merged: base stop_loss preserved even though LLM didn't set it
        assert "stop_loss" in p["params"]

    def test_llm_rejected_for_unknown_strategy(self):
        def bad_llm(**kwargs):
            return {"strategy": "made_up_strat", "params": {"rsi_min": 35}}
        p = propose_regime_strategy(
            "NVDA", regime="trending", use_llm=True, llm_fn=bad_llm,
        )
        assert p["source"] == "heuristic"

    def test_llm_rejected_when_params_out_of_range(self):
        def bad_llm(**kwargs):
            return {
                "strategy": "rsi_reversal",
                "params": {"rsi_min": 999, "take_profit": -0.5},
            }
        p = propose_regime_strategy(
            "NVDA", regime="ranging", use_llm=True, llm_fn=bad_llm,
        )
        # out-of-range values filtered → no valid numeric param → reject
        assert p["source"] == "heuristic"

    def test_llm_exception_falls_back(self):
        def explode(**kwargs):
            raise RuntimeError("provider down")
        p = propose_regime_strategy(
            "NVDA", regime="trending", use_llm=True, llm_fn=explode,
        )
        assert p["source"] == "heuristic"

    def test_llm_partial_valid_merges_with_base(self):
        def partial_llm(**kwargs):
            return {
                "strategy": "trend_momentum",
                "params": {
                    "rsi_min": 42,
                    "garbage_key": "whatever",  # unknown but stringy → pass-through
                    "rsi_max": 200,              # out of range → dropped
                },
            }
        p = propose_regime_strategy(
            "NVDA", regime="trending", use_llm=True, llm_fn=partial_llm,
        )
        assert p["source"] == "llm"
        assert p["params"]["rsi_min"] == 42
        assert p["params"]["rsi_max"] == _RECIPES["trending"]["params"]["rsi_max"]
        assert p["params"]["garbage_key"] == "whatever"


# ── _validate_llm_proposal ─────────────────────────────────────────────────


class TestValidation:
    def test_non_dict_rejected(self):
        base = {"strategy": "x", "params": {"stop_loss": 0.03}, "reasoning": ""}
        assert _validate_llm_proposal("not a dict", base_recipe=base) is None
        assert _validate_llm_proposal(None, base_recipe=base) is None

    def test_missing_strategy_rejected(self):
        base = {"strategy": "x", "params": {"stop_loss": 0.03}, "reasoning": ""}
        out = _validate_llm_proposal({"params": {"rsi_min": 30}}, base_recipe=base)
        assert out is None

    def test_no_valid_numeric_param_rejected(self):
        base = {"strategy": "trend_momentum", "params": {"stop_loss": 0.04}, "reasoning": ""}
        # Only garbage keys → no recognized numeric → reject
        out = _validate_llm_proposal(
            {"strategy": "trend_momentum", "params": {"foo": "bar"}},
            base_recipe=base,
        )
        assert out is None
