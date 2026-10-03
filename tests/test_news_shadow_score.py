"""Synthetic schema and accounting tests; no provider or market calls."""

import copy
import json

import pytest

from eval.news_shadow_score import InvalidCohort, main, score


def _fixture(tmp_path):
    hashes = {key: key * 64 for key in ("a", "b", "c")}
    manifest = {
        "cohort_id": "synthetic-scorer-smoke-v1", "sample_kind": "synthetic",
        "primary_class_rule": "Use guidance over earnings when both occur in one article.",
        "frozen_at_utc": "2026-09-30T00:00:00Z",
        "cases": [
            {"case_id": case_id, "source_id": source, "source_sha256": hashes[sha],
             "source_url": f"https://example.test/{source}", "source_rights": "synthetic-only",
             "event_group_id": group, "split": split, "ticker": ticker,
             "published_at_utc": "2026-09-01T00:00:00Z", "available_at_utc": "2026-09-01T01:00:00Z",
             "evidence_span_ids": spans}
            for case_id, source, sha, group, split, ticker, spans in (
                ("train", "src-a", "a", "event-a", "train", "AA", []),
                ("one", "src-b", "b", "event-b", "test", "BB", ["claim-1"]),
                ("two", "src-c", "c", "event-c", "test", "CC", []),
            )],
        "models": [
            {"model_id": "cited", "revision": "synthetic-v1", "evidence_capable": True,
             "pricing_usd_per_million_tokens": {"input": 2, "output": 10}},
            {"model_id": "typed", "revision": "synthetic-v1", "evidence_capable": False,
             "pricing_usd_per_million_tokens": None},
        ],
    }
    gold = [
        {"case_id": "one", "source_id": "src-b", "source_sha256": hashes["b"],
         "status": "adjudicated", "reviewer_ids": ["human-a", "human-b"],
         "event_type": "earnings", "concerns_company": True, "evidence_span_ids": ["claim-1"]},
        {"case_id": "two", "source_id": "src-c", "source_sha256": hashes["c"],
         "status": "adjudicated", "reviewer_ids": ["human-a", "human-b"],
         "event_type": "other", "concerns_company": False, "evidence_span_ids": []},
    ]
    predictions = [
        {"model_id": model, "case_id": item["case_id"], "source_id": item["source_id"],
         "source_sha256": item["source_sha256"], "event_type": item["event_type"],
         "concerns_company": item["concerns_company"], "abstain": False,
         "latency_ms": latency, "usage": {"input_tokens": 100, "output_tokens": 10, "billed_usd": .001},
         **({"evidence_span_ids": item["evidence_span_ids"]} if model == "cited" else {}),
         "concerns_company_probability": p}
        for model in ("cited", "typed")
        for item, latency, p in zip(gold, (100, 300), (.8, .1))
    ]

    def write():
        paths = [tmp_path / file for file in ("manifest.json", "gold.jsonl", "predictions.jsonl")]
        paths[0].write_text(json.dumps(manifest), encoding="utf-8")
        for path, rows in zip(paths[1:], (gold, predictions)):
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return paths

    return manifest, gold, predictions, write


def test_full_cohort_metrics_cost_and_hashes(tmp_path):
    manifest, gold, predictions, write = _fixture(tmp_path)
    paths = write()
    report = score(*paths)
    assert report["manifest_cases"] == 3
    assert report["train_cases_checked_for_leakage"] == 1
    assert report["test_cases_scored"] == 2
    assert len(report["input_sha256"]["gold"]) == 64
    result = report["models"]["cited"]
    assert result["event_type"]["macro_f1"] == 0.5  # all 4 frozen classes, two have zero support
    assert result["company_relevance"]["brier_full_cohort"] == pytest.approx(.025)
    assert result["evidence_exact"] == {"capable": True, "eligible_nonempty_gold": 1,
                                         "cases": 1, "rate_eligible": 1, "rate_full_cohort": .5}
    assert result["usage"]["observed_billed_usd"] == .002
    assert result["usage"]["rate_estimated_usd"] == pytest.approx(.0006)
    assert result["latency_ms"] == {"p50": 100, "p95": 300, "definition": "nearest_rank"}
    assert report["models"]["typed"]["evidence_exact"]["rate_eligible"] is None


def test_abstain_keeps_denominator_and_withholds_brier(tmp_path):
    manifest, gold, predictions, write = _fixture(tmp_path)
    second = next(row for row in predictions if row["model_id"] == "typed" and row["case_id"] == "two")
    second.update(abstain=True, event_type=None, concerns_company=None)
    second.pop("concerns_company_probability")
    report = score(*write())["models"]["typed"]
    assert report["test_cases"] == 2
    assert report["abstentions"] == 1
    assert report["company_relevance"]["accuracy_full_cohort"] == .5
    assert report["company_relevance"]["brier_full_cohort"] is None
    assert report["company_relevance"]["brier_probability_coverage"] == 1


def test_abstention_with_probability_keeps_full_cohort_calibration(tmp_path):
    manifest, gold, predictions, write = _fixture(tmp_path)
    second = next(row for row in predictions if row["model_id"] == "typed" and row["case_id"] == "two")
    second.update(abstain=True, event_type=None, concerns_company=None)
    result = score(*write())["models"]["typed"]
    assert result["abstentions"] == 1
    assert result["company_relevance"]["accuracy_full_cohort"] == .5
    assert result["company_relevance"]["brier_full_cohort"] == pytest.approx(.025)
    assert result["company_relevance"]["brier_probability_coverage"] == 2


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.01, 1.01, True, "0.5"])
def test_bad_probability_rejected(tmp_path, value):
    _, _, predictions, write = _fixture(tmp_path)
    predictions[0]["concerns_company_probability"] = value
    with pytest.raises(InvalidCohort, match="probability|non-JSON numeric"):
        score(*write())


def test_missing_extra_duplicate_predictions_and_gold_rejected(tmp_path):
    manifest, gold, predictions, write = _fixture(tmp_path)
    for modify in (
        lambda rows: rows.pop(),
        lambda rows: rows.append(copy.deepcopy(rows[0])),
        lambda rows: rows[0].update(case_id="unknown"),
        lambda rows: rows[0].update(event_type="rumor"),
    ):
        rows = copy.deepcopy(predictions)
        modify(rows)
        paths = write()
        paths[2].write_text("".join(json.dumps(row) + "\n" for row in rows))
        with pytest.raises(InvalidCohort):
            score(*paths)
    gold.pop()
    with pytest.raises(InvalidCohort, match="gold incomplete"):
        score(*write())


def test_leakage_and_future_rejected(tmp_path):
    manifest, gold, predictions, write = _fixture(tmp_path)
    for change in (
        lambda m: m["cases"][0].update(event_group_id="event-b"),
        lambda m: m["cases"][0].update(source_sha256="b" * 64),
        lambda m: m["cases"][1].update(available_at_utc="2026-10-01T00:00:00Z"),
        lambda m: m["cases"][2].update(case_id="one"),
    ):
        data = copy.deepcopy(manifest)
        change(data)
        paths = write()
        paths[0].write_text(json.dumps(data))
        with pytest.raises(InvalidCohort):
            score(*paths)


@pytest.mark.parametrize("bad_split", [[], {}, None, 1])
def test_malformed_split_is_validation_error(tmp_path, bad_split):
    manifest, gold, predictions, write = _fixture(tmp_path)
    manifest["cases"][0]["split"] = bad_split
    with pytest.raises(InvalidCohort, match="split"):
        score(*write())


def test_ambiguous_gold_rejected_and_partial_probability_withheld(tmp_path):
    manifest, gold, predictions, write = _fixture(tmp_path)
    gold[0]["status"] = "ambiguous"
    with pytest.raises(InvalidCohort, match="unresolved"):
        score(*write())
    gold[0]["status"] = "adjudicated"
    predictions[0].pop("concerns_company_probability")
    result = score(*write())["models"]["cited"]["company_relevance"]
    assert result["brier_full_cohort"] is None
    assert result["brier_probability_coverage"] == 1


def test_same_event_for_two_tickers_in_test_allowed(tmp_path):
    manifest, gold, predictions, write = _fixture(tmp_path)
    manifest["cases"][2]["event_group_id"] = "event-b"
    report = score(*write())
    assert report["test_cases_scored"] == 2
    assert report["test_event_groups"] == 1


def test_failure_kind_is_separate_from_policy_abstention(tmp_path):
    manifest, gold, predictions, write = _fixture(tmp_path)
    second = next(row for row in predictions if row["model_id"] == "typed" and row["case_id"] == "two")
    second.update(abstain=True, event_type=None, concerns_company=None, failure_kind="timeout")
    second.pop("concerns_company_probability")
    report = score(*write())["models"]["typed"]
    assert report["abstentions_by_kind"]["timeout"] == 1
    assert report["abstentions_by_kind"]["policy_or_unclassified"] == 0
    second["concerns_company_probability"] = .1
    with pytest.raises(InvalidCohort, match="failed call cannot supply"):
        score(*write())


def test_no_partial_report_output_on_invalid_input(tmp_path, capsys):
    manifest, gold, predictions, write = _fixture(tmp_path)
    predictions.pop()
    paths = write()
    output = tmp_path / "report.json"
    with pytest.raises(SystemExit) as caught:
        main(["--manifest", str(paths[0]), "--gold", str(paths[1]),
              "--predictions", str(paths[2]), "--output", str(output)])
    assert caught.value.code == 2
    assert not output.exists()
    assert "incomplete" in capsys.readouterr().err


def test_incomplete_billed_cost_not_extrapolated(tmp_path):
    manifest, gold, predictions, write = _fixture(tmp_path)
    predictions[0]["usage"].pop("billed_usd")
    report = score(*write())["models"]["cited"]["usage"]
    assert report["billed_cost_coverage"] == 1
    assert report["observed_billed_usd"] is None
    assert report["rate_estimated_usd"] is not None


def test_selective_coverage_does_not_call_empty_acceptance_perfect(tmp_path):
    _, _, _, write = _fixture(tmp_path)
    report = score(*write())
    assert report["report_schema_version"] == 2
    assert report["thresholds_source"] == "code_default"
    result = report["models"]["cited"]["selective_company_relevance"]
    curve = {row["confidence_threshold"]: row for row in result["curve"]}
    assert curve[0.8]["accepted"] == 2
    assert curve[0.8]["coverage_full_cohort"] == 1
    assert curve[0.8]["relevance_errors"] == 0
    assert curve[0.95]["accepted"] == 0
    assert curve[0.95]["withheld"] == 2
    assert curve[0.95]["relevance_error_rate_accepted"] is None
    assert curve[0.95]["joint_event_and_relevance_accuracy_accepted"] is None
    assert report["models"]["cited"]["company_relevance"]["brier_full_cohort"] == pytest.approx(.025)


def test_confident_wrong_answer_is_counted_as_an_error(tmp_path):
    manifest, _, predictions, write = _fixture(tmp_path)
    manifest["relevance_confidence_thresholds"] = [0.5, 0.9]
    predictions[0].update(concerns_company=False, concerns_company_probability=.02)
    report = score(*write())
    assert report["thresholds_source"] == "manifest"
    result = report["models"]["cited"]["selective_company_relevance"]["curve"][1]
    assert result["accepted"] == 2
    assert result["relevance_errors"] == 1
    assert result["relevance_error_rate_accepted"] == .5


def test_gate_uses_probability_of_emitted_label_not_max_probability(tmp_path):
    _, _, predictions, write = _fixture(tmp_path)
    predictions[0].update(concerns_company=False, concerns_company_probability=.99)
    result = score(*write())["models"]["cited"]["selective_company_relevance"]
    assert result["label_probability_disagreements"] == 1
    curve = {row["confidence_threshold"]: row for row in result["curve"]}
    assert curve[0.0]["relevance_errors"] == 1
    assert curve[0.5]["accepted"] == 1
    assert curve[0.5]["coverage_full_cohort"] == .5


def test_relevance_confidence_does_not_claim_correct_event_type(tmp_path):
    _, _, predictions, write = _fixture(tmp_path)
    predictions[0]["event_type"] = "guidance"
    result = score(*write())["models"]["cited"]["selective_company_relevance"]["curve"][0]
    assert result["relevance_error_rate_accepted"] == 0
    assert result["joint_event_and_relevance_accuracy_accepted"] == .5


def test_probability_on_abstention_does_not_restore_answer_coverage(tmp_path):
    _, _, predictions, write = _fixture(tmp_path)
    predictions[0].update(abstain=True, event_type=None, concerns_company=None, evidence_span_ids=[])
    result = score(*write())["models"]["cited"]
    assert result["company_relevance"]["brier_probability_coverage"] == 2
    gate = result["selective_company_relevance"]
    assert gate["excluded_abstentions"] == 1
    assert gate["eligible_answered_with_probability"] == 1
    assert gate["curve"][0]["coverage_full_cohort"] == .5


def test_failures_and_missing_probability_keep_full_cohort_denominator(tmp_path):
    _, _, predictions, write = _fixture(tmp_path)
    predictions[0].update(abstain=True, event_type=None, concerns_company=None,
                          evidence_span_ids=[], failure_kind="timeout")
    predictions[0].pop("concerns_company_probability")
    predictions[1].pop("concerns_company_probability")
    gate = score(*write())["models"]["cited"]["selective_company_relevance"]
    assert gate["test_cases"] == 2
    assert gate["excluded_abstentions"] == 1
    assert gate["excluded_answered_without_probability"] == 1
    assert all(row["accepted"] == 0 and row["withheld"] == 2 for row in gate["curve"])


def test_language_slices_expose_difficult_subset_without_dropping_it(tmp_path):
    manifest, _, predictions, write = _fixture(tmp_path)
    manifest["cases"][0]["language"] = "fr"  # train must not enter slices
    manifest["cases"][1]["language"] = "en"
    manifest["cases"][2]["language"] = "zh-hans"
    predictions[1].update(abstain=True, event_type=None, concerns_company=None, evidence_span_ids=[])
    predictions[1].pop("concerns_company_probability")
    result = score(*write())["models"]["cited"]
    assert set(result["language_slices"]) == {"en", "zh-hans"}
    assert sum(v["test_cases"] for v in result["language_slices"].values()) == 2
    english = result["language_slices"]["en"]
    chinese = result["language_slices"]["zh-hans"]
    assert english["company_relevance"]["brier_full_cohort"] == pytest.approx(.04)
    assert chinese["company_relevance"]["brier_full_cohort"] is None
    assert chinese["company_relevance"]["accuracy_full_cohort"] == 0
    assert chinese["selective_company_relevance"]["curve"][0]["coverage_full_cohort"] == 0
    assert result["company_relevance"]["brier_full_cohort"] is None


def test_legacy_language_unknown_is_explicit_not_inferred(tmp_path):
    _, _, _, write = _fixture(tmp_path)
    result = score(*write())["models"]["cited"]["language_slices"]
    assert set(result) == {"und"}
    assert result["und"]["test_cases"] == 2


@pytest.mark.parametrize("thresholds", [[], "0.8", [0.8, 0.8], [0.9, 0.5],
                                         [-0.1], [1.1], [True], [None], [float("nan")]])
def test_invalid_frozen_thresholds_are_rejected(tmp_path, thresholds):
    manifest, _, _, write = _fixture(tmp_path)
    manifest["relevance_confidence_thresholds"] = thresholds
    with pytest.raises(InvalidCohort, match="threshold|non-JSON numeric"):
        score(*write())


@pytest.mark.parametrize("language", [None, [], "", "EN", "en_US", "English", " en"])
def test_invalid_language_metadata_is_rejected(tmp_path, language):
    manifest, _, _, write = _fixture(tmp_path)
    manifest["cases"][1]["language"] = language
    with pytest.raises(InvalidCohort, match="language"):
        score(*write())


def test_threshold_and_language_changes_alter_manifest_hash(tmp_path):
    manifest, _, _, write = _fixture(tmp_path)
    initial = score(*write())["input_sha256"]["manifest"]
    manifest["relevance_confidence_thresholds"] = [0.5, 0.9]
    changed_threshold = score(*write())["input_sha256"]["manifest"]
    manifest["cases"][1]["language"] = "en"
    changed_language = score(*write())["input_sha256"]["manifest"]
    assert len({initial, changed_threshold, changed_language}) == 3


def test_inclusive_threshold_and_exact_probability_endpoints(tmp_path):
    manifest, _, predictions, write = _fixture(tmp_path)
    manifest["relevance_confidence_thresholds"] = [0.8, 1.0]
    report = score(*write())["models"]["cited"]["selective_company_relevance"]
    assert report["curve"][0]["accepted"] == 2
    predictions[0]["concerns_company_probability"] = 1.0
    predictions[1]["concerns_company_probability"] = 0.0
    report = score(*write())["models"]["cited"]["selective_company_relevance"]
    assert report["curve"][1]["accepted"] == 2
