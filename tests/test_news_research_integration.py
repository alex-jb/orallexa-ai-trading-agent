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
    real_risk, real_report = ma._run_risk_manager, ma._run_llm_market_report
    role_inputs = []

    def fake_risk(*args):
        role_inputs.append(("risk_manager", args[3]))
        return {"plan_summary": "synthetic"}

    def fake_report(*args):
        role_inputs.append(("deep_market_report", args[2]))
        return "synthetic market report"

    def fake_panel(**kwargs):
        role_inputs.append(("perspective_panel", kwargs["news_report"]))
        return {"consensus": "NEUTRAL", "agreement": 0, "avg_score": 0}

    monkeypatch.setattr(ma, "_run_ml_analyst", lambda *_: ("ML " * 400, None))
    monkeypatch.setattr(ma, "_run_risk_manager", fake_risk)
    monkeypatch.setattr(ma, "_run_llm_market_report", fake_report)
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
    monkeypatch.setattr(panel, "run_perspective_panel", fake_panel)
    monkeypatch.setattr(fusion, "fuse_signals", fake_fusion)
    monkeypatch.setattr(cc, "Anthropic", Mock(side_effect=AssertionError("paid calls forbidden")))
    return SimpleNamespace(brain=brain, feed=feed, raw=raw, now=now, log=log,
                           contexts=context_seen, items=items_seen, role_inputs=role_inputs,
                           real_risk=real_risk, real_report=real_report)


def assert_evidence(audit):
    assert audit["selected_count"] == 1
    assert len(audit["candidates"]) == 2
    assert audit["candidates"][0]["source_url"] == "https://example.org/good"
    assert audit["candidates"][1]["disposition"] == "rejected"
    assert audit["sentiment_scope"] == "text_sequence"
    assert audit["target_sentiment"] == "not_extracted"
    assert all(row["target_sentiment"] == "not_extracted" for row in audit["sentiment_scores"])
    assert "entity-specific sentiment are unverified" in audit["prompt_context"]["text"]


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


def eight_headlines(wired):
    wired.raw[:] = [{"content": {"title": f"Nvidia earnings source number {i}",
                                 "pubDate": "2026-10-14T12:00:00Z",
                                 "canonicalUrl": {"url": f"https://example.org/{i}?x=" + "a" * 900},
                                 "provider": {"displayName": f"Outlet {i}"}}} for i in range(8)]


@pytest.mark.parametrize("compression", ["off", "extractive"])
def test_all_deep_roles_keep_eight_quotes_and_full_report_survives_compression(wired, monkeypatch, compression):
    import engine.context_compressor as compressor
    eight_headlines(wired)
    compressed = []

    def fake_compress(text, **kwargs):
        compressed.append(text)
        return "COMPRESSED:" + text[:60]

    monkeypatch.setattr(compressor, "compress", fake_compress)
    result = ma.run_multi_agent_analysis("NVDA", brain=wired.brain, compress_context=compression)
    packed = result.news_research["prompt_context"]
    assert packed["included_count"] == 8 and len(packed["text"]) <= 2000
    assert all(source["content"]["title"] in wired.contexts[0] for source in wired.raw)
    assert all(text == packed["text"] for _, text in wired.role_inputs)
    assert all(source["content"]["canonicalUrl"]["url"] in result.news_report for source in wired.raw)
    assert all("NEWS" not in text for text in compressed)
    assert set(result.news_research["context_consumers"]) == {
        "debate", "perspective_panel", "risk_manager", "deep_market_report"}


@pytest.mark.parametrize("role", ["risk", "report"])
def test_real_provider_request_construction_keeps_all_eight_citations(wired, monkeypatch, role):
    import llm.call_logger as calls
    eight_headlines(wired)
    audit = {}
    _, _ = ma._run_news_analyst("NVDA", audit=audit)
    packed = audit["prompt_context"]
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text='{"plan_summary":"synthetic"}')])
    logged = Mock(return_value=(response, {}))
    monkeypatch.setattr(calls, "logged_create", logged)
    if role == "risk":
        decision = DecisionOutput("WAIT", 40, "MEDIUM", [], {"up": .33, "neutral": .34, "down": .33}, "test")
        wired.real_risk(object(), decision, "market", packed["text"], "ml", "NVDA", {"close": 101})
    else:
        wired.real_report(object(), "market", packed["text"], "ml", "NVDA", {"close": 101})
    prompt = logged.call_args.kwargs["messages"][0]["content"]
    assert packed["text"] in prompt
    assert all(f"[{row['citation_id']}]" in prompt for row in packed["citation_ledger"])
    assert "https://example.org" not in prompt


@pytest.mark.parametrize("endpoint", ["/api/deep-analysis", "/api/deep-analysis-stream"])
def test_eight_source_api_response_keeps_prompt_ledgers_and_unmodified_source_links(wired, monkeypatch, endpoint):
    from fastapi.testclient import TestClient
    import api_server
    import engine.breaking_signals as breaking
    eight_headlines(wired)
    monkeypatch.setattr(api_server, "DEMO_MODE", False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-not-a-real-key")
    monkeypatch.setattr(breaking, "detect_breaking", lambda *_: None)
    response = TestClient(api_server.app).post(endpoint, data={"ticker": "NVDA"})
    assert response.status_code == 200
    if endpoint.endswith("-stream"):
        done = next(chunk for chunk in response.text.split("\n\n") if chunk.startswith("event: done\n"))
        data = json.loads(done.split("data: ", 1)[1])
    else:
        data = response.json()
    audit = data["news_research"]
    assert audit["prompt_context"]["included_count"] == 8
    assert set(audit["context_consumers"]) == {"debate", "perspective_panel", "risk_manager", "deep_market_report"}
    assert all("returned_references" in value for value in audit["context_consumers"].values())
    assert all(source["content"]["title"] in wired.contexts[0] for source in wired.raw)
    assert all(source["content"]["canonicalUrl"]["url"] in data["reports"]["news"] for source in wired.raw)
    assert wired.log.load_decisions(1)[0]["extra"]["news_research"] == audit


def test_budget_skipped_roles_have_no_consumer_receipts(wired):
    budget = SimpleNamespace(allow=lambda: False, report=lambda: {"exhausted": True})
    result = ma.run_multi_agent_analysis("NVDA", brain=wired.brain, token_budget=budget)
    assert result.news_research["prompt_context"]["state"] == "prepared"
    assert result.news_research.get("context_consumers", {}) == {}
    assert set(result.budget_skipped) == {"debate", "perspective_panel", "risk_manager", "deep_market_report"}


def test_lite_path_keeps_its_six_source_limit_and_separate_human_report(wired, monkeypatch):
    from engine.deep_analysis_lite import run_deep_analysis_lite
    import engine.ml_signal as ml
    eight_headlines(wired)
    monkeypatch.setattr(ml, "run_ml_analysis", lambda **_: None)
    result = run_deep_analysis_lite(wired.brain)
    audit = result["news_research"]
    assert audit["prompt_context"]["included_count"] == 6
    assert "lite_debate" in audit["context_consumers"]
    for row in audit["prompt_context"]["citation_ledger"]:
        assert row["excerpt"] in wired.contexts[0]
        assert row["source_url"] in result["reports"]["news"]
    assert result["decision_output"].extra["news_research"] == audit


def test_complete_daily_generation_saves_each_roles_prepared_context_and_reference_audit(wired, monkeypatch, tmp_path):
    import engine.daily_intel as daily
    import llm.call_logger as calls
    import yfinance
    import re
    eight_headlines(wired)
    monkeypatch.delenv("DAILY_INTEL_USE_RSS", raising=False)
    monkeypatch.setattr(yfinance, "Ticker", lambda ticker: SimpleNamespace(news=wired.raw if ticker == "NVDA" else []))
    monkeypatch.setattr(daily, "CACHE_PATH", tmp_path / "brief.json")
    mover = {"ticker": "NVDA", "price": 101., "change_pct": 1., "volume_ratio": 2.}
    monkeypatch.setattr(daily, "_fetch_top_movers", lambda: ([mover], [], []))
    monkeypatch.setattr(daily, "_fetch_sectors", lambda: [])
    monkeypatch.setattr(daily, "_enrich_picks_with_regime_and_pm", lambda value: value)
    monkeypatch.setattr(daily, "_generate_options_flow", lambda *_: None)
    monkeypatch.setattr(daily, "_fetch_macro", lambda: [])
    monkeypatch.setattr(daily, "_calc_fear_greed", lambda *_: {})
    monkeypatch.setattr(daily, "_generate_econ_calendar", lambda: [])
    monkeypatch.setattr(daily, "_calc_breadth", lambda *_: {})
    monkeypatch.setattr(daily, "_generate_earnings_watchlist", lambda *_: [])
    requests = []

    def fake_create(client, **kwargs):
        requests.append(kwargs)
        prompt = kwargs["messages"][0]["content"]
        label = re.search(r"\[(E\d+:[0-9a-f]{12})\]", prompt).group(1)
        kind = kwargs["request_type"]
        if kind == "daily_intel_summary":
            text = f"MIXED\nSource headline [{label}]."
        elif kind == "daily_intel_picks":
            text = json.dumps([{"ticker": "NVDA", "reason": f"Source [{label}]", "direction": "neutral"}])
        elif kind == "daily_intel_playbook":
            text = json.dumps({"tone_en": f"Source [{label}]"})
        else:
            text = json.dumps({"thread": [f"Source headline [{label}]."]})
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)]), {}

    monkeypatch.setattr(calls, "logged_create", fake_create)
    result = daily.generate_daily_intel(force=True)
    assert len(requests) == 4
    contexts = result["news_research"]["prompt_contexts"]
    assert set(contexts) == {"summary", "playbook", "picks", "social_draft"}
    for packed in contexts.values():
        assert len(packed["text"]) <= 2000 and packed["included_count"] == 4
        assert packed["returned_references"]["state"] == "references_resolve"
        assert packed["returned_references"]["entailment_verified"] is False
        assert any(packed["text"] in request["messages"][0]["content"] for request in requests)
    saved = json.loads(daily.CACHE_PATH.read_text())
    assert saved["news_research"] == result["news_research"]
    assert all(len(row["source_url"]) > 900 for row in saved["headlines"])
    assert all(row["sentiment_scope"] == "text_sequence" for row in saved["headlines"])
    assert all(row["target_sentiment"] == "not_extracted" for row in saved["headlines"])
