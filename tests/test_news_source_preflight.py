"""Synthetic archived-input checks; no live article, human annotation or model call."""

import copy
import hashlib
import json

import pytest

from eval.news_shadow_score import InvalidCohort, main as score_main, preflight_sources, score
from eval.news_source_preflight import main


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path):
    raw = "ACME reports results.\n营收增加。\n".encode("utf-8")
    snapshot = tmp_path / "snapshots" / "acme.txt"
    snapshot.parent.mkdir()
    snapshot.write_bytes(raw)
    start = len("ACME reports results.\n".encode("utf-8"))
    span = {"span_id": "claim-1", "start_byte": start, "end_byte": len(raw) - 1,
            "span_sha256": _digest(raw[start:-1])}
    source = {"source_id": "src-1", "source_sha256": _digest(raw),
              "source_url": "https://example.test/acme", "source_rights": "synthetic-only",
              "published_at_utc": "2026-09-01T00:00:00Z", "available_at_utc": "2026-09-01T01:00:00Z"}
    manifest = {
        "cohort_id": "synthetic-archive-v1", "sample_kind": "synthetic",
        "primary_class_rule": "Guidance takes precedence over earnings.",
        "frozen_at_utc": "2026-09-30T00:00:00Z", "require_source_bundle": True,
        "cases": [{**source, "case_id": "one", "event_group_id": "event-1", "split": "test",
                   "ticker": "ACME", "language": "en", "evidence_span_ids": ["claim-1"]}],
        "models": [{"model_id": "candidate", "revision": "synthetic-v1", "evidence_capable": True}],
    }
    bundle = {"bundle_schema_version": 1, "cohort_id": manifest["cohort_id"], "sources": [
        {**source, "snapshot_path": "snapshots/acme.txt", "captured_at_utc": "2026-09-02T00:00:00Z",
         "evidence_spans": [span]}]}
    gold = [{"case_id": "one", "source_id": "src-1", "source_sha256": source["source_sha256"],
             "status": "adjudicated", "reviewer_ids": ["synthetic-a", "synthetic-b"],
             "event_type": "earnings", "concerns_company": True, "evidence_span_ids": ["claim-1"]}]
    predictions = [{"model_id": "candidate", "case_id": "one", "source_id": "src-1",
                    "source_sha256": source["source_sha256"], "event_type": "earnings", "concerns_company": True,
                    "evidence_span_ids": ["claim-1"], "abstain": False, "concerns_company_probability": .8,
                    "latency_ms": 12, "usage": {"input_tokens": 10, "output_tokens": 3}}]
    paths = [tmp_path / name for name in ("manifest.json", "gold.jsonl", "predictions.jsonl", "bundle.json")]

    def write():
        paths[0].write_text(json.dumps(manifest), encoding="utf-8")
        paths[3].write_text(json.dumps(bundle), encoding="utf-8")
        for path, rows in zip(paths[1:3], (gold, predictions)):
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return paths

    return manifest, bundle, snapshot, write


def test_preflight_without_gold_or_predictions_has_only_unreviewed_rows(tmp_path):
    manifest, bundle, snapshot, write = _fixture(tmp_path)
    paths = write()
    paths[1].unlink()
    paths[2].unlink()
    report = preflight_sources(paths[0], paths[3])
    verification = report["source_verification"]
    assert verification["mode"] == "snapshot_bytes_verified"
    assert verification["verified_sources"] == verification["verified_spans"] == 1
    assert verification["sources"][0]["snapshot_bytes"] == len(snapshot.read_bytes())
    assert report["input_sha256"]["source_bundle"] == _digest(paths[3].read_bytes())
    assert report["gold_status"] == report["predictions_status"] == "not_checked"
    assert report["unreviewed_cases"][0]["reviewer_id"] is None
    assert report["unreviewed_cases"][0]["event_type"] is None
    assert report["unreviewed_cases"][0]["concerns_company"] is None
    assert report["unreviewed_cases"][0]["evidence_span_ids"] == []


def test_score_requires_requested_bundle_and_preserves_metrics(tmp_path):
    manifest, bundle, snapshot, write = _fixture(tmp_path)
    paths = write()
    with pytest.raises(InvalidCohort, match="requires a source bundle"):
        score(*paths[:3])
    result = score(*paths[:3], source_bundle_path=paths[3])
    assert result["source_verification"]["verified_sources"] == 1
    assert result["models"]["candidate"]["company_relevance"]["brier_full_cohort"] == pytest.approx(.04)
    manifest["require_source_bundle"] = False
    legacy = score(*write()[:3])
    assert legacy["source_verification"]["mode"] == "metadata_only"
    assert "source_bundle" not in legacy["input_sha256"]
    assert legacy["models"] == result["models"]


def test_changed_snapshot_fails_even_with_unchanged_declared_hash(tmp_path):
    _, _, snapshot, write = _fixture(tmp_path)
    paths = write()
    snapshot.write_bytes(snapshot.read_bytes().replace(b"ACME", b"SCAM"))
    with pytest.raises(InvalidCohort, match="snapshot bytes"):
        preflight_sources(paths[0], paths[3])


@pytest.mark.parametrize("kind", ["empty", "non_utf8", "oversized"])
def test_snapshot_must_be_bounded_nonempty_utf8(tmp_path, kind):
    manifest, bundle, snapshot, write = _fixture(tmp_path)
    raw = {"empty": b"", "non_utf8": b"\xff", "oversized": b"x" * (16 * 1024 * 1024 + 1)}[kind]
    snapshot.write_bytes(raw)
    manifest["cases"][0]["source_sha256"] = bundle["sources"][0]["source_sha256"] = _digest(raw)
    paths = write()
    with pytest.raises(InvalidCohort, match="UTF-8|16 MiB"):
        preflight_sources(paths[0], paths[3])


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate", "wrong_cohort", "wrong_schema", "bool_schema"])
def test_bundle_must_cover_every_source_exactly_once(tmp_path, change):
    _, bundle, _, write = _fixture(tmp_path)
    if change == "missing":
        bundle["sources"] = []
    elif change == "extra":
        bundle["sources"].append({"source_id": "unknown"})
    elif change == "duplicate":
        bundle["sources"].append(copy.deepcopy(bundle["sources"][0]))
    elif change == "wrong_cohort":
        bundle["cohort_id"] = "other"
    else:
        bundle["bundle_schema_version"] = True if change == "bool_schema" else 2
    paths = write()
    with pytest.raises(InvalidCohort):
        preflight_sources(paths[0], paths[3])


@pytest.mark.parametrize("field,value", [
    ("source_url", "https://example.test/other"), ("source_rights", "changed"),
    ("source_sha256", "b" * 64), ("published_at_utc", "2026-08-31T00:00:00Z"),
    ("available_at_utc", "2026-09-01T02:00:00Z"),
    ("captured_at_utc", "2026-09-01T00:30:00Z"), ("captured_at_utc", "2026-10-01T00:00:00Z"),
])
def test_bundle_metadata_and_capture_order_are_bound(tmp_path, field, value):
    _, bundle, _, write = _fixture(tmp_path)
    bundle["sources"][0][field] = value
    paths = write()
    with pytest.raises(InvalidCohort):
        preflight_sources(paths[0], paths[3])


@pytest.mark.parametrize("path", ["/etc/passwd", "../acme.txt", "snapshots/../acme.txt", "snapshots//acme.txt",
                                  "snapshots\\acme.txt", "C:/acme.txt", "snapshots/missing.txt", "snapshots"])
def test_snapshot_path_cannot_escape_or_reference_a_nonfile(tmp_path, path):
    _, bundle, _, write = _fixture(tmp_path)
    bundle["sources"][0]["snapshot_path"] = path
    paths = write()
    with pytest.raises(InvalidCohort, match="snapshot_path"):
        preflight_sources(paths[0], paths[3])


def test_symlink_outside_bundle_is_rejected(tmp_path):
    _, bundle, snapshot, write = _fixture(tmp_path)
    outside = tmp_path.parent / (tmp_path.name + "-outside.txt")
    outside.write_bytes(snapshot.read_bytes())
    snapshot.unlink()
    snapshot.symlink_to(outside)
    paths = write()
    with pytest.raises(InvalidCohort, match="within the bundle"):
        preflight_sources(paths[0], paths[3])


@pytest.mark.parametrize("change", ["missing", "extra", "duplicate", "range", "hash", "utf8", "bool_offset", "whitespace"])
def test_evidence_range_set_and_content_are_verified(tmp_path, change):
    _, bundle, snapshot, write = _fixture(tmp_path)
    source = bundle["sources"][0]
    span = source["evidence_spans"][0]
    if change == "missing":
        source["evidence_spans"] = []
    elif change == "extra":
        source["evidence_spans"].append({"span_id": "unknown"})
    elif change == "duplicate":
        source["evidence_spans"].append(copy.deepcopy(span))
    elif change == "range":
        span["end_byte"] += 2
    elif change == "hash":
        span["span_sha256"] = "b" * 64
    elif change == "utf8":
        span["start_byte"] += 1
    elif change == "bool_offset":
        span["start_byte"] = True
    else:
        span.update(start_byte=len(snapshot.read_bytes()) - 1, end_byte=len(snapshot.read_bytes()),
                    span_sha256=_digest(b"\n"))
    paths = write()
    with pytest.raises(InvalidCohort):
        preflight_sources(paths[0], paths[3])


def test_shared_source_uses_one_archive_and_union_of_case_spans(tmp_path):
    manifest, bundle, snapshot, write = _fixture(tmp_path)
    second = copy.deepcopy(manifest["cases"][0])
    second.update(case_id="two", ticker="OTHER", evidence_span_ids=[])
    manifest["cases"].append(second)
    paths = write()
    report = preflight_sources(paths[0], paths[3])
    assert report["test_cases"] == 2
    assert report["source_verification"]["verified_sources"] == 1
    assert report["source_verification"]["verified_spans"] == 1
    second["available_at_utc"] = "2026-09-01T02:00:00Z"
    paths = write()
    with pytest.raises(InvalidCohort, match="every manifest case"):
        preflight_sources(paths[0], paths[3])


def test_train_archives_are_checked_but_never_get_review_rows(tmp_path):
    manifest, bundle, _, write = _fixture(tmp_path)
    train_raw = b"Synthetic older training source."
    (tmp_path / "snapshots" / "train.txt").write_bytes(train_raw)
    train = {**manifest["cases"][0], "case_id": "train", "source_id": "src-train", "split": "train",
             "source_url": "https://example.test/train", "event_group_id": "event-train",
             "source_sha256": _digest(train_raw), "evidence_span_ids": []}
    manifest["cases"].append(train)
    bundle["sources"].append({**bundle["sources"][0], "source_id": "src-train",
                              "source_url": train["source_url"], "source_sha256": train["source_sha256"],
                              "snapshot_path": "snapshots/train.txt", "evidence_spans": []})
    paths = write()
    report = preflight_sources(paths[0], paths[3])
    assert report["source_verification"]["verified_sources"] == 2
    assert len(report["unreviewed_cases"]) == 1
    bundle["sources"].pop()
    paths = write()
    with pytest.raises(InvalidCohort, match="missing sources"):
        preflight_sources(paths[0], paths[3])


def test_bundle_hash_binds_changed_capture_metadata(tmp_path):
    _, bundle, _, write = _fixture(tmp_path)
    paths = write()
    first = preflight_sources(paths[0], paths[3])
    bundle["sources"][0]["captured_at_utc"] = "2026-09-03T00:00:00Z"
    paths = write()
    second = preflight_sources(paths[0], paths[3])
    assert first["input_sha256"]["manifest"] == second["input_sha256"]["manifest"]
    assert first["input_sha256"]["source_bundle"] != second["input_sha256"]["source_bundle"]


@pytest.mark.parametrize("value", [None, "true", 1])
def test_require_source_bundle_is_boolean(tmp_path, value):
    manifest, _, _, write = _fixture(tmp_path)
    manifest["require_source_bundle"] = value
    paths = write()
    with pytest.raises(InvalidCohort, match="require_source_bundle"):
        preflight_sources(paths[0], paths[3])


def test_preflight_cli_writes_only_after_all_sources_pass(tmp_path):
    _, _, snapshot, write = _fixture(tmp_path)
    paths = write()
    output = tmp_path / "preflight.json"
    args = ["--manifest", str(paths[0]), "--source-bundle", str(paths[3]), "--output", str(output)]
    main(args)
    good_bytes = output.read_bytes()
    assert json.loads(good_bytes)["report_kind"] == "news_source_preflight"
    snapshot.write_bytes(b"tampered")
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    assert output.read_bytes() == good_bytes
    output.unlink()
    with pytest.raises(SystemExit):
        main(args)
    assert not output.exists()


def test_scorer_cli_binds_bundle_and_does_not_rewrite_output_on_tampering(tmp_path):
    _, _, snapshot, write = _fixture(tmp_path)
    paths = write()
    output = tmp_path / "score.json"
    args = ["--manifest", str(paths[0]), "--gold", str(paths[1]), "--predictions", str(paths[2]),
            "--source-bundle", str(paths[3]), "--output", str(output)]
    score_main(args)
    good_bytes = output.read_bytes()
    assert json.loads(good_bytes)["input_sha256"]["source_bundle"] == _digest(paths[3].read_bytes())
    snapshot.write_bytes(b"tampered")
    with pytest.raises(SystemExit) as error:
        score_main(args)
    assert error.value.code == 2
    assert output.read_bytes() == good_bytes
