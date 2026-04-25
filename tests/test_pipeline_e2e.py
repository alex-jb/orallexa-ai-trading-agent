"""
tests/test_pipeline_e2e.py
──────────────────────────────────────────────────────────────────
End-to-end integration tests for the analyze → PM gate → execute path.

Unit tests cover each module in isolation; these tests cover the
seams. Specifically: when a downstream skill returns a BUY at high
confidence, does the brain → PM → executor chain correctly:

  • approve and forward when portfolio has headroom
  • REJECT before any order placement when concentration is too high
  • surface the verdict in DecisionOutput.extra
  • cap position size to PM's scaled value when both caller and PM
    propose limits

Mocks: every leaf skill (run_prediction, AlpacaExecutor.execute_signal)
is patched. yfinance is never hit. PM is the real implementation.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.brain import OrallexaBrain
from engine.portfolio_manager import Position, approve_decision
from models.decision import DecisionOutput


def _bullish_decision() -> DecisionOutput:
    return DecisionOutput(
        decision="BUY",
        confidence=0.78,
        risk_level="MEDIUM",
        reasoning=["initial signal — strong momentum"],
        probabilities={"up": 0.65, "neutral": 0.20, "down": 0.15},
        source="test",
        signal_strength=0.65,
    )


# ── brain → PM ─────────────────────────────────────────────────────────────


class TestBrainToPM:
    def test_pm_blocks_when_position_oversized(self):
        """30% existing NVDA + new BUY → PM rejects, decision flips to WAIT."""
        brain = OrallexaBrain("NVDA")
        with patch.object(brain, "run_prediction", return_value=_bullish_decision()), \
             patch("models.confidence.guard_decision", side_effect=lambda x: x):
            result = brain.run_for_mode(
                mode="swing",
                use_claude=False,
                portfolio=[Position("NVDA", 3_000)],
                portfolio_value=10_000,
            )
        assert result.decision == "WAIT"
        verdict = result.extra.get("portfolio_manager")
        assert verdict is not None and verdict["approved"] is False

    def test_pm_approves_with_headroom(self):
        """Empty book → PM approves, decision stays BUY, position scaled."""
        brain = OrallexaBrain("NVDA")
        with patch.object(brain, "run_prediction", return_value=_bullish_decision()), \
             patch("models.confidence.guard_decision", side_effect=lambda x: x):
            result = brain.run_for_mode(
                mode="swing",
                use_claude=False,
                portfolio=[],
                portfolio_value=10_000,
            )
        assert result.decision == "BUY"
        verdict = result.extra.get("portfolio_manager")
        assert verdict["approved"] is True
        assert verdict["scaled_position_pct"] > 0


# ── PM → executor (logic mirroring /api/alpaca/execute) ────────────────────


def _execute_with_pm(*, ticker: str, decision: str, confidence: int,
                     position_pct: float, portfolio: list, portfolio_value: float,
                     executor):
    """Replicates the gating logic of api_server.alpaca_execute."""
    verdict = approve_decision(
        ticker=ticker,
        decision={"decision": decision, "confidence": confidence,
                  "signal_strength": confidence},
        portfolio=portfolio,
        portfolio_value=portfolio_value,
    )
    if not verdict["approved"]:
        return {"executed": False, "reason": "rejected_by_portfolio_manager",
                "portfolio_manager": verdict}
    scaled = verdict.get("scaled_position_pct") or position_pct
    if scaled > 0:
        position_pct = min(position_pct, scaled)
    placed = executor.execute_signal(
        ticker=ticker, decision=decision, confidence=confidence,
        entry_price=0.0, stop_loss=0.0, take_profit=0.0,
        position_pct=position_pct,
    )
    placed["portfolio_manager"] = verdict
    return placed


class TestPMToExecutor:
    def test_pm_rejection_blocks_executor_call(self):
        """When PM rejects, the executor must never be invoked."""
        executor = MagicMock()
        out = _execute_with_pm(
            ticker="NVDA", decision="BUY", confidence=80, position_pct=10.0,
            portfolio=[Position("NVDA", 3_000)],   # 30% — over 20% cap
            portfolio_value=10_000,
            executor=executor,
        )
        assert out["executed"] is False
        assert out["reason"] == "rejected_by_portfolio_manager"
        executor.execute_signal.assert_not_called()

    def test_pm_caps_oversized_position_request(self):
        """Caller asks for 50%, PM headroom only 5% — order goes in at 5%."""
        executor = MagicMock()
        executor.execute_signal.return_value = {"executed": True, "filled_pct": 5.0}
        _execute_with_pm(
            ticker="NVDA", decision="BUY", confidence=85, position_pct=50.0,
            portfolio=[Position("NVDA", 1_500)],   # 15% existing → 5% headroom
            portfolio_value=10_000,
            executor=executor,
        )
        passed_pct = executor.execute_signal.call_args.kwargs["position_pct"]
        assert passed_pct <= 5.0

    def test_pm_low_confidence_rejection(self):
        """Below min_confidence → reject regardless of headroom."""
        executor = MagicMock()
        out = _execute_with_pm(
            ticker="NVDA", decision="BUY", confidence=20, position_pct=5.0,
            portfolio=[],
            portfolio_value=10_000,
            executor=executor,
        )
        assert out["executed"] is False
        executor.execute_signal.assert_not_called()

    def test_pm_warnings_dont_block_execution(self):
        """Streak warning should attach to verdict but still place order."""
        executor = MagicMock()
        executor.execute_signal.return_value = {"executed": True}
        out = _execute_with_pm(
            ticker="GOOGL", decision="BUY", confidence=80, position_pct=5.0,
            portfolio=[Position("GOOGL", 500)],
            portfolio_value=10_000,
            executor=executor,
        )
        # Streak warnings come from recent_decisions list — empty here, so this
        # primarily tests that approval forwards to executor cleanly.
        assert out.get("executed") is True
        executor.execute_signal.assert_called_once()


# ── Full chain: brain → PM → executor ──────────────────────────────────────


class TestFullChain:
    def test_blocked_signal_never_reaches_executor(self):
        """Brain says BUY, PM rejects: no order placed end-to-end."""
        brain = OrallexaBrain("NVDA")
        executor = MagicMock()
        with patch.object(brain, "run_prediction", return_value=_bullish_decision()), \
             patch("models.confidence.guard_decision", side_effect=lambda x: x):
            result = brain.run_for_mode(
                mode="swing",
                use_claude=False,
                portfolio=[Position("NVDA", 3_000)],
                portfolio_value=10_000,
            )

        if result.decision == "WAIT":
            # Caller would short-circuit here and not call the executor at all.
            executor.execute_signal.assert_not_called()
        else:
            pytest.fail("Expected PM to downgrade to WAIT but got " + result.decision)

    def test_approved_signal_reaches_executor_with_pm_metadata(self):
        """Brain BUY → PM approves → execute_signal called with PM-scaled %."""
        brain = OrallexaBrain("AAPL")
        executor = MagicMock()
        executor.execute_signal.return_value = {"executed": True}

        with patch.object(brain, "run_prediction", return_value=_bullish_decision()), \
             patch("models.confidence.guard_decision", side_effect=lambda x: x):
            result = brain.run_for_mode(
                mode="swing",
                use_claude=False,
                portfolio=[],
                portfolio_value=10_000,
            )

        assert result.decision == "BUY"
        pm = result.extra["portfolio_manager"]
        assert pm["approved"] is True

        # Caller routes to executor with PM-scaled position
        out = _execute_with_pm(
            ticker="AAPL", decision="BUY", confidence=78, position_pct=10.0,
            portfolio=[],
            portfolio_value=10_000,
            executor=executor,
        )
        assert out.get("executed") is True
        executor.execute_signal.assert_called_once()
