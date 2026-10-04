"""Offline, provider-independent scoring of frozen company-news classifications.

No network access, model invocation, or broker access. Usage and billed costs are
supplied by the caller; the scorer never estimates missing usage from text length.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path


EVENTS = ("earnings", "guidance", "regulatory", "other")
FAILURES = ("timeout", "provider_error", "schema_error", "missing_source")
DEFAULT_RELEVANCE_THRESHOLDS = (0.0, 0.5, 0.8, 0.95, 1.0)
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_LANGUAGE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*\Z")


class InvalidCohort(ValueError):
    """Input cannot support a reproducible complete-cohort comparison."""


def _object(value, where):
    if not isinstance(value, dict):
        raise InvalidCohort(f"{where}: expected JSON object")
    return value


def _string(value, where):
    if not isinstance(value, str) or not value.strip():
        raise InvalidCohort(f"{where}: expected nonempty string")
    return value


def _number(value, where, *, minimum=0.0):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < minimum:
        raise InvalidCohort(f"{where}: expected finite number >= {minimum}")
    return float(value)


def _integer(value, where):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidCohort(f"{where}: expected nonnegative integer")
    return value


def _confidence_thresholds(value):
    if not isinstance(value, (list, tuple)) or not value:
        raise InvalidCohort("relevance_confidence_thresholds: expected nonempty array")
    thresholds = [_number(v, "relevance_confidence_thresholds") for v in value]
    if any(v > 1 for v in thresholds) or any(a >= b for a, b in zip(thresholds, thresholds[1:])):
        raise InvalidCohort("relevance_confidence_thresholds: must increase strictly within [0, 1]")
    return thresholds


def _utc(value, where):
    _string(value, where)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidCohort(f"{where}: invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise InvalidCohort(f"{where}: timestamp must have UTC offset")
    return parsed


def _ids(value, where):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise InvalidCohort(f"{where}: expected array of nonempty strings")
    if len(value) != len(set(value)):
        raise InvalidCohort(f"{where}: duplicate IDs")
    return set(value)


def _reject_duplicate_fields(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise InvalidCohort(f"duplicate JSON field: {key}")
        data[key] = value
    return data


def _reject_json_constant(value):
    raise InvalidCohort(f"non-JSON numeric constant: {value}")


def _parse_json(payload):
    return json.loads(payload, object_pairs_hook=_reject_duplicate_fields, parse_constant=_reject_json_constant)


def _read_json(path):
    try:
        raw = Path(path).read_bytes()
        return _parse_json(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidCohort(f"{path}: invalid JSON or unreadable file: {exc}") from exc


def _read_jsonl(path):
    try:
        raw = Path(path).read_bytes()
        lines = raw.decode("utf-8").splitlines()
        rows = []
        for line_number, line in enumerate(lines, 1):
            if not line.strip():
                raise InvalidCohort(f"{path}:{line_number}: empty line")
            try:
                rows.append(_object(_parse_json(line), f"{path}:{line_number}"))
            except json.JSONDecodeError as exc:
                raise InvalidCohort(f"{path}:{line_number}: invalid JSON") from exc
        return rows, hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeError) as exc:
        raise InvalidCohort(f"{path}: unreadable JSONL: {exc}") from exc


def _read_manifest(path):
    payload, digest = _read_json(path)
    data = _object(payload, "manifest")
    _string(data.get("cohort_id"), "manifest.cohort_id")
    if data.get("sample_kind") not in ("synthetic", "stratified", "representative"):
        raise InvalidCohort("manifest.sample_kind: expected synthetic, stratified, or representative")
    _string(data.get("primary_class_rule"), "manifest.primary_class_rule")
    if not isinstance(data.get("require_source_bundle", False), bool):
        raise InvalidCohort("manifest.require_source_bundle: expected boolean")
    frozen = _utc(data.get("frozen_at_utc"), "manifest.frozen_at_utc")
    _confidence_thresholds(data.get("relevance_confidence_thresholds", DEFAULT_RELEVANCE_THRESHOLDS))
    rows = data.get("cases")
    if not isinstance(rows, list) or not rows:
        raise InvalidCohort("manifest.cases: expected nonempty array")
    cases = {}
    sources = {}
    groups = {}
    split_counts = {"train": 0, "test": 0}
    for row in rows:
        row = _object(row, "manifest.case")
        case_id = _string(row.get("case_id"), "manifest.case_id")
        if case_id in cases:
            raise InvalidCohort(f"duplicate case_id: {case_id}")
        source = _string(row.get("source_id"), f"{case_id}.source_id")
        source_sha = row.get("source_sha256")
        if not isinstance(source_sha, str) or not _SHA256.fullmatch(source_sha):
            raise InvalidCohort(f"{case_id}.source_sha256: expected lowercase SHA-256")
        url = _string(row.get("source_url"), f"{case_id}.source_url")
        rights = _string(row.get("source_rights"), f"{case_id}.source_rights")
        if not url.startswith(("https://", "http://")):
            raise InvalidCohort(f"{case_id}.source_url: expected HTTP(S) URL")
        if source in sources and sources[source] != (source_sha, url, rights):
            raise InvalidCohort(f"source_id {source} has conflicting hash/URL/rights")
        sources[source] = (source_sha, url, rights)
        group = _string(row.get("event_group_id"), f"{case_id}.event_group_id")
        split = row.get("split")
        if not isinstance(split, str) or split not in split_counts:
            raise InvalidCohort(f"{case_id}.split: expected train or test")
        split_counts[split] += 1
        when = _utc(row.get("published_at_utc"), f"{case_id}.published_at_utc")
        available = _utc(row.get("available_at_utc"), f"{case_id}.available_at_utc")
        if available < when or available > frozen:
            raise InvalidCohort(f"{case_id}: future article after freeze")
        allowed = _ids(row.get("evidence_span_ids"), f"{case_id}.evidence_span_ids")
        _string(row.get("ticker"), f"{case_id}.ticker")
        language = row.get("language", "und")
        if not isinstance(language, str) or not _LANGUAGE.fullmatch(language):
            raise InvalidCohort(f"{case_id}.language: expected lowercase language tag, or und if unknown")
        cases[case_id] = {"split": split, "group": group, "source": source, "hash": source_sha,
                          "allowed": allowed, "language": language}
        groups.setdefault(group, set()).add(split)
    if not split_counts["test"]:
        raise InvalidCohort("manifest: no test cases")
    for group, splits in groups.items():
        if len(splits) != 1:
            raise InvalidCohort(f"event_group_id {group} crosses train/test split")
    by_sha = {}
    for case in cases.values():
        by_sha.setdefault(case["hash"], set()).add(case["split"])
    if any(len(splits) != 1 for splits in by_sha.values()):
        raise InvalidCohort("source hash crosses train/test split")
    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise InvalidCohort("manifest.models: expected nonempty array")
    pricing = {}
    for entry in models:
        entry = _object(entry, "manifest.model")
        name = _string(entry.get("model_id"), "manifest.model_id")
        _string(entry.get("revision"), f"{name}.revision")
        if name in pricing:
            raise InvalidCohort(f"duplicate model_id: {name}")
        if not isinstance(entry.get("evidence_capable"), bool):
            raise InvalidCohort(f"{name}.evidence_capable: expected boolean")
        rates = entry.get("pricing_usd_per_million_tokens")
        if rates is None:
            rate = None
        else:
            rates = _object(rates, f"{name}.pricing")
            rate = {key: _number(rates.get(key), f"{name}.pricing.{key}") for key in ("input", "output")}
        pricing[name] = {"rate": rate, "evidence_capable": entry["evidence_capable"]}
    return data, cases, pricing, split_counts, len({case["group"] for case in cases.values() if case["split"] == "test"}), digest


def _snapshot_bytes(root: Path, relative_path: str) -> bytes:
    """Read only a regular UTF-8 snapshot within the declared bundle directory."""
    relative_path = _string(relative_path, "source.snapshot_path")
    if ("\\" in relative_path or "\x00" in relative_path or ":" in relative_path
            or any(part in ("", ".", "..") for part in relative_path.split("/"))):
        raise InvalidCohort("source.snapshot_path: expected normalized relative path")
    try:
        path = (root / relative_path).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise InvalidCohort("source.snapshot_path: must be a regular file within the bundle directory")
        with path.open("rb") as handle:
            raw = handle.read(MAX_SNAPSHOT_BYTES + 1)
        if not raw or len(raw) > MAX_SNAPSHOT_BYTES:
            raise InvalidCohort("source snapshot: expected 1 byte to 16 MiB")
        raw.decode("utf-8")
        return raw
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        if isinstance(exc, InvalidCohort):
            raise
        raise InvalidCohort(f"source.snapshot_path: unreadable UTF-8 snapshot: {exc}") from exc


def _verify_source_bundle(manifest: dict, bundle_path: str | Path) -> dict:
    bundle, digest = _read_json(bundle_path)
    bundle = _object(bundle, "source bundle")
    if type(bundle.get("bundle_schema_version")) is not int or bundle["bundle_schema_version"] != 1:
        raise InvalidCohort("source bundle: expected bundle_schema_version 1")
    if bundle.get("cohort_id") != manifest["cohort_id"]:
        raise InvalidCohort("source bundle: cohort_id does not match manifest")
    entries = bundle.get("sources")
    if not isinstance(entries, list):
        raise InvalidCohort("source bundle.sources: expected array")
    root = Path(bundle_path).resolve().parent
    expected = {}
    for case in manifest["cases"]:
        expected.setdefault(case["source_id"], []).append(case)
    frozen = _utc(manifest["frozen_at_utc"], "manifest.frozen_at_utc")
    verified = {}
    for entry in entries:
        entry = _object(entry, "source bundle.source")
        source_id = _string(entry.get("source_id"), "source bundle.source_id")
        if source_id not in expected or source_id in verified:
            raise InvalidCohort(f"source bundle: unknown or duplicate source_id {source_id}")
        source_cases = expected[source_id]
        published = _utc(entry.get("published_at_utc"), f"{source_id}.published_at_utc")
        available = _utc(entry.get("available_at_utc"), f"{source_id}.available_at_utc")
        captured = _utc(entry.get("captured_at_utc"), f"{source_id}.captured_at_utc")
        if not published <= available <= captured <= frozen:
            raise InvalidCohort(f"{source_id}: require publication <= availability <= capture <= freeze")
        for case in source_cases:
            for key in ("source_sha256", "source_url", "source_rights"):
                if entry.get(key) != case[key]:
                    raise InvalidCohort(f"{source_id}: {key} does not match manifest")
            if (published != _utc(case["published_at_utc"], source_id)
                    or available != _utc(case["available_at_utc"], source_id)):
                raise InvalidCohort(f"{source_id}: source timestamps do not match every manifest case")
        raw = _snapshot_bytes(root, entry.get("snapshot_path"))
        if hashlib.sha256(raw).hexdigest() != source_cases[0]["source_sha256"]:
            raise InvalidCohort(f"{source_id}: snapshot bytes do not match source_sha256")
        spans = entry.get("evidence_spans")
        if not isinstance(spans, list):
            raise InvalidCohort(f"{source_id}.evidence_spans: expected array")
        allowed = set().union(*(set(case["evidence_span_ids"]) for case in source_cases))
        checked = set()
        for span in spans:
            span = _object(span, f"{source_id}.evidence_span")
            span_id = _string(span.get("span_id"), f"{source_id}.span_id")
            if span_id not in allowed or span_id in checked:
                raise InvalidCohort(f"{source_id}: unknown or duplicate evidence span {span_id}")
            start = _integer(span.get("start_byte"), f"{span_id}.start_byte")
            end = _integer(span.get("end_byte"), f"{span_id}.end_byte")
            if not 0 <= start < end <= len(raw):
                raise InvalidCohort(f"{source_id}:{span_id}: invalid byte range")
            excerpt = raw[start:end]
            try:
                if not excerpt.decode("utf-8").strip():
                    raise InvalidCohort(f"{source_id}:{span_id}: empty evidence text")
            except UnicodeError as exc:
                raise InvalidCohort(f"{source_id}:{span_id}: byte range splits UTF-8 text") from exc
            if hashlib.sha256(excerpt).hexdigest() != span.get("span_sha256"):
                raise InvalidCohort(f"{source_id}:{span_id}: evidence bytes do not match span_sha256")
            checked.add(span_id)
        if checked != allowed:
            raise InvalidCohort(f"{source_id}: missing evidence spans {sorted(allowed - checked)}")
        verified[source_id] = {
            "source_id": source_id, "source_sha256": source_cases[0]["source_sha256"],
            "snapshot_path": entry["snapshot_path"], "snapshot_bytes": len(raw),
            "captured_at_utc": entry["captured_at_utc"], "verified_spans": len(checked),
        }
    if set(verified) != set(expected):
        raise InvalidCohort(f"source bundle: missing sources {sorted(set(expected) - set(verified))}")
    return {
        "mode": "snapshot_bytes_verified", "bundle_sha256": digest,
        "verified_sources": len(verified),
        "verified_spans": sum(source["verified_spans"] for source in verified.values()),
        "sources": [verified[key] for key in sorted(verified)],
        "limits": "Byte and metadata consistency only; not source authenticity, timestamp truth, use rights, reviewer independence or proof of model input.",
    }


def preflight_sources(manifest_path: str | Path, source_bundle_path: str | Path) -> dict:
    """Verify archived inputs before labels or model outputs exist; never invent gold."""
    manifest, _, _, counts, _, manifest_hash = _read_manifest(manifest_path)
    verification = _verify_source_bundle(manifest, source_bundle_path)
    return {
        "report_kind": "news_source_preflight", "report_schema_version": 1,
        "cohort_id": manifest["cohort_id"], "sample_kind": manifest["sample_kind"],
        "manifest_cases": len(manifest["cases"]), "test_cases": counts["test"],
        "input_sha256": {"manifest": manifest_hash, "source_bundle": verification["bundle_sha256"]},
        "source_verification": verification, "gold_status": "not_checked", "predictions_status": "not_checked",
        "unreviewed_cases": [
            {"case_id": case["case_id"], "source_id": case["source_id"],
             "source_sha256": case["source_sha256"], "ticker": case["ticker"],
             "allowed_evidence_span_ids": case["evidence_span_ids"],
             "status": "unreviewed", "reviewer_id": None, "event_type": None,
             "concerns_company": None, "evidence_span_ids": []}
            for case in manifest["cases"] if case["split"] == "test"
        ],
    }


def _labels(row, case, where, *, prediction=False, evidence_capable=True):
    abstain = row.get("abstain", False) if prediction else False
    if not isinstance(abstain, bool):
        raise InvalidCohort(f"{where}.abstain: expected boolean")
    if evidence_capable and "evidence_span_ids" not in row:
        raise InvalidCohort(f"{where}: evidence-capable arm must supply evidence_span_ids")
    spans = _ids(row.get("evidence_span_ids", []), f"{where}.evidence_span_ids")
    if not evidence_capable and spans:
        raise InvalidCohort(f"{where}: classification-only arm declared evidence_capable=false")
    if not spans <= case["allowed"]:
        raise InvalidCohort(f"{where}: evidence span ID not in frozen source map")
    event, relevance = row.get("event_type"), row.get("concerns_company")
    if abstain:
        if event is not None or relevance is not None or spans:
            raise InvalidCohort(f"{where}: abstention must use null labels and no evidence")
    elif event not in EVENTS or not isinstance(relevance, bool):
        raise InvalidCohort(f"{where}: expected event_type and boolean concerns_company")
    return event, relevance, spans, abstain


def _read_gold(path, cases):
    gold = {}
    test_ids = {key for key, case in cases.items() if case["split"] == "test"}
    rows, digest = _read_jsonl(path)
    for row in rows:
        case_id = _string(row.get("case_id"), "gold.case_id")
        if case_id not in test_ids or case_id in gold:
            raise InvalidCohort(f"gold: unknown, non-test, or duplicate case_id {case_id}")
        if row.get("source_id") != cases[case_id]["source"] or row.get("source_sha256") != cases[case_id]["hash"]:
            raise InvalidCohort(f"gold {case_id}: source ID/hash does not match manifest")
        if row.get("status") != "adjudicated":
            raise InvalidCohort(f"gold {case_id}: unresolved/ambiguous/missing-source case; resolve before scoring, keep case in cohort")
        reviewers = _ids(row.get("reviewer_ids"), f"gold {case_id}.reviewer_ids")
        if len(reviewers) < 2:
            raise InvalidCohort(f"gold {case_id}: expected at least two distinct independent reviewer IDs")
        gold[case_id] = _labels(row, cases[case_id], f"gold {case_id}")
    if set(gold) != test_ids:
        raise InvalidCohort(f"gold incomplete: missing {sorted(test_ids - set(gold))}")
    return gold, digest


def _read_predictions(path, cases, pricing):
    test_ids = {key for key, case in cases.items() if case["split"] == "test"}
    predictions = {model: {} for model in pricing}
    entries, digest = _read_jsonl(path)
    for row in entries:
        model = _string(row.get("model_id"), "prediction.model_id")
        case_id = _string(row.get("case_id"), "prediction.case_id")
        if model not in predictions or case_id not in test_ids or case_id in predictions[model]:
            raise InvalidCohort(f"prediction: unknown model/case, non-test, or duplicate {model}:{case_id}")
        case = cases[case_id]
        if row.get("source_id") != case["source"] or row.get("source_sha256") != case["hash"]:
            raise InvalidCohort(f"prediction {model}:{case_id}: source ID/hash does not match manifest")
        label = _labels(row, case, f"prediction {model}:{case_id}", prediction=True,
                        evidence_capable=pricing[model]["evidence_capable"])
        failure_kind = row.get("failure_kind")
        if failure_kind is not None and (failure_kind not in FAILURES or not label[3]):
            raise InvalidCohort(f"prediction {model}:{case_id}: invalid failure_kind or failure without abstention")
        probability = row.get("concerns_company_probability")
        if probability is not None:
            if failure_kind is not None:
                raise InvalidCohort(f"prediction {model}:{case_id}: failed call cannot supply a scored probability")
            probability = _number(probability, f"prediction {model}:{case_id}.probability")
            if probability > 1:
                raise InvalidCohort(f"prediction {model}:{case_id}: probability exceeds 1")
        usage = _object(row.get("usage"), f"prediction {model}:{case_id}.usage")
        tokens = {name: _integer(usage.get(name), f"prediction {model}:{case_id}.{name}") for name in ("input_tokens", "output_tokens")}
        billed = usage.get("billed_usd")
        if billed is not None:
            billed = _number(billed, f"prediction {model}:{case_id}.billed_usd")
        predictions[model][case_id] = {
            "label": label, "probability": probability, "latency_ms": _number(row.get("latency_ms"), f"prediction {model}:{case_id}.latency_ms"),
            "tokens": tokens, "billed_usd": billed, "failure_kind": failure_kind,
        }
    for model, rows in predictions.items():
        if set(rows) != test_ids:
            raise InvalidCohort(f"prediction {model} incomplete: missing {sorted(test_ids - set(rows))}")
    return predictions, digest


def _class_metrics(gold, predictions, labels, index):
    out = {}
    for target in labels:
        tp = sum(gold[k][index] == target and predictions[k]["label"][index] == target for k in gold)
        fp = sum(gold[k][index] != target and predictions[k]["label"][index] == target for k in gold)
        fn = sum(gold[k][index] == target and predictions[k]["label"][index] != target for k in gold)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        out[str(target).lower()] = {"support": tp + fn, "precision": precision, "recall": recall,
                                  "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}
    return out


def _percentile(values, percentile):
    """Nearest-rank percentile, after sorting the complete cohort."""
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * percentile) - 1]


def _relevance_metrics(gold, rows):
    n = len(gold)
    classes = _class_metrics(gold, rows, (False, True), 1)
    errors = [(row["probability"] - float(gold[key][1])) ** 2
              for key, row in rows.items() if row["probability"] is not None]
    return {
        "per_class": classes,
        "macro_f1": statistics.mean(v["f1"] for v in classes.values()),
        "accuracy_full_cohort": sum(not row["label"][3] and row["label"][1] == gold[key][1]
                                    for key, row in rows.items()) / n,
        "brier_full_cohort": sum(errors) / n if len(errors) == n else None,
        "brier_probability_coverage": len(errors),
        "brier_withheld_reason": None if len(errors) == n else
        "requires an explicit probability on every test case, including abstentions",
    }


def _selective_relevance(gold, rows, thresholds):
    """Describe a frozen binary-relevance gate; never select a winning threshold."""
    n = len(gold)
    eligible = {
        key: row["probability"] if row["label"][1] else 1.0 - row["probability"]
        for key, row in rows.items() if not row["label"][3] and row["probability"] is not None
    }
    curve = []
    for threshold in thresholds:
        accepted = [key for key, confidence in eligible.items() if confidence >= threshold]
        mistakes = sum(rows[key]["label"][1] != gold[key][1] for key in accepted)
        joint_correct = sum(rows[key]["label"][:2] == gold[key][:2] for key in accepted)
        curve.append({
            "confidence_threshold": threshold, "accepted": len(accepted),
            "withheld": n - len(accepted), "coverage_full_cohort": len(accepted) / n,
            "relevance_errors": mistakes,
            "relevance_error_rate_accepted": mistakes / len(accepted) if accepted else None,
            "joint_event_and_relevance_accuracy_accepted": joint_correct / len(accepted) if accepted else None,
        })
    return {
        "scope": "binary company relevance only; not event confidence, evidence truth or trading",
        "test_cases": n, "eligible_answered_with_probability": len(eligible),
        "excluded_abstentions": sum(row["label"][3] for row in rows.values()),
        "excluded_answered_without_probability": sum(not row["label"][3] and row["probability"] is None
                                                    for row in rows.values()),
        "label_probability_disagreements": sum(confidence < 0.5 for confidence in eligible.values()),
        "curve": curve,
    }


def _language_slices(gold, rows, cases, thresholds):
    results = {}
    for language in sorted({cases[key]["language"] for key in gold}):
        subset_gold = {key: value for key, value in gold.items() if cases[key]["language"] == language}
        subset_rows = {key: rows[key] for key in subset_gold}
        events = _class_metrics(subset_gold, subset_rows, EVENTS, 0)
        results[language] = {
            "test_cases": len(subset_gold),
            "test_event_groups": len({cases[key]["group"] for key in subset_gold}),
            "abstentions": sum(row["label"][3] for row in subset_rows.values()),
            "event_type": {"per_class": events, "macro_f1": statistics.mean(v["f1"] for v in events.values())},
            "company_relevance": _relevance_metrics(subset_gold, subset_rows),
            "selective_company_relevance": _selective_relevance(subset_gold, subset_rows, thresholds),
        }
    return results


def score(manifest_path, gold_path, predictions_path, *, source_bundle_path=None):
    """Validate every declared test example and return a deterministic JSON-ready report."""
    manifest, cases, pricing, counts, test_groups, manifest_hash = _read_manifest(manifest_path)
    if source_bundle_path is None and manifest.get("require_source_bundle", False):
        raise InvalidCohort("manifest requires a source bundle; supply --source-bundle")
    verification = (_verify_source_bundle(manifest, source_bundle_path) if source_bundle_path is not None
                    else {"mode": "metadata_only", "bundle_sha256": None,
                          "verified_sources": 0, "verified_spans": 0,
                          "limits": "No snapshot bytes or evidence ranges were checked."})
    gold, gold_hash = _read_gold(gold_path, cases)
    predictions, prediction_hash = _read_predictions(predictions_path, cases, pricing)
    thresholds = _confidence_thresholds(manifest.get("relevance_confidence_thresholds", DEFAULT_RELEVANCE_THRESHOLDS))
    results = {}
    for model, rows in sorted(predictions.items()):
        events = _class_metrics(gold, rows, EVENTS, 0)
        answered = sum(not v["label"][3] for v in rows.values())
        eligible = [key for key in gold if gold[key][2]]
        exact = sum(not rows[key]["label"][3] and rows[key]["label"][2] == gold[key][2] for key in eligible)
        billed = [row["billed_usd"] for row in rows.values() if row["billed_usd"] is not None]
        rate = pricing[model]["rate"]
        estimate = (sum(row["tokens"]["input_tokens"] * rate["input"] + row["tokens"]["output_tokens"] * rate["output"] for row in rows.values()) / 1_000_000) if rate is not None else None
        latency = [row["latency_ms"] for row in rows.values()]
        n = len(gold)
        results[model] = {
            "test_cases": n, "answered": answered, "abstentions": n - answered,
            "abstentions_by_kind": {"policy_or_unclassified": sum(v["label"][3] and v["failure_kind"] is None for v in rows.values()),
                                    **{kind: sum(v["failure_kind"] == kind for v in rows.values()) for kind in FAILURES}},
            "event_type": {"per_class": events, "macro_f1": statistics.mean(v["f1"] for v in events.values())},
            "company_relevance": _relevance_metrics(gold, rows),
            "selective_company_relevance": _selective_relevance(gold, rows, thresholds),
            "language_slices": _language_slices(gold, rows, cases, thresholds),
            "evidence_exact": {"capable": pricing[model]["evidence_capable"], "eligible_nonempty_gold": len(eligible),
                               "cases": exact if pricing[model]["evidence_capable"] else None,
                               "rate_eligible": exact / len(eligible) if eligible and pricing[model]["evidence_capable"] else None,
                               "rate_full_cohort": exact / n if pricing[model]["evidence_capable"] else None},
            "latency_ms": {"p50": _percentile(latency, .5), "p95": _percentile(latency, .95), "definition": "nearest_rank"},
            "usage": {"input_tokens": sum(v["tokens"]["input_tokens"] for v in rows.values()),
                      "output_tokens": sum(v["tokens"]["output_tokens"] for v in rows.values()),
                      "billed_cost_coverage": len(billed), "observed_billed_usd": sum(billed) if len(billed) == n else None,
                      "observed_billed_usd_per_1000": sum(billed) * 1000 / n if len(billed) == n else None,
                      "rate_estimated_usd": estimate, "rate_estimated_usd_per_1000": estimate * 1000 / n if estimate is not None else None,
                      "pricing_usd_per_million_tokens": rate},
        }
    file_hashes = {"manifest": manifest_hash, "gold": gold_hash, "predictions": prediction_hash}
    if source_bundle_path is not None:
        file_hashes["source_bundle"] = verification["bundle_sha256"]
    return {"report_schema_version": 3, "cohort_id": manifest["cohort_id"], "frozen_at_utc": manifest["frozen_at_utc"],
            "sample_kind": manifest.get("sample_kind"),
            "input_sha256": file_hashes,
            "source_verification": verification,
            "manifest_cases": len(cases), "train_cases_checked_for_leakage": counts["train"],
            "relevance_confidence_thresholds": thresholds,
            "thresholds_source": "manifest" if "relevance_confidence_thresholds" in manifest else "code_default",
            "test_cases_scored": counts["test"], "test_event_groups": test_groups, "models": results,
            "notes": ["Synthetic inputs are not empirical performance.",
                      "Only declared test cases are scored; train cases are checked for event/source leakage.",
                      "Abstentions count as misses in full-cohort F1; explicit probabilities on abstentions can contribute to Brier if all test cases have them.",
                      "Evidence is N/A for classification-only arms; exact match uses nonempty gold citations only, not independent proof that evidence is true.",
                      "Billed cost requires all per-case billed amounts; token-rate estimates omit unreported fees and are separate.",
                      "Selective coverage uses the full cohort; abstentions and missing probabilities remain withheld. Empty accepted sets have null error rates.",
                      "Thresholds and language tags must be frozen before model outputs. This scorer cannot attest preregistration or select a deployment threshold.",
                      "Language slices are descriptive and may share event groups; differences are not causal language effects or independent significance tests."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--source-bundle", type=Path, help="Verify local snapshot bytes and evidence byte ranges")
    parser.add_argument("--output", type=Path, help="Write report only after complete validation")
    args = parser.parse_args(argv)
    try:
        report = score(args.manifest, args.gold, args.predictions, source_bundle_path=args.source_bundle)
    except InvalidCohort as exc:
        parser.exit(2, f"invalid cohort: {exc}\n")
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
