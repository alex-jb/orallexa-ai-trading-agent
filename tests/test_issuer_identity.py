"""Issuer linking checks with controlled catalogs and exact source spans."""
from copy import deepcopy
import hashlib
import json

import pytest

from engine.issuer_identity import IssuerDirectory, SEC_DIRECTORY_URL, audit_issuer_mentions
from engine.news_research import snapshot_record
from eval.run_issuer_identity_probe import main


CAPTURE = "2026-11-11T21:00:00Z"
CUTOFF = "2026-11-11T22:00:00Z"
ROWS = [
    [320193, "Apple Inc.", "AAPL", "Nasdaq"],
    [1652044, "Alphabet Inc.", "GOOG", "Nasdaq"],
    [1652044, "Alphabet Inc.", "GOOGL", "Nasdaq"],
    [1067983, "BERKSHIRE HATHAWAY INC", "BRK-A", "NYSE"],
    [1067983, "BERKSHIRE HATHAWAY INC", "BRK-B", "NYSE"],
    [1090872, "AGILENT TECHNOLOGIES, INC.", "A", "NYSE"],
    [789019, "MICROSOFT CORP", "MSFT", "Nasdaq"],
    [1973239, "ARM HOLDINGS PLC /UK", "ARM", "Nasdaq"],
    [11, "Twin Corp", "TWIN", "Nasdaq"],
    [22, "Twin Corporation", "TWIN", "NYSE"],
    [33, "Split Co", "AAA-B", "NYSE"],
    [44, "Other Co", "AAA.B", "NYSE"],
    [55, "One Venue Co", "OV", None],
    [55, "One Venue Co", "OV", "OTC"],
]


def capture(rows=ROWS, *, time=CAPTURE, fields=None):
    raw = json.dumps({"fields": fields if fields is not None else ["cik", "name", "ticker", "exchange"],
                      "data": rows}).encode()
    return raw, {"source_url": SEC_DIRECTORY_URL, "captured_at_utc": time,
                 "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


@pytest.fixture
def directory():
    return IssuerDirectory.from_capture(*capture())


def snapshot(text, *, published="2026-11-11T20:00:00Z", captured=CAPTURE):
    return snapshot_record({"title": text, "url": "https://example.invalid/identity-fixture",
                            "provider": "synthetic", "published": published},
                           source="synthetic", captured_at=captured)


def mention(text, quote):
    start = text.index(quote)
    return {"start": start, "end": start + len(quote), "text": quote}


def test_catalog_validates_body_and_observation_time_before_indexing():
    raw, receipt = capture()
    for changed, meta in [(raw + b" ", receipt), (raw, {**receipt, "bytes": True}),
                          (raw, {**receipt, "captured_at_utc": "2026-11-11T21:00:00"}),
                          (raw, {**receipt, "source_url": "https://example.invalid/catalog"})]:
        with pytest.raises(ValueError):
            IssuerDirectory.from_capture(changed, meta)


def test_catalog_accepts_named_columns_and_counts_exact_duplicates():
    directory = IssuerDirectory.from_capture(*capture(
        [["AAPL", "Apple Inc.", "Nasdaq", "0000320193", "other"]] * 2,
        fields=["ticker", "name", "exchange", "cik", "extra"]))
    assert directory.receipt["input_rows"] == 2
    assert directory.receipt["distinct_rows"] == 1
    assert directory.resolve_symbol("AAPL")["issuer_cik"] == "0000320193"


@pytest.mark.parametrize("rows,fields", [
    ([[True, "Alpha Inc", "ALPH", "NYSE"]], None),
    ([[1, "Alpha Inc", "ＡＬＰＨ", "NYSE"]], None),
    ([[1, "Alpha Inc", "ALPH", 12]], None),
    ([[1, "Alpha Inc", "ALPH"]], None),
    (ROWS, ["name", "name", "ticker", "exchange"]),
    ([], None),
])
def test_malformed_rows_do_not_silently_reduce_the_directory(rows, fields):
    with pytest.raises(ValueError):
        IssuerDirectory.from_capture(*capture(rows, fields=fields))


@pytest.mark.parametrize("name,cik", [
    ("apple INC.", "0000320193"),
    ("Microsoft Corporation", "0000789019"),
    ("Arm Holdings PLC", "0001973239"),
    ("CIK:320193", "0000320193"),
])
def test_issuer_name_and_cik_never_select_a_security(directory, name, cik):
    result = directory.resolve_mention(name)
    assert result["status"] == "issuer_match"
    assert result["issuer_cik"] == cik
    assert result["symbol"] is None


def test_short_alias_bare_ticker_and_subsidiary_are_not_hard_links(directory):
    apple = directory.resolve_mention("Apple")
    assert apple["status"] == "name_candidate" and apple["issuer_cik"] is None
    assert apple["matched_rows"][0]["ticker"] == "AAPL"
    assert directory.resolve_mention("A")["match_basis"] == "explicit_symbol_required"
    assert directory.resolve_mention("GOOGL")["issuer_cik"] is None
    assert directory.resolve_mention("Google")["status"] == "unresolved"
    assert directory.resolve_mention("$A")["issuer_cik"] == "0001090872"


def test_name_ticker_and_normalized_spelling_collisions_abstain(directory):
    for value in ("Twin Corp", "Twin", "$TWIN", "NYSE:AAA-B"):
        result = directory.resolve_mention(value)
        assert result["status"] == "ambiguous"
        assert result["issuer_cik"] is None and result["symbol"] is None
        assert len(result["matched_rows"]) == 2
    assert directory.resolve_mention("NYSE:TWIN")["issuer_cik"] == "0000000022"
    assert directory.resolve_mention("CBOE:TWIN")["status"] == "unresolved"


def test_multiple_venues_can_identify_issuer_without_selecting_instrument(directory):
    result = directory.resolve_mention("$OV")
    assert result["status"] == "issuer_match" and result["symbol"] is None
    assert result["issuer_cik"] == "0000000055"
    assert directory.resolve_mention("OTC:OV")["symbol"] == {"ticker": "OV", "exchange": "OTC"}


def test_focus_relations_keep_other_share_class_and_utf8_evidence(directory):
    text = "资料：$GOOG and NASDAQ:GOOGL; Apple Inc."
    result = audit_issuer_mentions(directory, snapshot(text),
                                   [mention(text, q) for q in ("$GOOG", "NASDAQ:GOOGL", "Apple Inc.")],
                                   as_of=CUTOFF, focus_symbol="GOOGL")
    first, second, third = result["mentions"]
    assert (first["focus_relation"], first["focus_symbol_relation"]) == ("same_issuer", "other_symbol_same_issuer")
    assert second["focus_symbol_relation"] == "same_symbol"
    assert third["focus_relation"] == "different_issuer"
    assert first["start_char"] == 3 and first["start_byte"] == 9 and first["end_byte"] == 14
    assert first["span_sha256"] == hashlib.sha256(b"$GOOG").hexdigest()
    assert not result["scope"]["used_for_trading"] and not result["scope"]["event_role_evaluated"]


def test_share_class_punctuation_keeps_directory_symbol(directory):
    text = "NYSE:BRK.B was cited."
    result = audit_issuer_mentions(directory, snapshot(text), [mention(text, "NYSE:BRK.B")],
                                   as_of=CUTOFF, focus_symbol="BRK-A")["mentions"][0]
    assert result["symbol"]["ticker"] == "BRK-B"
    assert result["focus_symbol_relation"] == "other_symbol_same_issuer"


def test_rejects_partial_wrong_and_repeated_spans_without_recounting(directory):
    text = "$BRK.B and Apple Inc."
    correct = mention(text, "Apple Inc.")
    rows = [mention(text, "$BRK"), {**correct, "start": True}, {**correct, "text": "Microsoft"}, correct, correct]
    result = audit_issuer_mentions(directory, snapshot(text), rows, as_of=CUTOFF)
    assert [r["status"] for r in result["mentions"]] == ["invalid_span"] * 3 + ["issuer_match", "duplicate_span"]
    assert sum(result["mention_status_counts"].values()) == len(rows)


def test_future_directory_and_future_news_both_stop_linking(directory):
    text = "$AAPL"
    m = [mention(text, text)]
    early = audit_issuer_mentions(directory, snapshot(text), m,
                                  as_of="2026-11-11T20:59:59Z", focus_symbol="AAPL")
    assert early["reason"] == "directory_after_cutoff" and early["focus"] is None
    assert early["mentions"] == [{"mention_index": 0, "origin": "provided", "status": "blocked", "reason": "directory_after_cutoff"}]
    future = audit_issuer_mentions(directory, snapshot(text, captured="2026-11-11T22:00:01Z"), m, as_of=CUTOFF)
    assert future["reason"] == "captured_after_cutoff"
    equal = audit_issuer_mentions(directory, snapshot(text), m, as_of=CAPTURE)
    assert equal["mentions"][0]["status"] == "symbol_match"


def test_tampered_or_malformed_snapshot_does_not_link(directory):
    text = "$AAPL"
    for item, reason in [(None, "invalid_snapshot"),
                         ({**snapshot(text), "snapshot_text": text + " extra"}, "snapshot_hash_mismatch")]:
        result = audit_issuer_mentions(directory, item, [mention(text, text)], as_of=CUTOFF)
        assert result["status"] == "blocked" and result["reason"] == reason
        assert result["mention_status_counts"] == {"blocked": 1}
    for kwargs in ({"as_of": "2026-11-11"}, {"as_of": CUTOFF, "focus_symbol": "Apple Inc."}):
        with pytest.raises(ValueError):
            audit_issuer_mentions(directory, snapshot(text), [], **kwargs)


def test_explicit_scan_preserves_notation_without_promoting_bare_words(directory):
    text = "资料：$GOOG, NASDAQ:GOOGL, CIK:320193; $12 and A; NYSE:$MSFT; xx$AAPL; $AAPL_tail."
    result = audit_issuer_mentions(directory, snapshot(text), [mention(text, "$GOOG")],
                                   as_of=CUTOFF, scan_explicit=True)
    assert result["provided_mentions"] == 1 and result["explicit_scan_mentions"] == 3
    assert [(row["quote"], row["status"]) for row in result["mentions"]] == [
        ("$GOOG", "symbol_match"), ("$GOOG", "duplicate_span"),
        ("NASDAQ:GOOGL", "symbol_match"), ("CIK:320193", "issuer_match")]
    assert all(row["origin"] == "explicit_scan" for row in result["mentions"][1:])
    blocked = audit_issuer_mentions(directory, snapshot(text), [],
                                   as_of="2026-11-11T20:59:59Z", scan_explicit=True)
    assert blocked["status"] == "blocked" and blocked["explicit_scan_mentions"] == 0


def test_cli_creates_hash_bound_report_and_refuses_overwrite(tmp_path):
    raw, receipt = capture()
    cat, meta, src, out = [tmp_path / n for n in ("dir.json", "receipt.json", "input.json", "out.json")]
    cat.write_bytes(raw)
    meta.write_text(json.dumps(receipt))
    text = "$AAPL and Apple"
    record = {"id": "sample", "snapshot": snapshot(text), "mentions": [mention(text, "$AAPL"), mention(text, "Apple")]}
    src.write_text(json.dumps({"records": [record]}))
    argv = ["--directory", str(cat), "--receipt", str(meta), "--input", str(src),
            "--as-of", CUTOFF, "--focus-symbol", "AAPL", "--output", str(out)]
    assert main(argv) == 0
    data = json.loads(out.read_bytes())
    assert data["input_sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert data["mention_status_counts"] == {"symbol_match": 1, "name_candidate": 1}
    assert data["records"][0]["mentions"][0]["focus_symbol_relation"] == "same_symbol"
    before = out.read_bytes()
    with pytest.raises(SystemExit):
        main(argv)
    assert out.read_bytes() == before
    new_out = tmp_path / "duplicate.json"
    src.write_text(json.dumps({"records": [record, deepcopy(record)]}))
    with pytest.raises(SystemExit):
        main([*argv[:-1], str(new_out)])
    assert not new_out.exists()
