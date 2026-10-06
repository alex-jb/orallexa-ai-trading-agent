#!/usr/bin/env python3
"""Pinned, offline source probes; synthetic examples, not a model benchmark.

Reads Graphiti source snapshots and Orallexa Git blobs, verifies every input
before selecting AST definitions, and exclusively creates a JSON receipt.
No upstream module import, optimizer, database, provider, or market call.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

ORALLEXA_COMMIT = "9bdb4d955d006a04159feb2d8b8b207402ddc33d"
GRAPHITI_COMMIT = "689de295c209631405c00e19e0af4f9735142f13"
SOURCES = {
    "graphiti": {
        "graphiti_core/search/search_filters.py": "7d45f4b66cc55d0cea90504817bff9f025d48045",
        "graphiti_core/edges.py": "28c170355e02a569b60c5e070f019572889ace82",
        "graphiti_core/utils/maintenance/edge_operations.py": "80a1ef384088c09d1bb33700ccdb0fbe7a6998b8",
        "graphiti_core/search/search.py": "51c65d217000033bde1e772cfb2b1ddd97e8d0c9",
        "graphiti_core/graphiti.py": "be7375e6fef97c9b96d7c981d2edb7957a24b2ef",
        "README.md": "48ef8e013e97cfb498d6ca9c494e4d65ab42c06a",
        "LICENSE": "5feb0d9d299a1107adfa8331306b13cc0eff2d78",
    },
    "orallexa": {
        "engine/platt_calibration.py": "c10a93c3bc8d45eb4e1e05f6a6a2c925e71428c0",
        "eval/decision_eval.py": "03e7e4dc78526fc86a3659cc52e7783fa938cdfe",
        "models/confidence.py": "c056c0db8f9387ef82688c76221235dbd542926c",
        "tests/test_platt_calibration.py": "254c283a05aa663f2912ec81e5d99d2685c11be4",
        "markets/auto/brier_audit.py": "1a1381bc4037bf95031f41ee2003773a7e9cc1c3",
        "markets/auto/polymarket_daily.py": "19e8baac03ccaa0fb25c3915d6b699287fc71034",
    },
}


def verify_sources(graphiti_root: Path, orallexa_root: Path):
    texts, identities = {}, []
    for project, paths in SOURCES.items():
        for path, expected in paths.items():
            if project == "graphiti":
                raw = (graphiti_root / path).read_bytes()
                commit = GRAPHITI_COMMIT
            else:
                raw = subprocess.check_output([
                    "git", "-C", str(orallexa_root), "show", f"{ORALLEXA_COMMIT}:{path}",
                ])
                commit = ORALLEXA_COMMIT
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            if blob != expected:
                raise ValueError(f"source byte mismatch: {project}/{path}")
            texts[(project, path)] = raw.decode("utf-8")
            identities.append({"project": project, "commit": commit, "path": path,
                               "bytes": len(raw), "git_blob_sha1": blob,
                               "sha256": hashlib.sha256(raw).hexdigest()})
    return texts, identities


def selected_definitions(text: str, names: set[str], namespace: dict):
    tree = ast.parse(text)
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
             and n.name in names]
    if {n.name for n in nodes} != names:
        raise ValueError("selected source definitions missing")
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    exec(compile(module, "<verified-source-definitions>", "exec"), namespace)


def encode(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(type(value).__name__)


def run(texts, identities):
    cases = []
    module = ModuleType("_memory_calibration_source_probe")
    sys.modules[module.__name__] = module
    oral = module.__dict__
    oral.update(math=math, dataclass=dataclass, MAX_CONFIDENCE=82.0)
    selected_definitions(texts[("orallexa", "engine/platt_calibration.py")],
                         {"PlattCalibrator", "_platt_transform", "identity", "_brier"}, oral)
    selected_definitions(texts[("orallexa", "eval/decision_eval.py")],
                         {"confidence_calibration"}, oral)
    selected_definitions(texts[("orallexa", "models/confidence.py")], {"scale_confidence"}, oral)
    ident = oral["identity"]()
    for p in [0, .1, .2, .25, .4, .5, .6, .75, .8, .9, 1]:
        q = ident.calibrate(p)
        cases.append({"id": f"cold_start_{p:g}", "input_probability": p,
                      "actual_probability": q, "absolute_change": abs(q-p)})
    assert ident.calibrate(.25) < .000001 and ident.calibrate(.75) > .999999

    # Constructed frequency-matched groups, not actual financial forecasts.
    labels = [1]*25 + [0]*75 + [1]*75 + [0]*25
    raw = [.25]*100 + [.75]*100
    mapped = [ident.calibrate(p) for p in raw]
    raw_brier, mapped_brier = oral["_brier"](raw, labels), oral["_brier"](mapped, labels)
    assert raw_brier == .1875 and mapped_brier > raw_brier
    cases.append({"id": "cold_start_synthetic_brier", "synthetic": True, "n": len(labels),
                  "groups": [{"p": .25, "n": 100, "positive": 25},
                             {"p": .75, "n": 100, "positive": 75}],
                  "raw_brier": raw_brier, "mapped_brier": mapped_brier})

    evaluated = []
    groups = [(20, 5), (40, 6), (60, 7), (75, 8)]
    for confidence, positives in groups:
        evaluated.extend({"confidence": confidence, "correct": i < positives,
                          "forward_return": .01 if i < positives else -.01}
                         for i in range(10))
    bucket_result = oral["confidence_calibration"](evaluated_decisions=evaluated)
    accuracies = [row["accuracy"] for row in bucket_result["buckets"]]
    assert accuracies == [.5, .6, .7, .8]
    # This probability interpretation is hypothetical; the project score's
    # scaling/capping does not establish this semantics.
    ece_if_probability = sum(abs(c/100 - positive/10) for c, positive in groups)/4
    cases.append({"id": "monotonic_accuracy_is_not_probability_calibration", "synthetic": True,
                  "input_groups": [{"confidence": c, "n": 10, "correct": p} for c, p in groups],
                  "source_function_result": bucket_result,
                  "ece_if_score_were_probability": ece_if_probability,
                  "interpretation": "conditional diagnostic, not measured project ECE"})
    capped = oral["scale_confidence"](100)
    endpoint = oral["confidence_calibration"](evaluated_decisions=[
        {"confidence": capped, "correct": True, "forward_return": .01},
    ])
    counted = sum(row["count"] for row in endpoint["buckets"])
    assert capped == 82 and endpoint["total_evaluated"] == 1 and counted == 0
    cases.append({"id": "capped_confidence_82_missing_from_buckets", "synthetic": True,
                  "raw_confidence": 100, "source_scaled_confidence": capped,
                  "source_function_result": endpoint, "sum_bucket_counts": counted})

    class Provider(Enum):
        NEO4J = "neo4j"
        KUZU = "kuzu"

    graph = {"Enum": Enum, "GraphProvider": Provider}
    selected_definitions(texts[("graphiti", "graphiti_core/search/search_filters.py")],
                         {"ComparisonOperator", "date_filter_query_constructor",
                          "edge_search_filter_query_constructor"}, graph)
    op = graph["ComparisonOperator"]
    def date(day, operator):
        return SimpleNamespace(date=datetime(2026, 10, day, tzinfo=timezone.utc),
                               comparison_operator=operator)
    def filters(**kwargs):
        values = dict.fromkeys(["node_labels", "edge_types", "valid_at", "invalid_at",
                                "created_at", "expired_at", "edge_uuids", "property_filters"])
        values.update(kwargs)
        return SimpleNamespace(**values)
    constructor = graph["edge_search_filter_query_constructor"]
    for name, f in [
        ("default_no_time_filter", filters()),
        ("event_time_only", filters(valid_at=[[date(2, op.less_than_equal)]])),
        ("explicit_event_and_ingestion_time", filters(valid_at=[[date(2, op.less_than_equal)]],
                                                     created_at=[[date(3, op.less_than_equal)]])),
        ("expiry_null_or_later", filters(expired_at=[
            [SimpleNamespace(date=None, comparison_operator=op.is_null)],
            [date(3, op.greater_than)],
        ])),
    ]:
        query, params = constructor(f, Provider.NEO4J)
        if name == "default_no_time_filter":
            assert query == [] and params == {}
        if name == "event_time_only":
            assert not any("created_at" in q for q in query)
        cases.append({"id": name, "actual_query_fragments": query, "actual_parameters": params,
                      "scope": "source query builder with attribute stubs; no database execution"})
    for field in ["valid_at", "invalid_at", "created_at", "expired_at"]:
        ranges = [[date(1, op.greater_than_equal), date(2, op.less_than)],
                  [date(3, op.greater_than_equal), date(4, op.less_than)]]
        query, params = constructor(filters(**{field: ranges}), Provider.NEO4J)
        assert len(params) == 2 and params[field+"_0"] == ranges[1][0].date
        assert params[field+"_1"] == ranges[1][1].date
        assert query[0].count("$"+field+"_0") == 2
        cases.append({"id": field+"_two_or_ranges_reuse_parameter_names",
                      "intended_ranges": [[d.date for d in r] for r in ranges],
                      "actual_query_fragments": query, "actual_parameters": params,
                      "distinct_requested_dates": 4, "bound_parameters": len(params),
                      "scope": "parameter overwrite verified; no database execution"})

    # Only aware UTC inputs. The upstream timezone normalization is stubbed,
    # not evaluated; the wall clock is fixed for a reproducible mutation probe.
    dt = lambda hour, minute=0: datetime(2026, 10, 6, hour, minute, tzinfo=timezone.utc)
    graph.update(ensure_utc=lambda value: value, utc_now=lambda: dt(11))
    selected_definitions(texts[("graphiti", "graphiti_core/utils/maintenance/edge_operations.py")],
                         {"resolve_edge_contradictions"}, graph)
    old = SimpleNamespace(valid_at=dt(9), invalid_at=None, expired_at=None, created_at=dt(9, 1))
    before = vars(old).copy()
    new = SimpleNamespace(valid_at=dt(9, 30), invalid_at=None)
    result = graph["resolve_edge_contradictions"](new, [old])
    assert result == [old] and old.invalid_at == dt(9, 30) and old.expired_at == dt(11)
    cutoff = dt(10)
    def event_window(f):
        return f["valid_at"] <= cutoff and (f["invalid_at"] is None or f["invalid_at"] > cutoff)
    cases.append({"id": "late_known_invalidation_mutates_old_event_end", "synthetic": True,
                  "before": before, "after": vars(old).copy(), "cutoff": cutoff,
                  "event_window_before_update": event_window(before),
                  "event_window_after_update": event_window(vars(old)),
                  "ingestion_window_after_update": old.created_at <= cutoff < old.expired_at,
                  "scope": "selected mutation helper; illustrative replay predicates, not Graphiti retrieval"})

    # Transcribed values from FinBench v1 Table 1, also present in its PDF.
    # This is a table-definition consistency check, not a dataset recomputation.
    possible = [round(k/3, 2) for k in range(4)]
    for reported in [.81, .82, .83]:
        assert reported not in possible
        cases.append({"id": f"finbench_n3_coverage_{reported:g}", "reported_n": 3,
                      "reported_cov80": reported, "possible_unweighted_hit_fractions_rounded2": possible,
                      "compatible_with_binary_hit_count_over_reported_n": False,
                      "source": "https://arxiv.org/html/2607.16229v1#S6.T1",
                      "scope": "requires author clarification of coverage denominator/definition"})

    return {"schema": "orallexa.memory-calibration-source-probe.v1", "date": "2026-10-06",
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "source_inputs": identities, "case_count": len(cases), "cases": cases,
            "not_performed": ["full upstream package imports", "Platt fitting or held-out evaluation",
                              "memory retrieval/model inference or RL training", "database execution",
                              "FinBench CSV recomputation", "provider/broker calls",
                              "live-path calibration activation or runtime source edits"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphiti-root", type=Path, required=True)
    parser.add_argument("--orallexa-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to replace receipt: {args.output}")
    texts, identities = verify_sources(args.graphiti_root, args.orallexa_root)
    receipt = run(texts, identities)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, default=encode, allow_nan=False)
        handle.write("\n")
    print(f"Verified {len(identities)} source inputs; recorded {receipt['case_count']} cases.")


if __name__ == "__main__":
    main()
