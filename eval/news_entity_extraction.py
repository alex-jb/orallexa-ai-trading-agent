"""Pure, exact-span evaluation for a frozen exploratory financial-entity probe.

Missing predictions remain false negatives; invalid/duplicate predictions remain
in precision denominators. Conditional sentiment scores disclose detection scope.
No neural dependency, downloads, market data, or model API calls at import time.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import random

from engine.news_context import anchor_char_span
from eval.news_entity_sentiment import LABELS, validated_annotations


ENTITY_TYPE = "financial_entity"
ENTITY_DESCRIPTION = "Named companies, organizations and financial assets, including currencies, cryptocurrencies and commodities"


def canonical_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def corpus(rows: list) -> dict:
    """Use the same exact gold-annotation policy as the document diagnostic."""
    if not isinstance(rows, list):
        raise ValueError("Dataset must be a list")
    result = {}
    for index, row in enumerate(rows):
        if (not isinstance(row, dict) or not isinstance(row.get("content"), str)
                or not row["content"].strip() or not isinstance(row.get("annotations"), list)):
            continue
        gold, rejected = validated_annotations(row["content"], row["annotations"], index)
        if gold:
            result[index] = {"text": row["content"], "gold": gold, "rejected": rejected,
                             "text_sha256": hashlib.sha256(row["content"].encode("utf-8")).hexdigest()}
    return result


def freeze_protocol(rows: list, *, dataset_sha256: str, model_revision: str,
                    random_count: int = 128, seed: int = 20261029) -> dict:
    if type(random_count) is not int or random_count < 1:
        raise ValueError("random_count must be a positive integer")
    data = corpus(rows)
    indices = sorted(data)
    random_indices = sorted(random.Random(seed).sample(indices, min(random_count, len(indices))))
    opposed = [index for index in indices
               if {"positive", "negative"} <= {a["label"] for a in data[index]["gold"]}]
    return {"schema_version": 1, "protocol": "exploratory_exact_span_entity_sentiment.v1",
            "dataset_sha256": dataset_sha256,
            "model": {"repo": "fastino/gliner2.5-small-v1", "revision": model_revision,
                      "package": "gliner2==2.1.0"},
            "schema": {"entity_type": ENTITY_TYPE, "description": ENTITY_DESCRIPTION,
                       "attribute": "sentiment", "labels": list(LABELS), "qualify_labels": True},
            "inference": {"threshold": .5, "batch_size": 4, "torch_threads": 4},
            "selection": {"seed": seed, "random_count_requested": random_count,
                          "eligible_documents": len(indices),
                          "eligible_gold_mentions": sum(len(item["gold"]) for item in data.values())},
            "cohorts": {"seeded_random": random_indices, "opposing_polarities": opposed},
            "selected_rows": sorted(set(random_indices) | set(opposed)),
            "limits": {"holdout": False, "baselines_previously_inspected": True,
                       "training_contamination_unknown": True, "ticker_linking_evaluated": False,
                       "event_time_evaluated": False, "trading_returns_evaluated": False}}


def _prf(tp: int, predicted: int, gold: int) -> dict:
    return {"true_positives": tp, "predicted": predicted, "gold": gold,
            "precision": tp / predicted if predicted else 0.0,
            "recall": tp / gold if gold else 0.0,
            "f1": 2 * tp / (predicted + gold) if predicted + gold else 0.0}


def _sentiment(pairs: list[tuple[str, str]]) -> dict:
    counts = Counter(pairs)
    labels = (*LABELS, "abstain")
    classes = {}
    for label in LABELS:
        support = sum(counts[label, guess] for guess in labels)
        predicted = sum(counts[gold, label] for gold in LABELS)
        classes[label] = _prf(counts[label, label], predicted, support)
    return {"mentions": len(pairs),
            "accuracy": sum(counts[label, label] for label in LABELS) / len(pairs) if pairs else None,
            "macro_f1": sum(c["f1"] for c in classes.values()) / 3 if pairs else None,
            "abstentions": sum(counts[gold, "abstain"] for gold in LABELS),
            "per_class": classes,
            "confusion": {gold: {pred: counts[gold, pred] for pred in labels} for gold in LABELS}}


def evaluate_extractions(rows: list, protocol: dict, predictions: list[dict]) -> dict:
    data = corpus(rows)
    expected = protocol["selected_rows"]
    if len(expected) != len(set(expected)) or any(index not in data for index in expected):
        raise ValueError("Protocol contains duplicate or unusable rows")
    by_row = {}
    for row in predictions:
        index = row.get("row_index")
        if index not in expected or index in by_row:
            raise ValueError("Prediction row is unexpected or duplicated")
        if row.get("text_sha256") != data[index]["text_sha256"]:
            raise ValueError("Prediction text hash differs from dataset")
        if row.get("protocol_sha256") != canonical_hash(protocol):
            raise ValueError("Prediction protocol differs from frozen protocol")
        if not isinstance(row.get("entities"), list):
            raise ValueError("Prediction entities must be a list")
        by_row[index] = row
    if set(by_row) != set(expected):
        raise ValueError("Incomplete predictions; never drop unprocessed rows from denominators")
    if any(index not in by_row for cohort in protocol["cohorts"].values() for index in cohort):
        raise ValueError("Cohort rows are outside the frozen selection")
    results = {}
    for name, indices in protocol["cohorts"].items():
        if len(indices) != len(set(indices)):
            raise ValueError("Cohort contains duplicated rows")
        predicted_n = gold_n = detection_tp = joint_tp = invalid_n = failures = 0
        conditional = []
        broadcast = defaultdict(list)
        latencies = []
        for index in indices:
            item, output = data[index], by_row[index]
            gold = {(a["start"], a["end"]): a["label"] for a in item["gold"]}
            raw = output["entities"]
            if output.get("error_type"):
                if raw:
                    raise ValueError("Failed inference must not contain predictions")
                failures += 1
            gold_n += len(gold)
            predicted_n += len(raw)
            valid = defaultdict(list)
            for entity in raw:
                try:
                    anchor_char_span(item["text"], entity["start"], entity["end"], entity["text"])
                except (KeyError, TypeError, ValueError, UnicodeError):
                    invalid_n += 1
                    continue
                attribute = entity.get("sentiment")
                label = attribute.get("label") if isinstance(attribute, dict) else None
                valid[entity["start"], entity["end"]].append(label if label in LABELS else "abstain")
            detection_tp += len(set(valid) & set(gold))
            joint_tp += sum(label in valid.get(span, []) for span, label in gold.items())
            for span in set(valid) & set(gold):
                guesses = valid[span]
                conditional.append((gold[span], guesses[0] if len(guesses) == 1 else "abstain"))
                for backend in ("vader", "keywords"):
                    label = output.get("document_labels", {}).get(backend)
                    broadcast[backend].append((gold[span], label if label in LABELS else "abstain"))
            latency = output.get("elapsed_seconds")
            if isinstance(latency, (int, float)) and not isinstance(latency, bool) and latency >= 0:
                latencies.append(float(latency))
        results[name] = {"documents": len(indices), "inference_errors": failures,
                         "invalid_prediction_spans": invalid_n,
                         "detection": _prf(detection_tp, predicted_n, gold_n),
                         "joint_span_and_sentiment": _prf(joint_tp, predicted_n, gold_n),
                         "sentiment_on_detected_gold_spans": _sentiment(conditional),
                         "broadcast_on_same_detected_spans": {
                             backend: _sentiment(broadcast[backend]) for backend in ("vader", "keywords")},
                         "latency": {"timed_documents": len(latencies),
                                     "total_seconds": sum(latencies),
                                     "mean_seconds": sum(latencies) / len(latencies) if latencies else None}}
    return {"schema_version": 1, "protocol_sha256": canonical_hash(protocol),
            "prediction_log_sha256": canonical_hash(predictions), "complete": True,
            "scope": protocol.get("limits", {}), "cohorts": results}
