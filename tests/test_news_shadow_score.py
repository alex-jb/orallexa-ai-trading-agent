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
