"""Prepare blank reviews and preserve explicit adjudication; no model calls."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from eval.news_shadow_score import (
    InvalidCohort, _labels, _object, _read_json, _read_manifest,
    _string, preflight_sources,
)


def _context(manifest_path, bundle_path):
    preflight = preflight_sources(manifest_path, bundle_path)
    manifest, cases, _, _, _, digest = _read_manifest(manifest_path)
    if digest != preflight["input_sha256"]["manifest"]:
        raise InvalidCohort("manifest changed during preflight")
    rows = {}
    for row in preflight["unreviewed_cases"]:
        rows[row["case_id"]] = {key: value for key, value in row.items() if key != "reviewer_id"}
    header = {"annotation_schema_version": 1, "cohort_id": manifest["cohort_id"],
              "input_sha256": preflight["input_sha256"]}
    return header, rows, cases, preflight


def prepare_reviews(manifest_path, bundle_path):
    """Return two blank copies. A claimed ID is supplied later by a reviewer."""
    header, rows, _, preflight = _context(manifest_path, bundle_path)
    return {"preflight.json": preflight, **{
        f"review_{slot}.json": {**deepcopy(header), "document_kind": "news_independent_review",
                               "reviewer_id": None, "cases": deepcopy(list(rows.values()))}
        for slot in ("a", "b")
    }}


def _bound_document(path, kind, header, expected):
    data, digest = _read_json(path)
    data = _object(data, str(path))
    if (type(data.get("annotation_schema_version")) is not int
            or data["annotation_schema_version"] != 1 or data.get("document_kind") != kind):
        raise InvalidCohort(f"{path}: invalid document kind/schema")
    if data.get("cohort_id") != header["cohort_id"] or data.get("input_sha256") != header["input_sha256"]:
        raise InvalidCohort(f"{path}: stale cohort or input hashes")
    if not isinstance(data.get("cases"), list):
        raise InvalidCohort(f"{path}: cases must be an array")
    rows = {}
    for row in data["cases"]:
        row = _object(row, f"{path}.case")
        case_id = _string(row.get("case_id"), f"{path}.case_id")
        if case_id not in expected or case_id in rows:
            raise InvalidCohort(f"{path}: unknown or duplicate case {case_id}")
        for key in ("source_id", "source_sha256", "ticker", "allowed_evidence_span_ids"):
            if row.get(key) != expected[case_id][key]:
                raise InvalidCohort(f"{path}:{case_id}: mismatched {key}")
        rows[case_id] = row
    if set(rows) != set(expected):
        raise InvalidCohort(f"{path}: incomplete cases; preserve the full cohort")
    return data, rows, digest


def _null_labels(row, where):
    if ("event_type" not in row or "concerns_company" not in row
            or row.get("event_type") is not None or row.get("concerns_company") is not None
            or row.get("evidence_span_ids") != []):
        raise InvalidCohort(f"{where}: unresolved case requires null labels and empty evidence")


def _review(path, header, expected, cases):
    data, rows, digest = _bound_document(path, "news_independent_review", header, expected)
    identity = data.get("reviewer_id")
    if identity is not None:
        identity = _string(identity, f"{path}.reviewer_id").strip()
    labels = {}
    for case_id, row in rows.items():
        where = f"{path}:{case_id}"
        status = row.get("status")
        if status not in ("unreviewed", "reviewed", "ambiguous"):
            raise InvalidCohort(f"{where}: invalid review status")
        if status == "reviewed":
            labels[case_id] = _labels(row, cases[case_id], where)
        else:
            _null_labels(row, where)
        if status != "unreviewed" and identity is None:
            raise InvalidCohort(f"{where}: completed review requires reviewer_id")
        if status == "ambiguous":
            _string(row.get("note"), f"{where}.note")
    return identity, rows, labels, digest


def _review_pair(review_a, review_b, header, expected, cases):
    a = _review(review_a, header, expected, cases)
    b = _review(review_b, header, expected, cases)
    if a[0] is not None and b[0] is not None and a[0].casefold() == b[0].casefold():
        raise InvalidCohort("reviews require distinct claimed reviewer IDs")
    return a, b


def compare_reviews(manifest_path, bundle_path, review_a, review_b):
    """Describe pending/conflicting rows without turning agreement into gold."""
    header, expected, cases, _ = _context(manifest_path, bundle_path)
    a, b = _review_pair(review_a, review_b, header, expected, cases)
    counts = {key: 0 for key in ("pending", "ambiguous", "agreement", "disagreement")}
    compared = []
    for case_id in expected:
        statuses = [review[1][case_id]["status"] for review in (a, b)]
        fields = []
        if "unreviewed" in statuses:
            state = "pending"
        elif "ambiguous" in statuses:
            state = "ambiguous"
        else:
            fields = [field for index, field in enumerate(("event_type", "concerns_company", "evidence_span_ids"))
                      if a[2][case_id][index] != b[2][case_id][index]]
            state = "disagreement" if fields else "agreement"
        counts[state] += 1
        compared.append({"case_id": case_id, "state": state, "review_statuses": statuses,
                         "disagreement_fields": fields})
    bindings = {"review_a": a[3], "review_b": b[3]}
    report = {**header, "document_kind": "news_review_comparison", "review_sha256": bindings,
              "reviewer_ids": [a[0], b[0]], "total_cases": len(expected), "counts": counts,
              "ready_for_adjudication": counts["pending"] == 0, "ready_for_scoring": False,
              "cases": compared, "limits": "Claimed IDs do not prove identity or independent human work."}
    adjudication = {**header, "document_kind": "news_adjudication", "review_sha256": bindings,
                    "adjudicator_id": None, "cases": [
                        {**row, "status": "unresolved", "reason": None} for row in expected.values()
                    ]}
    return {"comparison.json": report, "adjudication.json": adjudication}


def finalize_gold(manifest_path, bundle_path, review_a, review_b, adjudication_path):
    """Require two completed reviews and an explicit decision for every case."""
    header, expected, cases, _ = _context(manifest_path, bundle_path)
    a, b = _review_pair(review_a, review_b, header, expected, cases)
    if any(review[0] is None or any(row["status"] == "unreviewed" for row in review[1].values())
           for review in (a, b)):
        raise InvalidCohort("gold requires two complete reviews; pending cases cannot be dropped")
    data, decisions, digest = _bound_document(adjudication_path, "news_adjudication", header, expected)
    bindings = {"review_a": a[3], "review_b": b[3]}
    if data.get("review_sha256") != bindings:
        raise InvalidCohort("adjudication: stale review hashes; compare the current reviews again")
    adjudicator = _string(data.get("adjudicator_id"), "adjudication.adjudicator_id").strip()
    gold = []
    for case_id, row in decisions.items():
        if row.get("status") != "adjudicated":
            raise InvalidCohort(f"{case_id}: explicit adjudication required even for agreement")
        _labels(row, cases[case_id], f"adjudication:{case_id}")
        _string(row.get("reason"), f"adjudication:{case_id}.reason")
        gold.append({**row, "reviewer_ids": [a[0], b[0]], "adjudicator_id": adjudicator,
                     "annotation_input_sha256": header["input_sha256"], "review_sha256": bindings,
                     "adjudication_sha256": digest})
    return gold


def _write_documents(output_dir, documents):
    # Validate and serialize before reserving a new directory; never overwrite reviews.
    payloads = {name: json.dumps(data, indent=2, sort_keys=True) + "\n" for name, data in documents.items()}
    output_dir.mkdir()
    for name, payload in payloads.items():
        (output_dir / name).write_text(payload, encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "compare", "finalize"))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-bundle", required=True, type=Path)
    parser.add_argument("--review-a", type=Path)
    parser.add_argument("--review-b", type=Path)
    parser.add_argument("--adjudication", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        if args.output_dir is None or any((args.review_a, args.review_b, args.adjudication, args.output)):
            parser.error("prepare requires only --output-dir plus manifest/source-bundle")
    else:
        if args.review_a is None or args.review_b is None:
            parser.error("compare/finalize require --review-a and --review-b")
        if args.command == "compare" and (args.output_dir is None or args.adjudication or args.output):
            parser.error("compare requires --output-dir without --adjudication/--output")
        if args.command == "finalize" and (args.adjudication is None or args.output is None or args.output_dir):
            parser.error("finalize requires --adjudication and --output without --output-dir")
    try:
        if args.command == "prepare":
            _write_documents(args.output_dir, prepare_reviews(args.manifest, args.source_bundle))
        elif args.command == "compare":
            _write_documents(args.output_dir, compare_reviews(args.manifest, args.source_bundle, args.review_a, args.review_b))
        else:
            rows = finalize_gold(args.manifest, args.source_bundle, args.review_a, args.review_b, args.adjudication)
            payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(payload)
    except (InvalidCohort, OSError) as exc:
        parser.exit(2, f"invalid annotation workflow: {exc}\n")


if __name__ == "__main__":
    main()
