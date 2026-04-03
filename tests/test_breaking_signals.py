"""Tests for engine/breaking_signals.py — detection logic only (no file I/O)."""
import pytest
from unittest.mock import patch
from models.decision import DecisionOutput


@pytest.fixture
def buy_decision():
    return DecisionOutput(
        decision="BUY", confidence=75, risk_level="LOW",
        signal_strength=72, recommendation="Buy",
        reasoning=["Bull: strong"], source="test",
        probabilities={"up": 0.65, "neutral": 0.20, "down": 0.15},
    )


@pytest.fixture
def sell_decision():
    return DecisionOutput(
        decision="SELL", confidence=60, risk_level="HIGH",
        signal_strength=55, recommendation="Sell",
        reasoning=["Bear: weak"], source="test",
        probabilities={"up": 0.20, "neutral": 0.15, "down": 0.65},
    )


@pytest.fixture
def prev_buy_log():
    return {
        "ticker": "NVDA", "decision": "BUY", "confidence": 70,
        "probabilities": {"up": 0.60, "neutral": 0.25, "down": 0.15},
    }


@pytest.fixture
def prev_sell_log():
    return {
        "ticker": "NVDA", "decision": "SELL", "confidence": 65,
        "probabilities": {"up": 0.20, "neutral": 0.20, "down": 0.60},
    }


class TestDetectBreaking:
    @patch("engine.breaking_signals._get_last_signal", return_value=None)
    def test_no_previous_signal_returns_none(self, mock_get, buy_decision):
        from engine.breaking_signals import detect_breaking
        result = detect_breaking(buy_decision, "NVDA")
        assert result is None

    @patch("engine.breaking_signals._get_last_signal")
    def test_decision_flip_detected(self, mock_get, sell_decision, prev_buy_log):
        mock_get.return_value = prev_buy_log
        from engine.breaking_signals import detect_breaking
        result = detect_breaking(sell_decision, "NVDA")
        assert result is not None
        flips = [a for a in (result if isinstance(result, list) else [result]) if a.get("type") == "decision_flip"]
        assert len(flips) >= 1
        assert flips[0]["severity"] == "critical"
        assert flips[0]["prev_decision"] == "BUY"
        assert flips[0]["new_decision"] == "SELL"

    @patch("engine.breaking_signals._get_last_signal")
    def test_no_alert_when_same_decision(self, mock_get, buy_decision, prev_buy_log):
        mock_get.return_value = prev_buy_log
        from engine.breaking_signals import detect_breaking
        result = detect_breaking(buy_decision, "NVDA")
        # Small shifts should not trigger alerts
        if result is not None:
            alerts = result if isinstance(result, list) else [result]
            flips = [a for a in alerts if a.get("type") == "decision_flip"]
            assert len(flips) == 0

    @patch("engine.breaking_signals._get_last_signal")
    def test_probability_shift_detected(self, mock_get, buy_decision):
        # Previous had low up probability
        mock_get.return_value = {
            "ticker": "NVDA", "decision": "BUY", "confidence": 70,
            "probabilities": {"up": 0.40, "neutral": 0.30, "down": 0.30},
        }
        from engine.breaking_signals import detect_breaking
        result = detect_breaking(buy_decision, "NVDA")
        assert result is not None
        alerts = result if isinstance(result, list) else [result]
        prob_shifts = [a for a in alerts if a.get("type") == "probability_shift"]
        assert len(prob_shifts) >= 1

    @patch("engine.breaking_signals._get_last_signal")
    def test_confidence_shift_detected(self, mock_get):
        from engine.breaking_signals import detect_breaking
        mock_get.return_value = {
            "ticker": "NVDA", "decision": "BUY", "confidence": 40,
            "probabilities": {"up": 0.60, "neutral": 0.25, "down": 0.15},
        }
        current = DecisionOutput(
            decision="BUY", confidence=75, risk_level="LOW",
            signal_strength=72, recommendation="Buy",
            reasoning=["Bull: strong"], source="test",
            probabilities={"up": 0.62, "neutral": 0.23, "down": 0.15},
        )
        result = detect_breaking(current, "NVDA")
        assert result is not None
        alerts = result if isinstance(result, list) else [result]
        conf_shifts = [a for a in alerts if a.get("type") == "confidence_shift"]
        assert len(conf_shifts) >= 1


class TestLoadJson:
    def test_load_nonexistent_returns_empty(self):
        from engine.breaking_signals import _load_json
        assert _load_json("/nonexistent/path.json") == []

    def test_load_invalid_json_returns_empty(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json", encoding="utf-8")
        from engine.breaking_signals import _load_json
        assert _load_json(str(f)) == []
