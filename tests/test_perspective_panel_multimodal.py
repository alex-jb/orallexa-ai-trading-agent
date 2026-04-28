"""
tests/test_perspective_panel_multimodal.py
──────────────────────────────────────────────────────────────────
Day 3-5 multimodal debate tests. Mocks the Anthropic client so we
verify wiring (image block in the message, modality tag, diff math)
without making a real API call.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from llm.perspective_panel import (
    PerspectiveResult,
    ROLES,
    _call_perspective,
    compare_text_vs_vision,
    run_perspective_panel,
)


# ── _call_perspective vision wiring ───────────────────────────────────────


def _make_logged_create_response(payload: str):
    """Return (response, _) tuple shaped like logged_create."""
    response = MagicMock()
    response.content = [MagicMock(text=payload)]
    return response, {}


class TestCallPerspectiveVision:
    QUANT = ROLES[3]  # Quant Researcher

    def test_text_call_uses_string_content(self):
        captured = {}

        def fake_logged_create(client, **kwargs):
            captured["messages"] = kwargs["messages"]
            return _make_logged_create_response(
                '{"bias":"BULLISH","score":40,"conviction":70,'
                '"reasoning":"x","key_factor":"y"}'
            )

        with patch("llm.perspective_panel.logged_create", side_effect=fake_logged_create):
            out = _call_perspective(MagicMock(), self.QUANT, "ctx", "NVDA")

        assert out.modality == "text"
        # Text-only path keeps content as a string (legacy shape).
        assert isinstance(captured["messages"][0]["content"], str)
        assert "NVDA" in captured["messages"][0]["content"]

    def test_vision_call_includes_image_block(self):
        captured = {}

        def fake_logged_create(client, **kwargs):
            captured["messages"] = kwargs["messages"]
            captured["request_type"] = kwargs["request_type"]
            captured["max_tokens"] = kwargs["max_tokens"]
            return _make_logged_create_response(
                '{"bias":"BEARISH","score":-20,"conviction":55,'
                '"reasoning":"x","key_factor":"y"}'
            )

        png = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"
        with patch("llm.perspective_panel.logged_create", side_effect=fake_logged_create):
            out = _call_perspective(
                MagicMock(), self.QUANT, "ctx", "NVDA", chart_png=png
            )

        assert out.modality == "vision"

        content = captured["messages"][0]["content"]
        assert isinstance(content, list)
        assert len(content) == 2
        # Image block first
        assert content[0]["type"] == "image"
        assert content[0]["source"]["media_type"] == "image/png"
        # base64-encoded PNG bytes are present
        import base64
        assert base64.b64decode(content[0]["source"]["data"]) == png
        # Text block second carries the prompt with the chart hint
        assert content[1]["type"] == "text"
        assert "K-line chart" in content[1]["text"]

        # Vision calls get tagged separately for cost telemetry + bumped tokens.
        assert captured["request_type"].endswith("_vision")
        assert captured["max_tokens"] >= 400

    def test_vision_failure_returns_neutral_with_vision_modality(self):
        # Even when the LLM blows up, the vision PerspectiveResult must keep
        # modality="vision" so compare_text_vs_vision can pair it.
        with patch(
            "llm.perspective_panel.logged_create",
            side_effect=RuntimeError("api 500"),
        ):
            out = _call_perspective(
                MagicMock(), self.QUANT, "ctx", "NVDA",
                chart_png=b"\x89PNG\r\n\x1a\nbytes",
            )
        assert out.modality == "vision"
        assert out.bias == "NEUTRAL"
        assert out.conviction == 0


# ── compare_text_vs_vision ────────────────────────────────────────────────


def _result(role: str, modality: str, *, bias: str, score: int, conviction: int):
    return PerspectiveResult(
        role=role, icon="📊", bias=bias, score=score, conviction=conviction,
        reasoning=f"{modality} reasoning", key_factor="kf", modality=modality,
    )


class TestCompareTextVsVision:
    def test_no_vision_results_returns_zero_shape(self):
        text_only = [_result("Quant", "text", bias="BULLISH", score=30, conviction=60)]
        diff = compare_text_vs_vision(text_only)
        assert diff["n_pairs"] == 0
        assert diff["pairs"] == []
        assert diff["agreement_rate"] == 0.0

    def test_pairs_text_and_vision_by_role(self):
        results = [
            _result("Quant", "text", bias="BULLISH", score=30, conviction=60),
            _result("Quant", "vision", bias="BULLISH", score=50, conviction=70),
        ]
        diff = compare_text_vs_vision(results)
        assert diff["n_pairs"] == 1
        pair = diff["pairs"][0]
        assert pair["role"] == "Quant"
        assert pair["agree"] is True
        assert pair["score_delta"] == 20  # vision - text
        assert pair["conviction_delta"] == 10
        assert diff["agreement_rate"] == 1.0
        assert diff["avg_score_delta"] == 20.0

    def test_disagreement_lowers_rate(self):
        results = [
            _result("Quant", "text", bias="BULLISH", score=30, conviction=60),
            _result("Quant", "vision", bias="BEARISH", score=-25, conviction=55),
            _result("Aggressive", "text", bias="NEUTRAL", score=5, conviction=40),
            _result("Aggressive", "vision", bias="NEUTRAL", score=-2, conviction=45),
        ]
        diff = compare_text_vs_vision(results)
        assert diff["n_pairs"] == 2
        assert diff["agreement_rate"] == 0.5  # 1 of 2 agree
        # avg_score_delta = ((-25-30) + (-2-5))/2 = -31.0
        assert diff["avg_score_delta"] == -31.0

    def test_unmatched_role_dropped_from_pairs(self):
        # Vision-only result with no text-only counterpart can't be paired.
        results = [
            _result("Quant", "vision", bias="BULLISH", score=40, conviction=60),
        ]
        diff = compare_text_vs_vision(results)
        assert diff["n_pairs"] == 0


# ── run_perspective_panel multimodal flag ────────────────────────────────


@pytest.fixture
def mock_perspective_pool(monkeypatch):
    """Stub run_perspective_panel's deps so the function runs end-to-end."""
    monkeypatch.setattr("llm.perspective_panel.get_client", lambda: MagicMock())

    # Memory layers — return None / no-op.
    monkeypatch.setattr("llm.perspective_panel.SharedMemory", lambda: None,
                        raising=False)
    return None


class TestRunPerspectivePanelMultimodal:
    def _stub_perspective(self, monkeypatch, *, vision_seen):
        """Patch _call_perspective to record whether chart_png was passed."""
        def fake_call(client, role, context, ticker, mem_ctx, *, chart_png=None):
            modality = "vision" if chart_png is not None else "text"
            if modality == "vision":
                vision_seen.append(role["name"])
            return PerspectiveResult(
                role=role["name"], icon=role["icon"],
                bias="BULLISH" if modality == "text" else "BEARISH",
                score=30 if modality == "text" else -20,
                conviction=60,
                reasoning=f"{modality} answer", key_factor="kf",
                modality=modality,
            )
        monkeypatch.setattr("llm.perspective_panel._call_perspective", fake_call)

    def test_multimodal_off_no_chart_render(self, monkeypatch, mock_perspective_pool):
        seen = []
        self._stub_perspective(monkeypatch, vision_seen=seen)
        # render_kline_for must NOT be called when multimodal=False.
        monkeypatch.setattr(
            "engine.chart_render.render_kline_for",
            lambda *a, **kw: pytest.fail("should not render when multimodal=False"),
        )

        out = run_perspective_panel({}, "NVDA", multimodal=False)
        assert "multimodal_diff" not in out
        assert seen == []

    def test_multimodal_on_runs_vision_for_default_role(self, monkeypatch, mock_perspective_pool):
        seen = []
        self._stub_perspective(monkeypatch, vision_seen=seen)
        png = b"\x89PNG\r\n\x1a\nfake"
        monkeypatch.setattr(
            "engine.chart_render.render_kline_for",
            lambda *a, **kw: png,
        )

        out = run_perspective_panel({}, "NVDA", multimodal=True)

        # Default multimodal_roles=["Quant Researcher"] → exactly 1 vision call.
        assert seen == ["Quant Researcher"]
        # 4 text + 1 vision = 5 PerspectiveResult dicts.
        assert len(out["perspectives"]) == 5
        diff = out["multimodal_diff"]
        assert diff["n_pairs"] == 1
        assert diff["pairs"][0]["role"] == "Quant Researcher"

    def test_multimodal_on_chart_render_failure_falls_through_to_text(
        self, monkeypatch, mock_perspective_pool,
    ):
        seen = []
        self._stub_perspective(monkeypatch, vision_seen=seen)
        # render returns None — multimodal must skip cleanly, not crash.
        monkeypatch.setattr(
            "engine.chart_render.render_kline_for",
            lambda *a, **kw: None,
        )

        out = run_perspective_panel({}, "NVDA", multimodal=True)

        assert seen == []
        assert len(out["perspectives"]) == 4
        # multimodal flag still set → diff present but n_pairs=0.
        assert out["multimodal_diff"]["n_pairs"] == 0

    def test_multimodal_roles_override(self, monkeypatch, mock_perspective_pool):
        seen = []
        self._stub_perspective(monkeypatch, vision_seen=seen)
        monkeypatch.setattr(
            "engine.chart_render.render_kline_for",
            lambda *a, **kw: b"\x89PNG\r\n\x1a\nx",
        )

        out = run_perspective_panel(
            {}, "NVDA", multimodal=True,
            multimodal_roles=["Aggressive Trader", "Macro Strategist"],
        )

        # Two vision calls, in any order.
        assert sorted(seen) == ["Aggressive Trader", "Macro Strategist"]
        assert out["multimodal_diff"]["n_pairs"] == 2

    def test_consensus_ignores_vision_results(self, monkeypatch, mock_perspective_pool):
        """Headline consensus stays text-driven so historical comparisons
        remain apples-to-apples; vision is informational."""
        seen = []
        self._stub_perspective(monkeypatch, vision_seen=seen)
        monkeypatch.setattr(
            "engine.chart_render.render_kline_for",
            lambda *a, **kw: b"\x89PNG\r\n\x1a\nx",
        )

        out = run_perspective_panel({}, "NVDA", multimodal=True)
        # Stub: text=BULLISH/score=30 (4 roles), vision=BEARISH/-20 (1 role).
        # With vision excluded from consensus, avg_score is 30 (all text BULLISH),
        # so consensus must be BULLISH not pulled toward neutral by the bear vision.
        assert out["consensus"] == "BULLISH"
        assert out["avg_score"] == 30.0
