"""
v1.2.1 integration test: Risk Sizer wired into run_lightweight_debate().

Reference: docs/roadmap/v1.2.0-finpos-dual-agent.md § Integration.

These tests use monkeypatch to bypass the actual LLM calls so we can
verify the wire-up without spending API credits.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from models.decision import DecisionOutput  # noqa: E402


def _make_initial_decision(decision="BUY"):
    return DecisionOutput(
        decision=decision,
        confidence=65.0,
        risk_level="MEDIUM",
        reasoning=["initial signal"],
        probabilities={"up": 0.55, "neutral": 0.25, "down": 0.20},
        source="test",
        signal_strength=65.0,
        recommendation="Test recommendation.",
    )


def _mock_judge_ok_buy():
    """Return a canned judge dict that says BUY with 70% confidence."""
    return {
        "decision": "BUY",
        "confidence": 70.0,
        "risk_level": "MEDIUM",
        "up_probability": 0.60,
        "neutral_probability": 0.25,
        "down_probability": 0.15,
        "reasoning_summary": "Judge confirms BUY.",
        "reasoning_detail": "Bull thesis intact.",
    }


def test_debate_without_sizer_kwargs_is_unchanged_from_v120():
    """Existing callers that do NOT pass sizer_kwargs must see identical behavior."""
    from llm.debate import run_lightweight_debate

    with patch("llm.debate.get_client") as get_client, \
         patch("llm.debate._call_bull") as call_bull, \
         patch("llm.debate._call_bear") as call_bear, \
         patch("llm.debate._call_judge") as call_judge:
        get_client.return_value = object()
        call_bull.return_value = "Bull thinks BUY."
        call_bear.return_value = "Bear thinks WAIT."
        call_judge.return_value = _mock_judge_ok_buy()

        out = run_lightweight_debate(
            initial_decision=_make_initial_decision(),
            summary={},
            ticker="TEST",
        )

    assert out.decision == "BUY"
    # No sizer means no risk_sizer key in extra.
    assert "risk_sizer" not in out.extra
    assert "risk_sizer_error" not in out.extra


def test_debate_with_sizer_kwargs_adds_risk_sizer_output():
    """When caller passes sizer_kwargs, debate output must include risk_sizer sub-dict."""
    from llm.debate import run_lightweight_debate

    with patch("llm.debate.get_client") as get_client, \
         patch("llm.debate._call_bull") as call_bull, \
         patch("llm.debate._call_bear") as call_bear, \
         patch("llm.debate._call_judge") as call_judge:
        get_client.return_value = object()
        call_bull.return_value = "Bull."
        call_bear.return_value = "Bear."
        call_judge.return_value = _mock_judge_ok_buy()

        out = run_lightweight_debate(
            initial_decision=_make_initial_decision(),
            summary={},
            ticker="TEST",
            sizer_kwargs={
                "bankroll_usd": 10_000.0,
                "volatility_regime": "medium",
                "kelly_p_win": 0.55,
                "kelly_avg_win_pct": 0.04,
                "kelly_avg_loss_pct": 0.02,
            },
        )

    assert out.decision == "BUY"
    assert "risk_sizer" in out.extra, f"expected risk_sizer in extra: {out.extra}"
    rs = out.extra["risk_sizer"]
    # Contract: direction_input reflects the Judge's decision.
    assert rs["direction_input"] == "long"
    # Contract: verdict is fund or skip, not a direction.
    assert rs["verdict"] in ("fund", "skip")
    # Contract: Sizer never returns a direction of its own.
    assert "direction" not in rs or rs.get("direction") is None


def test_debate_judge_sell_maps_to_sizer_short():
    """Judge SELL must map to Sizer input direction=short."""
    from llm.debate import run_lightweight_debate

    with patch("llm.debate.get_client") as get_client, \
         patch("llm.debate._call_bull") as call_bull, \
         patch("llm.debate._call_bear") as call_bear, \
         patch("llm.debate._call_judge") as call_judge:
        get_client.return_value = object()
        call_bull.return_value = "Bull."
        call_bear.return_value = "Bear."
        call_judge.return_value = {**_mock_judge_ok_buy(), "decision": "SELL"}

        out = run_lightweight_debate(
            initial_decision=_make_initial_decision(decision="SELL"),
            summary={},
            ticker="TEST",
            sizer_kwargs={
                "bankroll_usd": 5_000.0,
                "volatility_regime": "high",
                "kelly_p_win": 0.60,
                "kelly_avg_win_pct": 0.03,
                "kelly_avg_loss_pct": 0.02,
            },
        )

    assert out.decision == "SELL"
    rs = out.extra["risk_sizer"]
    assert rs["direction_input"] == "short"


def test_debate_judge_wait_maps_to_sizer_no_op_and_skips():
    """Judge WAIT must map to Sizer no_op → skip verdict."""
    from llm.debate import run_lightweight_debate

    with patch("llm.debate.get_client") as get_client, \
         patch("llm.debate._call_bull") as call_bull, \
         patch("llm.debate._call_bear") as call_bear, \
         patch("llm.debate._call_judge") as call_judge:
        get_client.return_value = object()
        call_bull.return_value = "Bull."
        call_bear.return_value = "Bear."
        call_judge.return_value = {**_mock_judge_ok_buy(), "decision": "WAIT"}

        out = run_lightweight_debate(
            initial_decision=_make_initial_decision(),
            summary={},
            ticker="TEST",
            sizer_kwargs={
                "bankroll_usd": 10_000.0,
                "kelly_p_win": 0.55,
                "kelly_avg_win_pct": 0.04,
                "kelly_avg_loss_pct": 0.02,
            },
        )

    assert out.decision == "WAIT"
    rs = out.extra["risk_sizer"]
    assert rs["direction_input"] == "no_op"
    assert rs["verdict"] == "skip"
    assert rs["position_usd"] is None


def test_debate_sizer_error_is_non_fatal():
    """Sizer failure must not break the debate output."""
    from llm.debate import run_lightweight_debate

    with patch("llm.debate.get_client") as get_client, \
         patch("llm.debate._call_bull") as call_bull, \
         patch("llm.debate._call_bear") as call_bear, \
         patch("llm.debate._call_judge") as call_judge:
        get_client.return_value = object()
        call_bull.return_value = "Bull."
        call_bear.return_value = "Bear."
        call_judge.return_value = _mock_judge_ok_buy()

        # Pass sizer_kwargs missing required fields → sizer raises.
        out = run_lightweight_debate(
            initial_decision=_make_initial_decision(),
            summary={},
            ticker="TEST",
            sizer_kwargs={
                # Missing bankroll_usd — will trigger KeyError inside Sizer.
                "kelly_p_win": 0.55,
                "kelly_avg_win_pct": 0.04,
                "kelly_avg_loss_pct": 0.02,
            },
        )

    # Debate output still valid.
    assert out.decision == "BUY"
    # Error is captured in extra, not raised.
    assert "risk_sizer_error" in out.extra
    assert "risk_sizer" not in out.extra
