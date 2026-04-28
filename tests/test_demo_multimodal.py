"""
tests/test_demo_multimodal.py
──────────────────────────────────────────────────────────────────
Smoke + format tests for scripts/demo_multimodal_debate.py.

Mock mode is the testable path — live mode hits Anthropic and yfinance
and is exercised manually.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

mpf = pytest.importorskip("mplfinance")

from scripts.demo_multimodal_debate import (
    _bias_emoji,
    _mock_call_perspective,
    render_side_by_side,
    run_demo,
)


# ── Helpers ───────────────────────────────────────────────────────────────


class TestBiasEmoji:
    def test_known_biases(self):
        assert _bias_emoji("BULLISH") == "[+]"
        assert _bias_emoji("BEARISH") == "[-]"
        assert _bias_emoji("NEUTRAL") == "[0]"

    def test_unknown_falls_back(self):
        assert _bias_emoji("WEIRD") == "[?]"


# ── Mock perspective ──────────────────────────────────────────────────────


class TestMockCallPerspective:
    QUANT = {"name": "Quant Researcher", "icon": "Q"}

    def test_returns_canned_text_response(self):
        out = _mock_call_perspective(None, self.QUANT, "ctx", "NVDA", "")
        assert out.modality == "text"
        assert out.bias == "BULLISH"
        assert out.role == "Quant Researcher"

    def test_returns_canned_vision_when_chart_passed(self):
        out = _mock_call_perspective(None, self.QUANT, "ctx", "NVDA", "",
                                      chart_png=b"\x89PNG\r\n\x1a\nfake")
        assert out.modality == "vision"
        # The canned vision response should disagree with text — that's the
        # whole point of the demo (illustrate where the modalities diverge).
        assert out.bias == "BEARISH"

    def test_unknown_role_falls_back_to_neutral(self):
        out = _mock_call_perspective(
            None, {"name": "Unknown Role", "icon": ""}, "ctx", "NVDA", "",
        )
        assert out.bias == "NEUTRAL"
        assert out.score == 0


# ── Side-by-side report rendering ────────────────────────────────────────


class TestRenderSideBySide:
    def _panel(self, with_diff=True):
        panel = {
            "consensus": "BULLISH",
            "avg_score": 38.7,
            "agreement": 75,
            "perspectives": [
                {"role": "Quant Researcher", "icon": "Q", "bias": "BULLISH",
                 "score": 45, "conviction": 65, "reasoning": "8/10 ML models long",
                 "key_factor": "Multi-source alignment", "modality": "text"},
                {"role": "Quant Researcher", "icon": "Q", "bias": "BEARISH",
                 "score": -25, "conviction": 60, "reasoning": "H&S forming",
                 "key_factor": "Head and shoulders", "modality": "vision"},
            ],
            "panel_summary": "",
            "roles_selected": ["Quant Researcher"],
        }
        if with_diff:
            panel["multimodal_diff"] = {
                "pairs": [
                    {
                        "role": "Quant Researcher",
                        "text":   {"bias": "BULLISH", "score": 45, "conviction": 65,
                                   "reasoning": "8/10 ML models long"},
                        "vision": {"bias": "BEARISH", "score": -25, "conviction": 60,
                                   "reasoning": "H&S forming"},
                        "agree": False,
                        "score_delta": -70,
                        "conviction_delta": -5,
                    }
                ],
                "agreement_rate": 0.0,
                "avg_score_delta": -70.0,
                "avg_conviction_delta": -5.0,
                "n_pairs": 1,
            }
        return panel

    def test_includes_ticker_and_consensus_header(self):
        md = render_side_by_side(self._panel(), "NVDA")
        assert "NVDA" in md
        assert "BULLISH" in md
        assert "+38.7" in md
        assert "75%" in md

    def test_lists_every_perspective_row(self):
        md = render_side_by_side(self._panel(), "NVDA")
        # Two rows in the perspectives table — text + vision.
        assert md.count("Quant Researcher") >= 2
        assert "`text`" in md
        assert "`vision`" in md

    def test_diff_section_when_pairs_present(self):
        md = render_side_by_side(self._panel(), "NVDA")
        assert "Text vs Vision diff" in md
        assert "DISAGREE" in md
        assert "Score delta: -70" in md
        assert "Agreement rate: **0.0%**" in md

    def test_diff_section_handles_no_pairs(self):
        md = render_side_by_side(self._panel(with_diff=False), "NVDA")
        # No diff key present → renderer should not crash; falls into the
        # "_No vision pairs available_" branch.
        assert "No vision pairs available" in md

    def test_markdown_is_utf8_safe(self):
        md = render_side_by_side(self._panel(), "NVDA")
        # Must round-trip through utf-8 without errors (saved-report path).
        assert md.encode("utf-8").decode("utf-8") == md


# ── End-to-end mock flow ──────────────────────────────────────────────────


class TestRunDemoMock:
    def test_writes_report_files(self, tmp_path, monkeypatch):
        # Redirect _ROOT-rooted assets paths to tmp_path so the test doesn't
        # touch the committed assets/.
        import scripts.demo_multimodal_debate as demo
        monkeypatch.setattr(demo, "_ROOT", tmp_path)

        rc = run_demo("NVDA", period="3mo", mock=True, save_report=True)
        assert rc == 0

        report_md = tmp_path / "assets" / "demo_reports" / "multimodal_demo_NVDA.md"
        report_json = tmp_path / "assets" / "demo_reports" / "multimodal_demo_NVDA.json"
        assert report_md.exists()
        assert report_json.exists()

        body = report_md.read_text(encoding="utf-8")
        assert "Multi-modal Debate Demo" in body
        assert "BEARISH" in body  # vision response was bearish

        raw = json.loads(report_json.read_text(encoding="utf-8"))
        assert "multimodal_diff" in raw
        assert raw["multimodal_diff"]["n_pairs"] == 1

    def test_returns_zero_without_report_flag(self, tmp_path, monkeypatch):
        import scripts.demo_multimodal_debate as demo
        monkeypatch.setattr(demo, "_ROOT", tmp_path)
        rc = run_demo("AAPL", period="3mo", mock=True, save_report=False)
        assert rc == 0
        # No report dir created when --report not passed.
        assert not (tmp_path / "assets" / "demo_reports").exists()
