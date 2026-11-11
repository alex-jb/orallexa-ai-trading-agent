"""Metrics and protocol tests with synthetic data, without neural dependencies."""
from copy import deepcopy

import pytest

from eval.news_entity_extraction import corpus, evaluate_extractions, freeze_protocol, canonical_hash


ROWS = [{"content": "Alpha rises; Beta falls.", "annotations": [
    {"start": 0, "end": 5, "value": "Alpha", "label": "Positive"},
    {"start": 13, "end": 17, "value": "Beta", "label": "Negative"}]}]


def entity(start=0, end=5, text="Alpha", label="positive"):
    return {"start": start, "end": end, "text": text, "sentiment": {"label": label}}


def prediction(entities, **extra):
    return {"row_index": 0, "text_sha256": corpus(ROWS)[0]["text_sha256"], "entities": entities,
            "protocol_sha256": canonical_hash(freeze_protocol(ROWS, dataset_sha256="fixture", model_revision="fixture")),
            "document_labels": {"vader": "positive", "keywords": "neutral"}, **extra}


def score(predictions):
    protocol = freeze_protocol(ROWS, dataset_sha256="fixture", model_revision="fixture")
    return evaluate_extractions(ROWS, protocol, predictions)["cohorts"]["seeded_random"]


def test_missing_entities_stay_in_recall_and_detection_is_separate_from_sentiment():
    result = score([prediction([entity()])])
    assert result["detection"]["precision"] == 1
    assert result["detection"]["recall"] == .5
    assert result["joint_span_and_sentiment"]["f1"] == pytest.approx(2 / 3)
    assert result["sentiment_on_detected_gold_spans"]["accuracy"] == 1
    assert result["sentiment_on_detected_gold_spans"]["mentions"] == 1


def test_opposite_labels_can_differ_from_broadcast_on_identical_detected_spans():
    result = score([prediction([entity(), entity(13, 17, "Beta", "negative")])])
    assert result["joint_span_and_sentiment"]["f1"] == 1
    assert result["broadcast_on_same_detected_spans"]["vader"]["accuracy"] == .5
    assert result["sentiment_on_detected_gold_spans"]["accuracy"] == 1


def test_bad_offsets_and_duplicate_predictions_remain_false_positives():
    result = score([prediction([entity(), entity(), entity(1, 6, "Alpha")])])
    assert result["detection"]["predicted"] == 3
    assert result["detection"]["precision"] == pytest.approx(1 / 3)
    assert result["invalid_prediction_spans"] == 1
    assert result["joint_span_and_sentiment"]["precision"] == pytest.approx(1 / 3)
    assert result["sentiment_on_detected_gold_spans"]["abstentions"] == 1


@pytest.mark.parametrize("label", [None, "buy", "Positive"])
def test_missing_or_unknown_sentiment_is_not_filled_with_neutral(label):
    result = score([prediction([entity(label=label)])])
    assert result["detection"]["recall"] == .5
    assert result["joint_span_and_sentiment"]["true_positives"] == 0
    assert result["sentiment_on_detected_gold_spans"]["accuracy"] == 0
    assert result["sentiment_on_detected_gold_spans"]["abstentions"] == 1


def test_failure_and_empty_extraction_are_distinct_but_both_keep_false_negatives():
    failed = score([prediction([], error_type="RuntimeError")])
    empty = score([prediction([])])
    assert failed["inference_errors"] == 1 and empty["inference_errors"] == 0
    assert failed["detection"]["gold"] == empty["detection"]["gold"] == 2
    assert failed["detection"]["recall"] == empty["detection"]["recall"] == 0
    assert failed["sentiment_on_detected_gold_spans"]["accuracy"] is None


def test_incomplete_duplicate_or_wrong_source_predictions_fail():
    p = prediction([])
    for batch in ([], [p, p], [{**p, "row_index": 999}], [{**p, "text_sha256": "wrong"}],
                  [{**p, "protocol_sha256": "wrong"}],
                  [{**p, "entities": None}], [prediction([entity()], error_type="Error")]):
        with pytest.raises(ValueError):
            score(batch)


def test_protocol_freezes_sampling_and_preserves_separate_cohorts():
    data = ROWS + [{"content": f"Example{i}", "annotations": [
        {"start": 0, "end": 8, "value": f"Example{i}", "label": "Neutral"}]} for i in range(8)]
    before = deepcopy(data)
    p = freeze_protocol(data, dataset_sha256="fixture", model_revision="fixed", random_count=3)
    assert p == freeze_protocol(data, dataset_sha256="fixture", model_revision="fixed", random_count=3)
    assert len(p["cohorts"]["seeded_random"]) == 3
    assert p["cohorts"]["opposing_polarities"] == [0]
    assert data == before
    changed = deepcopy(p);changed["inference"]["threshold"] = .1
    assert canonical_hash(changed) != canonical_hash(p)
    for count in (True, 0, -1):
        with pytest.raises(ValueError):
            freeze_protocol(data, dataset_sha256="fixture", model_revision="fixed", random_count=count)


def test_duplicate_gold_spans_and_mismatched_offsets_share_original_validation_policy():
    data = deepcopy(ROWS)
    data[0]["annotations"].append(deepcopy(data[0]["annotations"][0]))
    data[0]["annotations"][1]["start"] = 12
    assert corpus(data) == {}


def test_chinese_character_offsets_work_without_treating_them_as_bytes():
    rows = [{"content": "苹果上涨。", "annotations": [
        {"start": 0, "end": 2, "value": "苹果", "label": "Positive"}]}]
    protocol = freeze_protocol(rows, dataset_sha256="fixture", model_revision="fixture")
    output = [{"row_index": 0, "text_sha256": corpus(rows)[0]["text_sha256"],
               "protocol_sha256": canonical_hash(protocol),
               "entities": [entity(0, 2, "苹果")]}]
    result = evaluate_extractions(rows, protocol, output)
    assert result["cohorts"]["seeded_random"]["joint_span_and_sentiment"]["f1"] == 1
