"""Synthetic fixtures check provenance and routing, not financial accuracy."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from engine import news_research as nr


CUTOFF = "2026-10-14T09:00:00-04:00"
CAPTURE = datetime(2026, 10, 14, 12, 55, tzinfo=timezone.utc)


def record(title="NVDA reports quarterly earnings", *, url="https://example.org/a",
           published="2026-10-14T12:30:00Z", captured=CAPTURE, provider="Example"):
    return nr.snapshot_record({"title": title, "url": url, "published": published,
                               "provider": provider}, source="synthetic", captured_at=captured)


def test_nine_am_new_york_excludes_later_same_day_and_late_capture():
    before = record()
    after = record("NVDA announces evening guidance", url="https://example.org/b",
                   published="2026-10-14T20:30:00Z",
                   captured=datetime(2026, 10, 14, 20, 35, tzinfo=timezone.utc))
    late = record("NVDA earlier headline captured later", url="https://example.org/c",
                  captured=datetime(2026, 10, 15, 12, 55, tzinfo=timezone.utc))
    result = nr.research_news("NVDA", as_of=CUTOFF, records=[before, after, late])
    assert [item["title"] for item in result.items] == [before["title"]]
    assert result.audit["as_of_utc"] == "2026-10-14T13:00:00Z"
    assert [r["reason"] for r in result.audit["candidates"]] == [
        None, "published_after_cutoff", "captured_after_cutoff"]


def test_cutoff_boundary_is_inclusive():
    boundary = datetime(2026, 10, 14, 13, tzinfo=timezone.utc)
    item = record(published="2026-10-14T13:00:00Z", captured=boundary)
    assert nr.research_news("NVDA", as_of=CUTOFF, records=[item]).items


@pytest.mark.parametrize("value", ["2026-10-14", "2026-10-14T09:00:00", "bad", True,
                                  float("nan"), float("inf"), None])
def test_ambiguous_or_invalid_timestamps_are_unknown(value):
    assert nr.parse_timestamp(value) is None


@pytest.mark.parametrize("value", ["2026-10-14T13:00:00Z", "Wed, 14 Oct 2026 13:00:00 GMT",
                                  "2026-10-14T09:00:00-04:00", 1791982800])
def test_supported_timestamps_are_aware(value):
    parsed = nr.parse_timestamp(value)
    assert parsed is not None and parsed.utcoffset().total_seconds() == 0


@pytest.mark.parametrize("field,value,reason", [
    ("published_at_utc", None, "unknown_publication_time"),
    ("available_at_utc", None, "unknown_capture_time"),
    ("captured_at_utc", "2026-10-14T12:00:00Z", "invalid_timestamp_order"),
    ("source_sha256", "0" * 64, "snapshot_hash_mismatch"),
    ("source_id", "made-up", "source_id_mismatch"),
    ("source_url", "javascript:alert(1)", "missing_source_url"),
    ("provider", {}, "invalid_provider"),
    ("snapshot_text", "A changed headline", "invalid_snapshot"),
    ("evidence_spans", [], "invalid_headline_span"),
])
def test_invalid_evidence_is_retained_with_reason(field, value, reason):
    item = record()
    item[field] = value
    result = nr.research_news("NVDA", as_of=CUTOFF, records=[item])
    assert result.items == [] and result.audit["status"] == "filtered"
    assert result.audit["input_count"] == 1
    assert result.audit["candidates"][0]["reason"] == reason


def test_utf8_headline_range_hash_and_exact_summary_are_preserved():
    item = nr.snapshot_record({"title": "英伟达公布业绩", "summary": "原文摘要\n第二行",
                               "link": "https://example.org/chinese",
                               "providerPublishTime": 1791981000},
                              source="synthetic", captured_at=CAPTURE)
    result = nr.research_news("NVDA", as_of=CUTOFF, records=[item])
    selected = result.items[0]
    data = selected["snapshot_text"].encode("utf-8")
    span = selected["evidence_spans"][0]
    assert data[span["start_byte"]:span["end_byte"]].decode() == item["title"]
    assert hashlib.sha256(data).hexdigest() == selected["source_sha256"]
    assert selected["snapshot_text"].endswith("原文摘要\n第二行")


def test_modern_yahoo_schema_and_legacy_schema_both_normalize():
    modern = nr.snapshot_record({"content": {"title": "Nvidia earnings",
                                "provider": {"displayName": "Reuters"},
                                "canonicalUrl": {"url": "https://example.org/new"},
                                "pubDate": "2026-10-14T12:00:00Z"}},
                               source="yfinance", captured_at=CAPTURE)
    legacy = nr.snapshot_record({"title": "Ford earnings", "publisher": "Example",
                                "link": "https://example.org/old",
                                "providerPublishTime": 1791981000},
                               source="yfinance", captured_at=CAPTURE)
    assert modern["provider"] == "Reuters" and modern["source_url"].endswith("/new")
    assert legacy["provider"] == "Example" and legacy["published_at_utc"].endswith("Z")


def test_historical_date_or_explicit_cutoff_never_fetches_live(monkeypatch):
    fetch = Mock(side_effect=AssertionError("must not fetch"))
    monkeypatch.setattr(nr, "_collect_live", fetch)
    monkeypatch.setattr(nr, "utc_now", lambda: datetime(2026, 10, 15, 13, tzinfo=timezone.utc))
    historical = nr.research_news("NVDA", trade_date="2026-10-14")
    assert historical.audit["status"] == "cutoff_required"
    explicit = nr.research_news("NVDA", as_of=CUTOFF)
    assert explicit.audit["status"] == "archive_required"
    assert fetch.call_count == 0


def test_archive_requires_cutoff_and_rejects_mismatched_trade_day():
    with pytest.raises(ValueError, match="precise"):
        nr.research_news("NVDA", records=[])
    with pytest.raises(ValueError, match="timezone"):
        nr.research_news("NVDA", as_of="2026-10-14")
    with pytest.raises(ValueError, match="same New York day"):
        nr.research_news("NVDA", as_of=CUTOFF, trade_date="2026-10-13", records=[])


def test_local_rank_preserves_single_letter_ticker_bilingual_alias_and_opposing_views():
    items = [record("Market weather this morning", url="https://example.org/unrelated"),
             record("F issues earnings guidance", url="https://example.org/f")]
    assert nr.research_news("F", as_of=CUTOFF, records=items, limit=1).items[0]["title"].startswith("F ")
    chinese = record("英伟达下调盈利预期", url="https://example.org/zh", provider="Chinese")
    bull = record("Nvidia earnings beat expectations", provider="English")
    bear = record("Nvidia earnings miss expectations", url="https://example.org/bear", provider="English")
    result = nr.research_news("NVDA", as_of=CUTOFF, records=items[:1] + [bull, bear, chinese], limit=3)
    assert {r["title"] for r in result.items} == {bull["title"], bear["title"], chinese["title"]}
    assert all(0 < r["relevance_score"] < float("inf") for r in result.items)


def test_exact_dedup_uses_latest_eligible_version_and_does_not_mutate_input():
    original = record()
    revised = record("NVDA reports revised quarterly earnings",
                     captured=datetime(2026, 10, 14, 12, 58, tzinfo=timezone.utc))
    supplied = [original, deepcopy(original), revised]
    before = deepcopy(supplied)
    result = nr.research_news("NVDA", as_of=CUTOFF, records=supplied)
    assert [r["title"] for r in result.items] == [revised["title"]] and supplied == before
    assert result.audit["candidates"][0]["reason"] == "superseded_snapshot"
    assert result.audit["candidates"][1]["reason"] == "duplicate_snapshot"
    assert len(result.audit["candidates"]) == 3


def test_revision_after_cutoff_cannot_replace_prior_snapshot():
    prior = record()
    revision = record("NVDA reports revised quarterly earnings",
                      captured=datetime(2026, 10, 15, 12, 58, tzinfo=timezone.utc))
    result = nr.research_news("NVDA", as_of=CUTOFF, records=[prior, revision])
    assert [r["title"] for r in result.items] == [prior["title"]]
    assert result.audit["candidates"][1]["reason"] == "captured_after_cutoff"


def test_conflicting_versions_at_same_capture_time_are_not_guessed():
    result = nr.research_news("NVDA", as_of=CUTOFF, records=[record(), record("NVDA revised earnings")])
    assert result.items == []
    assert {r["reason"] for r in result.audit["candidates"]} == {"conflicting_snapshot_versions"}


@pytest.mark.parametrize("states,expected", [
    (["empty", "empty"], "empty"), (["unavailable", "unavailable"], "unavailable"),
    (["empty", "unavailable"], "unavailable"), (["invalid", "empty"], "unavailable"),
])
def test_feed_failure_is_not_reported_as_no_news(monkeypatch, states, expected):
    monkeypatch.setattr(nr, "_collect_live", lambda *_: ([], [
        {"source": str(i), "status": status} for i, status in enumerate(states)]))
    result = nr.research_news("NVDA")
    assert result.audit["status"] == expected
    assert "does not establish absence" in result.report()


def test_live_capture_freezes_after_fetch_and_discloses_partial_feed_failure(monkeypatch):
    monkeypatch.setattr(nr, "_collect_live", lambda *_: ([record()], [
        {"source": "yfinance", "status": "ok"}, {"source": "rss", "status": "unavailable"}]))
    monkeypatch.setattr(nr, "utc_now", lambda: datetime(2026, 10, 14, 13, tzinfo=timezone.utc))
    result = nr.research_news("NVDA")
    assert result.audit["status"] == "partial" and len(result.items) == 1
    assert result.audit["as_of_utc"] == "2026-10-14T13:00:00Z"


def test_cli_replays_archive_and_never_replaces_existing_output(tmp_path, monkeypatch):
    source, output = tmp_path / "capture.json", tmp_path / "replay.json"
    source.write_text(json.dumps({"candidates": [record()]}), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["news_research", "--ticker", "NVDA", "--as-of", CUTOFF,
                                     "--input", str(source), "--output", str(output)])
    assert nr.main() == 0
    report = json.loads(output.read_text())
    assert report["selected_count"] == 1 and report["replay_input_sha256"]
    before = output.read_bytes()
    with pytest.raises(SystemExit) as exc:
        nr.main()
    assert exc.value.code == 2 and output.read_bytes() == before


def test_cli_replay_preserves_custom_aliases_and_retrieval_limit(tmp_path, monkeypatch):
    records = [record("Example device revenue guidance", url="https://example.org/target"),
               record("Other company earnings", url="https://example.org/other")]
    original = nr.research_news("XYZ", as_of=CUTOFF, records=records, aliases=["Example device"], limit=1)
    source, output = tmp_path / "custom.json", tmp_path / "replayed.json"
    source.write_text(json.dumps(original.audit), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["news_research", "--ticker", "XYZ", "--as-of", CUTOFF,
                                     "--input", str(source), "--output", str(output)])
    assert nr.main() == 0
    replay = json.loads(output.read_text())
    assert replay["selected_source_hashes"] == original.audit["selected_source_hashes"]
    assert replay["ranking"] == original.audit["ranking"]


def test_actual_live_collector_records_yahoo_failure_and_rss_metadata(monkeypatch):
    import yfinance
    import engine.news_aggregator as rss
    monkeypatch.setattr(yfinance, "Ticker", Mock(side_effect=RuntimeError("network")))
    monkeypatch.setattr(rss, "fetch_news_with_status", lambda _: {
        "items": [{"title": "Nvidia earnings", "url": "https://example.org/rss",
                   "provider": "Example", "published": "2026-10-14T12:00:00Z",
                   "source": "google_news", "captured_at_utc": "2026-10-14T12:55:00Z"}],
        "sources": [{"source": "google_news", "status": "ok"}]})
    records, sources = nr._collect_live("NVDA", True)
    assert sources[0]["status"] == "unavailable" and records[0]["source"] == "google_news"
    assert records[0]["available_at_utc"] == "2026-10-14T12:55:00Z"


def test_rss_status_distinguishes_failed_invalid_empty_and_success(monkeypatch):
    import engine.news_aggregator as rss
    responses = iter([None, b"<html>blocked</html>", b"<rss><channel/></rss>",
                      b"<rss><channel><item><title>Nvidia earnings</title>"
                      b"<link>https://example.org/rss</link></item></channel></rss>"])
    monkeypatch.setattr(rss, "_get_xml", lambda _: next(responses))
    failed = rss.fetch_news_with_status("NVDA")
    working = rss.fetch_news_with_status("NVDA")
    assert [s["status"] for s in failed["sources"]] == ["unavailable", "invalid"]
    assert [s["status"] for s in working["sources"]] == ["empty", "ok"]
    assert working["items"][0]["captured_at_utc"].endswith("Z")
