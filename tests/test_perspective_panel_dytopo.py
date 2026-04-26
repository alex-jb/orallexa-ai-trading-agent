"""
tests/test_perspective_panel_dytopo.py
──────────────────────────────────────────────────────────────────
Tests for the DyTopo-inspired dynamic role selection in
llm/perspective_panel.select_roles_for_context.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from llm.perspective_panel import select_roles_for_context, ROLES


class TestRoleSelection:
    def test_volatile_picks_all(self):
        roles = select_roles_for_context({}, regime="volatile")
        assert len(roles) == len(ROLES)

    def test_trending_picks_aggressive_quant(self):
        roles = select_roles_for_context({}, regime="trending")
        names = {r["name"] for r in roles}
        assert "Aggressive Trader" in names
        assert "Quant Researcher" in names
        assert len(roles) == 2

    def test_ranging_picks_conservative_quant(self):
        roles = select_roles_for_context({}, regime="ranging")
        names = {r["name"] for r in roles}
        assert "Conservative Analyst" in names
        assert "Quant Researcher" in names
        assert len(roles) == 2

    def test_mean_revert_alias_treated_as_ranging(self):
        roles = select_roles_for_context({}, regime="mean_revert")
        names = {r["name"] for r in roles}
        assert "Conservative Analyst" in names
        assert "Quant Researcher" in names

    def test_unknown_regime_picks_default_triple(self):
        roles = select_roles_for_context({}, regime=None)
        names = {r["name"] for r in roles}
        assert "Conservative Analyst" in names
        assert "Macro Strategist" in names
        assert "Quant Researcher" in names
        assert len(roles) == 3

    def test_min_roles_padding(self):
        # min_roles=3 on a regime that would normally pick 2
        roles = select_roles_for_context({}, regime="trending", min_roles=3)
        assert len(roles) == 3

    def test_returns_role_dicts_not_names(self):
        roles = select_roles_for_context({}, regime="trending")
        for r in roles:
            assert "name" in r and "system" in r and "focus" in r
