"""Offline diagnosis of document sentiment broadcast to gold entity mentions.

Accepts the published FinEntity JSON shape. This is a full-corpus diagnostic,
not the paper's train/test protocol, an entity extractor, or a trading backtest.
The CLI explicitly selects a local scorer; it never loads a transformer model,
downloads data, or invokes a model API. Reports contain hashes, not news text.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
from typing import Callable

from engine.news_context import anchor_char_span


LABELS = ("negative", "neutral", "positive")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _metrics(pairs: list[tuple[str, str]], documents: int) -> dict:
    counts = Counter(pairs)
    n = len(pairs)
    per_class = {}
    for label in LABELS:
        true = counts[label, label]
        support = sum(counts[label, predicted] for predicted in LABELS)
        predicted_n = sum(counts[gold, label] for gold in LABELS)
        precision = true / predicted_n if predicted_n else 0.0
        recall = true / support if support else 0.0
        f1 = 2 * true / (support + predicted_n) if support + predicted_n else 0.0
        per_class[label] = {"support": support, "precision": precision, "recall": recall, "f1": f1}
    return {"documents": documents, "mentions": n,
            "accuracy": sum(counts[label, label] for label in LABELS) / n if n else None,
            "macro_f1": sum(row["f1"] for row in per_class.values()) / 3 if n else None,
            "per_class": per_class,
            "confusion_gold_rows_predicted_columns": {
                gold: {pred: counts[gold, pred] for pred in LABELS} for gold in LABELS}}


def evaluate_document_scorer(rows: list, scorer: Callable[[str], dict]) -> dict:
    """Score each usable text once and broadcast its label to anchored mentions.

    Reject mismatched offsets without moving them, even if the same name exists
    elsewhere. Invalid annotations stay in the audit and leave metric denominators.
    Duplicate spans and conflicting labels at a span are excluded together.
    """
    if not isinstance(rows, list):
        raise ValueError("Dataset must be a JSON list")
    audit = {"input_documents": len(rows), "input_annotations": 0,
             "valid_annotations": 0, "invalid_annotations": [], "invalid_documents": [],
             "documents_with_invalid_annotations": 0}
    groups = {name: [] for name in ("all", "mixed_labels", "opposing_polarities",
                                   "single_mention", "multiple_mentions")}
    group_documents = Counter()
    gold_labels = Counter()
    oracle_correct = 0
    predictions = []
    for row_index, row in enumerate(rows):
        if (not isinstance(row, dict) or not isinstance(row.get("content"), str)
                or not row["content"].strip() or not isinstance(row.get("annotations"), list)):
            audit["invalid_documents"].append({"row_index": row_index, "reason": "invalid_document"})
            continue
        text = row["content"]
        candidates, invalid = [], []
        audit["input_annotations"] += len(row["annotations"])
        for annotation_index, annotation in enumerate(row["annotations"]):
            identity = {"row_index": row_index, "annotation_index": annotation_index,
                        "text_sha256": _hash(text)}
            if not isinstance(annotation, dict):
                invalid.append({**identity, "reason": "invalid_annotation"})
                continue
            label = annotation.get("label")
            label = label.lower() if isinstance(label, str) else None
            if label not in LABELS:
                invalid.append({**identity, "reason": "invalid_label"})
                continue
            try:
                span = anchor_char_span(text, annotation.get("start"), annotation.get("end"),
                                        annotation.get("value"))
            except (ValueError, UnicodeError):
                invalid.append({**identity, "reason": "span_mismatch"})
                continue
            candidates.append({**identity, **span, "label": label})
        spans = Counter((a["start_byte"], a["end_byte"]) for a in candidates)
        valid = []
        for annotation in candidates:
            if spans[annotation["start_byte"], annotation["end_byte"]] > 1:
                invalid.append({"row_index": row_index, "annotation_index": annotation["annotation_index"],
                                "text_sha256": _hash(text), "reason": "duplicate_or_conflicting_span"})
            else:
                valid.append(annotation)
        audit["invalid_annotations"].extend(invalid)
        audit["documents_with_invalid_annotations"] += bool(invalid)
        audit["valid_annotations"] += len(valid)
        if not valid:
            audit["invalid_documents"].append({"row_index": row_index, "reason": "no_valid_annotations"})
            continue
        output = scorer(text)
        predicted = output.get("label") if isinstance(output, dict) else None
        if predicted not in LABELS:
            raise ValueError(f"Scorer returned an invalid label at row {row_index}")
        gold = Counter(a["label"] for a in valid)
        gold_labels.update(gold)
        oracle_correct += max(gold.values())
        names = ["all", "single_mention" if len(valid) == 1 else "multiple_mentions"]
        if len(gold) > 1:
            names.append("mixed_labels")
        if gold["negative"] and gold["positive"]:
            names.append("opposing_polarities")
        pairs = [(a["label"], predicted) for a in valid]
        for name in names:
            groups[name].extend(pairs)
            group_documents[name] += 1
        predictions.append({"row_index": row_index, "text_sha256": _hash(text),
                            "prediction": predicted, "valid_mentions": len(valid)})
    n = audit["valid_annotations"]
    return {"schema_version": 1,
            "protocol": "full_corpus_document_broadcast_to_anchored_gold_mentions.v1",
            "unit": "gold_mention", "label_order": list(LABELS),
            "gold_policy": "exact_half_open_character_spans; invalid_or_duplicate_spans_excluded; no_repair",
            "scope": {"entity_detection_evaluated": False, "entity_linking_evaluated": False,
                      "event_time_evaluated": False, "trading_returns_evaluated": False,
                      "paper_split_reproduced": False},
            "audit": audit, "gold_label_counts": {label: gold_labels[label] for label in LABELS},
            "subsets": {name: _metrics(pairs, group_documents[name]) for name, pairs in groups.items()},
            "document_label_oracle": {"correct_mentions": oracle_correct,
                                      "accuracy_ceiling": oracle_correct / n if n else None,
                                      "one_label_per_document": True, "uses_gold_labels": True},
            "majority_label_oracle": {"correct_mentions": max(gold_labels.values(), default=0),
                                      "accuracy": max(gold_labels.values()) / n if n else None,
                                      "uses_gold_labels": True},
            "predictions": predictions}


def _local_scorer(backend: str) -> tuple[Callable[[str], dict], dict]:
    # Deliberately bypass auto-selection, which could load/download FinBERT.
    from engine import sentiment
    version = None
    if backend == "vader":
        if not sentiment._init_vader():
            raise ValueError("VADER is unavailable; install vaderSentiment explicitly")
        version = importlib.metadata.version("vaderSentiment")
    else:
        sentiment._SCORER_TYPE, sentiment._SCORER = "none", None
    sentiment._initialized = True
    implementation = Path(sentiment.__file__).read_bytes()
    return sentiment.score_text, {"requested_backend": backend, "active_backend": sentiment.get_scorer_type(),
                                  "package_version": version, "function": "engine.sentiment.score_text",
                                  "implementation_sha256": hashlib.sha256(implementation).hexdigest()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--backend", choices=("vader", "keywords"), required=True)
    parser.add_argument("--dataset-revision")
    parser.add_argument("--include-predictions", action="store_true",
                        help="Include per-document hash/label records; default reports retain their hash")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        raw = args.input.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != args.expected_sha256:
            raise ValueError("Dataset hash does not match --expected-sha256")
        rows = json.loads(raw.decode("utf-8"))
        scorer, metadata = _local_scorer(args.backend)
        result = evaluate_document_scorer(rows, scorer)
        result.update(dataset={"input_sha256": digest, "input_bytes": len(raw),
                               "declared_revision": args.dataset_revision}, scorer=metadata)
        prediction_text = json.dumps(result["predictions"], sort_keys=True, separators=(",", ":"))
        result["prediction_log_sha256"] = _hash(prediction_text)
        if not args.include_predictions:
            del result["predictions"]
        with args.output.open("x", encoding="utf-8") as output:
            output.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        print(json.dumps({"audit": {key: value for key, value in result["audit"].items()
                                   if not isinstance(value, list)}, "all": result["subsets"]["all"]}))
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(2, f"entity sentiment diagnostic: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
