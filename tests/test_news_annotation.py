"""Synthetic review traces and a real-source, deliberately unlabelled pilot."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from eval.news_annotation import compare_reviews, finalize_gold, main, prepare_reviews
from eval.news_shadow_score import InvalidCohort, preflight_sources, score


def _write(path, data):
    path.write_text(json.dumps(data) + "\n", encoding="utf-8")


@pytest.fixture
def cohort(tmp_path):
    raw = b"ACME announces quarterly results.\n"
    snapshot = tmp_path / "snapshot.txt"
    snapshot.write_bytes(raw)
    source = {"source_id": "synthetic-source", "source_sha256": hashlib.sha256(raw).hexdigest(),
              "source_url": "https://example.test/acme", "source_rights": "synthetic",
              "published_at_utc": "2026-09-01T00:00:00Z", "available_at_utc": "2026-09-01T01:00:00Z"}
    manifest = {"cohort_id": "synthetic-annotation-v1", "sample_kind": "synthetic",
                "primary_class_rule": "Synthetic annotation rule.", "frozen_at_utc": "2026-10-01T00:00:00Z",
                "require_source_bundle": True,
                "cases": [{**source, "case_id": str(i), "ticker": ticker, "split": "test",
                           "event_group_id": "same-event", "evidence_span_ids": ["headline"]}
                          for i, ticker in enumerate(("ACME", "OTHER"))],
                "models": [{"model_id": "synthetic-model", "revision": "fixture", "evidence_capable": True}]}
    bundle = {"bundle_schema_version": 1, "cohort_id": manifest["cohort_id"], "sources": [
        {**source, "captured_at_utc": "2026-09-02T00:00:00Z", "snapshot_path": "snapshot.txt",
         "evidence_spans": [{"span_id": "headline", "start_byte": 0, "end_byte": len(raw) - 1,
                             "span_sha256": hashlib.sha256(raw[:-1]).hexdigest()}]}]}
    paths = {name: tmp_path / (name + ".json") for name in ("manifest", "bundle", "a", "b", "decision")}
    _write(paths["manifest"], manifest)
    _write(paths["bundle"], bundle)
    prepared = prepare_reviews(paths["manifest"], paths["bundle"])
    reviews = [prepared["review_a.json"], prepared["review_b.json"]]

    def save():
        for key, review in zip(("a", "b"), reviews):
            _write(paths[key], review)

    def complete():
        for i, review in enumerate(reviews):
            review["reviewer_id"] = "synthetic-" + str(i)
            for j, row in enumerate(review["cases"]):
                row.update(status="reviewed", event_type="earnings", concerns_company=j == 0,
                           evidence_span_ids=["headline"])
        save()

    def compare():
        save()
        return compare_reviews(paths["manifest"], paths["bundle"], paths["a"], paths["b"])

    def decide():
        data = compare()["adjudication.json"]
        data["adjudicator_id"] = "synthetic-0"
        for j, row in enumerate(data["cases"]):
            row.update(status="adjudicated", event_type="earnings", concerns_company=j == 0,
                       evidence_span_ids=["headline"], reason="Synthetic explicit decision.")
        _write(paths["decision"], data)
        return data

    def finalize():
        return finalize_gold(paths["manifest"], paths["bundle"], paths["a"], paths["b"], paths["decision"])

    save()
    return paths, reviews, save, complete, compare, decide, finalize


def test_prepare_is_blank_and_copies_are_separate(cohort):
    paths, reviews, _, _, compare, _, _ = cohort
    assert all(review["reviewer_id"] is None for review in reviews)
    assert all(row["status"] == "unreviewed" and row["event_type"] is None
               and row["concerns_company"] is None and row["evidence_span_ids"] == []
               for review in reviews for row in review["cases"])
    reviews[0]["cases"][0]["note"] = "One reviewer only."
    assert "note" not in reviews[1]["cases"][0]
    report = compare()["comparison.json"]
    assert report["counts"] == {"pending": 2, "ambiguous": 0, "agreement": 0, "disagreement": 0}
    assert not report["ready_for_adjudication"] and not report["ready_for_scoring"]


def test_agreement_never_becomes_automatic_gold(cohort):
    paths, _, _, complete, compare, _, finalize = cohort
    complete()
    outputs = compare()
    assert outputs["comparison.json"]["counts"]["agreement"] == 2
    assert outputs["comparison.json"]["ready_for_adjudication"]
    assert not outputs["comparison.json"]["ready_for_scoring"]
    decision = outputs["adjudication.json"]
    decision["adjudicator_id"] = "synthetic-adjudicator"
    _write(paths["decision"], decision)
    with pytest.raises(InvalidCohort, match="explicit adjudication"):
        finalize()


def test_disagreement_and_ambiguity_preserve_all_cases(cohort):
    _, reviews, _, complete, compare, _, finalize = cohort
    complete()
    reviews[1]["cases"][0].update(event_type="regulatory", concerns_company=False, evidence_span_ids=[])
    reviews[1]["cases"][1].update(status="ambiguous", event_type=None, concerns_company=None,
                                  evidence_span_ids=[], note="Synthetic insufficient evidence.")
    report = compare()["comparison.json"]
    assert report["total_cases"] == 2
    assert report["counts"]["ambiguous"] == report["counts"]["disagreement"] == 1
    assert report["cases"][0]["disagreement_fields"] == ["event_type", "concerns_company", "evidence_span_ids"]
    assert report["ready_for_adjudication"]
    # A human may resolve both disagreements and an ambiguous review explicitly.
    paths = cohort[0]
    decision = compare()["adjudication.json"]
    decision["adjudicator_id"] = "synthetic-resolver"
    for row in decision["cases"]:
        row.update(status="adjudicated", event_type="earnings", concerns_company=False,
                   evidence_span_ids=["headline"], reason="Synthetic resolved ambiguity.")
    _write(paths["decision"], decision)
    assert len(finalize()) == 2


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "source", "hash", "ticker", "evidence_map", "manifest_hash", "bundle_hash"])
def test_review_binding_rejects_changed_or_dropped_cases(cohort, mutation):
    _, reviews, _, complete, compare, _, _ = cohort
    complete()
    data = reviews[0]
    if mutation == "missing":
        data["cases"].pop()
    elif mutation == "duplicate":
        data["cases"].append(copy.deepcopy(data["cases"][0]))
    elif mutation == "unknown":
        data["cases"][0]["case_id"] = "unknown"
    elif mutation in ("manifest_hash", "bundle_hash"):
        data["input_sha256"]["manifest" if mutation == "manifest_hash" else "source_bundle"] = "0" * 64
    else:
        key = {"source": "source_id", "hash": "source_sha256", "ticker": "ticker", "evidence_map": "allowed_evidence_span_ids"}[mutation]
        data["cases"][0][key] = ["other"] if mutation == "evidence_map" else "changed"
    with pytest.raises(InvalidCohort):
        compare()


@pytest.mark.parametrize("mutation", ["same_id", "no_id", "invalid_event", "invalid_relevance", "invalid_evidence", "unresolved_labels", "ambiguous_no_note"])
def test_invalid_review_cannot_be_compared(cohort, mutation):
    _, reviews, _, complete, compare, _, _ = cohort
    complete()
    row = reviews[0]["cases"][0]
    if mutation == "same_id":
        reviews[1]["reviewer_id"] = " SYNTHETIC-0 "
    elif mutation == "no_id":
        reviews[0]["reviewer_id"] = None
    elif mutation == "invalid_event":
        row["event_type"] = "profit"
    elif mutation == "invalid_relevance":
        row["concerns_company"] = "true"
    elif mutation == "invalid_evidence":
        row["evidence_span_ids"] = ["unknown"]
    elif mutation == "unresolved_labels":
        row["status"] = "unreviewed"
    else:
        row.update(status="ambiguous", event_type=None, concerns_company=None, evidence_span_ids=[])
    with pytest.raises(InvalidCohort):
        compare()


def test_changed_snapshot_is_checked_again(cohort):
    paths, _, _, complete, compare, _, _ = cohort
    complete()
    (paths["manifest"].parent / "snapshot.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(InvalidCohort, match="snapshot bytes"):
        compare()


def test_pending_review_blocks_finalization(cohort):
    _, reviews, save, complete, _, decide, finalize = cohort
    complete()
    row = reviews[1]["cases"][0]
    row.update(status="unreviewed", event_type=None, concerns_company=None, evidence_span_ids=[])
    save()
    decide()
    with pytest.raises(InvalidCohort, match="two complete reviews"):
        finalize()


@pytest.mark.parametrize("mutation", ["review_changed", "missing_case", "bad_label", "no_reason", "no_adjudicator", "wrong_review_hash"])
def test_invalid_adjudication_cannot_produce_gold(cohort, mutation):
    paths, reviews, save, complete, _, decide, finalize = cohort
    complete()
    decision = decide()
    if mutation == "review_changed":
        reviews[0]["cases"][0]["note"] = "Added after comparison."
        save()
    elif mutation == "missing_case":
        decision["cases"].pop()
    elif mutation == "bad_label":
        decision["cases"][0]["event_type"] = "unknown"
    elif mutation == "no_reason":
        decision["cases"][0]["reason"] = " "
    elif mutation == "no_adjudicator":
        decision["adjudicator_id"] = None
    else:
        decision["review_sha256"]["review_a"] = "0" * 64
    _write(paths["decision"], decision)
    with pytest.raises(InvalidCohort):
        finalize()


def test_explicit_synthetic_gold_is_accepted_by_scorer(cohort):
    paths, _, _, complete, _, decide, finalize = cohort
    complete()
    decide()
    gold = finalize()
    gold_path = paths["manifest"].parent / "gold.jsonl"
    predictions_path = paths["manifest"].parent / "predictions.jsonl"
    gold_path.write_text("".join(json.dumps(row) + "\n" for row in gold), encoding="utf-8")
    predictions = [{key: row[key] for key in ("case_id", "source_id", "source_sha256", "event_type", "concerns_company", "evidence_span_ids")} for row in gold]
    for row in predictions:
        row.update(model_id="synthetic-model", abstain=False, latency_ms=0,
                   usage={"input_tokens": 0, "output_tokens": 0})
    predictions_path.write_text("".join(json.dumps(row) + "\n" for row in predictions), encoding="utf-8")
    assert len(gold) == 2 and all(row["adjudication_sha256"] for row in gold)
    result = score(paths["manifest"], gold_path, predictions_path, source_bundle_path=paths["bundle"])
    assert result["test_cases_scored"] == 2
    assert result["models"]["synthetic-model"]["test_cases"] == 2


def test_prepare_cli_never_overwrites_existing_review_directory(cohort, tmp_path):
    paths = cohort[0]
    output = tmp_path / "reviews"
    argv = ["prepare", "--manifest", str(paths["manifest"]), "--source-bundle", str(paths["bundle"]), "--output-dir", str(output)]
    main(argv)
    existing = output / "review_a.json"
    existing.write_text("preserve human work", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2 and existing.read_text() == "preserve human work"


def test_finalize_cli_preserves_old_output_on_validation_failure_and_success(cohort, tmp_path):
    paths, _, _, complete, _, decide, _ = cohort
    complete()
    decision = decide()
    output = tmp_path / "gold.jsonl"
    output.write_text("existing gold", encoding="utf-8")
    argv = ["finalize", "--manifest", str(paths["manifest"]), "--source-bundle", str(paths["bundle"]),
            "--review-a", str(paths["a"]), "--review-b", str(paths["b"]),
            "--adjudication", str(paths["decision"]), "--output", str(output)]
    decision["cases"][0]["status"] = "unresolved"
    _write(paths["decision"], decision)
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2 and output.read_text() == "existing gold"
    decide()
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2 and output.read_text() == "existing gold"
    output.unlink()
    main(argv)
    assert len(output.read_text().splitlines()) == 2


def test_real_headline_development_pilot_stays_unlabelled():
    root = Path(__file__).resolve().parents[1] / "eval/data/news_source_pilot_2026-10-05"
    report = preflight_sources(root / "manifest.json", root / "bundle.json")
    assert report["sample_kind"] == "development_pilot"
    assert report["test_cases"] == 8
    assert report["source_verification"]["verified_sources"] == 4
    for name in ("review_a.json", "review_b.json"):
        review = json.loads((root / "blank_reviews" / name).read_text())
        assert review["input_sha256"] == report["input_sha256"]
        assert review["reviewer_id"] is None
        assert all(row["status"] == "unreviewed" and row["event_type"] is None
                   and row["concerns_company"] is None and row["evidence_span_ids"] == []
                   for row in review["cases"])
    assert not (root / "gold.jsonl").exists() and not (root / "predictions.jsonl").exists()
