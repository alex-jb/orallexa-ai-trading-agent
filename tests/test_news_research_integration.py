"""Exercise real research routing with synthetic sources and no model/network calls."""
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from engine import news_research as nr
from engine import multi_agent_analysis as ma
from models.decision import DecisionOutput


@pytest.fixture
def wired(monkeypatch, tmp_path):
    import core.brain
    import engine.sentiment as sentiment
    import engine.signal_fusion as fusion
    import engine.decision_log as log
    import llm.claude_client as cc
    import llm.debate as debate
    import llm.perspective_panel as panel
    import skills.prediction as prediction
    import yfinance

    now = datetime(2026, 10, 14, 13, tzinfo=timezone.utc)
    raw = [{"content": {"title": "Nvidia reports strong earnings growth",
                        "pubDate": "2026-10-14T12:00:00Z",
                        "canonicalUrl": {"url": "https://example.org/good"},
                        "provider": {"displayName": "Example"}}},
           {"content": {"title": "Nvidia evening earnings revision",
                        "pubDate": "2026-10-14T20:00:00Z",
                        "canonicalUrl": {"url": "https://example.org/future"}}}]
    monkeypatch.setattr(nr, "utc_now", lambda: now)
    feed = Mock(return_value=SimpleNamespace(news=raw))
    monkeypatch.setattr(yfinance, "Ticker", feed)
    monkeypatch.setattr(yfinance, "download", Mock(side_effect=AssertionError("network forbidden")))
    monkeypatch.setattr(sentiment, "_initialized", True)
    monkeypatch.setattr(sentiment, "_SCORER_TYPE", "none")  # Existing deterministic keyword fallback.
    monkeypatch.setattr(log, "LOG_PATH", str(tmp_path / "decisions.json"))

    frame = pd.DataFrame({"Close": [100., 101.]})
    brain = SimpleNamespace(ticker="NVDA", _prepare_data=lambda: frame,
                            _single_split=lambda _: (frame, frame),
                            _safe_summary_from_df=lambda _: {"close": 101.})
    monkeypatch.setattr(core.brain, "OrallexaBrain", lambda _: brain)
    monkeypatch.setattr(ma, "_run_ml_analyst", lambda *_: ("ML " * 400, None))
    monkeypatch.setattr(ma, "_run_risk_manager", lambda *_: {"plan_summary": "synthetic"})
    monkeypatch.setattr(ma, "_run_llm_market_report", lambda *_: "synthetic market report")
    monkeypatch.setattr(cc, "get_client", lambda: object())
    monkeypatch.setattr(prediction.PredictionSkill, "execute", lambda *_args, **_kw: DecisionOutput(
        decision="WAIT", confidence=40., risk_level="MEDIUM", reasoning=[],
        probabilities={"up": .33, "neutral": .34, "down": .33}, source="synthetic"))
    context_seen, items_seen = [], []

    def fake_debate(**kwargs):
        # Run the real context formatter, but never call a model.
        context_seen.append(debate._build_context(kwargs["summary"], kwargs["ticker"], kwargs["rag_context"]))
        return kwargs["initial_decision"]

    def fake_fusion(**kwargs):
        items_seen.extend(kwargs["news_items"])
        return {"conviction": 0, "direction": "NEUTRAL"}

    monkeypatch.setattr(debate, "run_lightweight_debate", fake_debate)
    monkeypatch.setattr(panel, "run_perspective_panel", lambda **_: {
        "consensus": "NEUTRAL", "agreement": 0, "avg_score": 0})
    monkeypatch.setattr(fusion, "fuse_signals", fake_fusion)
    monkeypatch.setattr(cc, "Anthropic", Mock(side_effect=AssertionError("paid calls forbidden")))
    return SimpleNamespace(brain=brain, feed=feed, raw=raw, now=now, log=log,
                           contexts=context_seen, items=items_seen)


def assert_evidence(audit):
    assert audit["selected_count"] == 1
    assert len(audit["candidates"]) == 2
    assert audit["candidates"][0]["source_url"] == "https://example.org/good"
    assert audit["candidates"][1]["disposition"] == "rejected"


def test_real_pipeline_filters_before_fusion_and_llm_context(wired):
    result = ma.run_multi_agent_analysis("NVDA", brain=wired.brain)
    assert_evidence(result.news_research)
    assert result.decision_output.extra["news_research"] == result.news_research
    assert {r["source_url"] for r in wired.items} == {"https://example.org/good"}
    assert "strong earnings growth" in wired.contexts[0]
    assert "evening earnings revision" not in wired.contexts[0]
    assert "2026-10-14T13:00:00Z" in wired.contexts[0]


def test_real_pipeline_historical_day_does_not_load_live_news(wired):
    result = ma.run_multi_agent_analysis("NVDA", trade_date="2026-10-13", brain=wired.brain)
    assert result.news_research["status"] == "cutoff_required"
    assert wired.feed.call_count == 0 and wired.items == []
    assert "precise news_as_of required" in wired.contexts[0]


def test_real_pipeline_uses_supplied_archive_without_live_feed(wired):
    records = [nr.snapshot_record(item, source="synthetic", captured_at=wired.now) for item in wired.raw]
    result = ma.run_multi_agent_analysis("NVDA", trade_date="2026-10-14", brain=wired.brain,
                                          news_as_of="2026-10-14T09:00:00-04:00", archived_news=records)
    assert_evidence(result.news_research)
    assert wired.feed.call_count == 0


@pytest.mark.parametrize("endpoint", ["/api/deep-analysis", "/api/deep-analysis-stream"])
def test_api_result_and_saved_decision_keep_same_evidence(wired, monkeypatch, endpoint):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import api_server
    import engine.breaking_signals as breaking
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-not-a-real-key")
    monkeypatch.setattr(breaking, "detect_breaking", lambda *_: None)
    response = TestClient(api_server.app).post(endpoint, data={"ticker": "NVDA"})
    assert response.status_code == 200, response.text
    if endpoint.endswith("-stream"):
        done = [chunk for chunk in response.text.split("\n\n") if chunk.startswith("event: done\n")]
        assert len(done) == 1, response.text
        data = json.loads(done[0].split("data: ", 1)[1])
    else:
        data = response.json()
    assert_evidence(data["news_research"])
    assert data["extra"]["news_research"] == data["news_research"]
    saved = wired.log.load_decisions(1)[0]
    assert saved["extra"]["news_research"] == data["news_research"]
    assert len(wired.items) == 1 and "evening earnings revision" not in wired.contexts[0]


def test_morning_brief_headlines_keep_selected_evidence_and_feed_status(wired):
    from engine.daily_intel import _fetch_headlines
    audit = {}
    headlines = _fetch_headlines(["NVDA"], research_audit=audit)
    assert len(headlines) == 1
    assert headlines[0]["source_url"] == headlines[0]["url"] == "https://example.org/good"
    assert headlines[0]["snapshot_text"] and headlines[0]["source_sha256"]
    assert_evidence(audit["NVDA"])
    assert audit["brief_selected_source_hashes"] == [headlines[0]["source_sha256"]]
