"""Evidence-input mechanics, not model quality or financial performance."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib

import pytest

from engine.news_context import (
    anchor_char_span, pack_news_context, news_context_for_role, audit_news_references,
)
from engine.news_research import snapshot_record


NOW = datetime(2026, 10, 14, 13, tzinfo=timezone.utc)
AUDIT = {"ticker": "NVDA", "status": "ok", "as_of_utc": "2026-10-14T13:00:00Z"}


def item(index=0, title=None):
    return snapshot_record({"title": title or f"Nvidia earnings report number {index}",
                            "url": f"https://example.org/{index}?link=" + "a" * 700,
                            "provider": f"Outlet {index}", "published": "2026-10-14T12:00:00Z"},
                           source="synthetic", captured_at=NOW)


def test_eight_complete_headlines_survive_long_urls_with_exact_citation_ledger():
    items = [item(i) for i in range(8)]
    before = deepcopy(items)
    result = pack_news_context(AUDIT, items)
    assert len(result["text"]) <= 2000
    assert result["included_count"] == 8 and result["omitted"] == []
    assert "https://" not in result["text"] and items == before
    for source, row in zip(items, result["citation_ledger"]):
        assert source["title"] in result["text"]
        assert row["source_url"] == source["source_url"]
        data = source["snapshot_text"].encode()[row["start_byte"]:row["end_byte"]]
        assert data.decode() == row["excerpt"]
        assert hashlib.sha256(data).hexdigest() == row["span_sha256"]


def test_chinese_character_positions_are_converted_to_original_utf8_bytes():
    text = "今天英伟达发布财报，英伟达上调预期。"
    span = anchor_char_span(text, 2, 5, "英伟达")
    assert (span["start_byte"], span["end_byte"]) == (6, 15)
    assert text.encode()[6:15].decode() == "英伟达"
    # A later identical entity has a different anchor, not a first-match search.
    second = text.index("英伟达", 5)
    other = anchor_char_span(text, second, second + 3, "英伟达")
    assert other["start_byte"] > span["end_byte"]


@pytest.mark.parametrize("start,end,expected", [(True, 2, "ab"), (-1, 2, "ab"),
                                                (0, 100, "ab"), (2, 1, ""),
                                                (0, 2, "AB"), (0, 0, "")])
def test_invalid_extractor_offsets_are_not_repaired_or_guessed(start, end, expected):
    with pytest.raises(ValueError):
        anchor_char_span("abcd", start, end, expected)


def test_budget_accounts_for_all_inputs_without_half_a_citation_row():
    items = [item(i, "Nvidia " + '"\\\n' * 90) for i in range(12)]
    result = pack_news_context(AUDIT, items, max_chars=500)
    assert len(result["text"]) <= 500
    assert result["included_count"] + len(result["omitted"]) == 12
    assert all(row["reason"] == "context_budget" for row in result["omitted"])
    for row in result["citation_ledger"]:
        assert f"[{row['citation_id']}]" in result["text"]
        assert row["truncated"] is True


def test_modified_evidence_is_accounted_for_while_valid_evidence_still_packs():
    changed = item(0)
    changed["snapshot_text"] += "revision"
    result = pack_news_context(AUDIT, [changed, item(1)])
    assert result["included_count"] == 1
    assert result["omitted"][0]["reason"] == "snapshot_hash_mismatch"
    assert result["input_count"] == 2


def test_malformed_input_does_not_drop_valid_inputs_or_break_accounting():
    result = pack_news_context(AUDIT, [None, item()])
    assert result["input_count"] == 2 and result["included_count"] == 1
    assert result["omitted"][0]["reason"] == "invalid_record"


def test_provider_publication_time_is_rendered_as_a_canonical_instant():
    row = item()
    row["published_at_utc"] = "Wed, 14 Oct 2026 12:00:00 GMT"
    packed = pack_news_context(AUDIT, [row])
    assert "pub=2026-10-14T12:00:00Z" in packed["text"]
    assert packed["citation_ledger"][0]["published_at_utc"] == "2026-10-14T12:00:00Z"


def test_duplicate_texts_from_different_urls_keep_distinct_source_bindings():
    rows = [item(0, "Nvidia earnings"), item(1, "Nvidia earnings")]
    result = pack_news_context(AUDIT, rows)
    ledger = result["citation_ledger"]
    assert ledger[0]["source_sha256"] == ledger[1]["source_sha256"]
    assert ledger[0]["citation_id"] != ledger[1]["citation_id"]
    assert ledger[0]["source_id"] != ledger[1]["source_id"]


def test_publication_age_is_not_converted_into_event_time():
    row = item(0, "Why Nvidia is lower today")
    row["published_at_utc"] = "2026-10-08T12:00:00Z"
    row["accepted_at_utc"] = "2026-10-08T11:00:00Z"
    result = pack_news_context(AUDIT, [row])
    evidence = result["citation_ledger"][0]
    assert evidence["age_hours"] == 145
    assert evidence["event_at_utc"] is None and evidence["event_time_basis"] == "not_extracted"
    assert "publication-relative" in result["text"]


def test_sec_acceptance_claim_does_not_substitute_for_acquisition_receipt():
    row = item()
    row["accepted_at_utc"] = "2026-10-14T11:00:00Z"
    row["available_at_utc"] = None
    result = pack_news_context(AUDIT, [row])
    assert result["included_count"] == 0
    assert result["omitted"][0]["reason"] == "unknown_capture_time"


def test_future_capture_and_missing_cutoff_do_not_become_usable_quotes():
    row = item()
    row["captured_at_utc"] = "2026-10-15T13:00:00Z"
    assert pack_news_context(AUDIT, [row])["omitted"][0]["reason"] == "captured_after_cutoff"
    result = pack_news_context({**AUDIT, "as_of_utc": None}, [item()])
    assert result["included_count"] == 0
    assert result["omitted"][0]["reason"] == "unknown_cutoff"


def test_empty_or_unavailable_news_keeps_its_state_in_the_model_segment():
    packed = pack_news_context({**AUDIT, "status": "unavailable"}, [])
    assert 'status="unavailable"' in packed["text"]
    assert "included=0" in packed["text"]


def test_intended_consumer_is_not_marked_as_provider_execution():
    audit = {"prompt_context": pack_news_context(AUDIT, [item()])}
    text = news_context_for_role(audit, "debate")
    consumer = audit["context_consumers"]["debate"]
    assert consumer["state"] == "prepared"
    assert consumer["text_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    audit["prompt_context"]["text"] += "changed"
    with pytest.raises(ValueError, match="changed"):
        news_context_for_role(audit, "risk")


def test_reference_resolution_does_not_claim_entailment_or_reject_a_decision():
    packed = pack_news_context(AUDIT, [item()])
    label = packed["citation_ledger"][0]["citation_id"]
    result = audit_news_references(f"A claim [{label}]; another [E99:bad].", packed)
    assert result["state"] == "unknown_references" and result["unknown"] == ["E99:bad"]
    assert result["cited"] == [label]
    assert result["entailment_verified"] is False and result["coverage_of_claims_verified"] is False
    assert audit_news_references("No citations", packed)["state"] == "no_references"
    assert audit_news_references({"reason": f"Claim [{label}]"}, packed)["state"] == "references_resolve"


@pytest.mark.parametrize("budget", [100, True, 2000.5])
def test_invalid_context_budget_fails_before_slicing_evidence(budget):
    with pytest.raises(ValueError):
        pack_news_context(AUDIT, [item()], max_chars=budget)
