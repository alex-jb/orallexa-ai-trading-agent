#!/usr/bin/env python3
"""Offline inspection of pinned SentinelBench and TIEM sources, without inference.

Only selected function ASTs execute against synthetic records. No upstream module,
server, subprocess harness, database, embedding model or provider is started.
Source bytes must match the pinned Git blobs before compilation. Output is exclusive.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import copy
import hashlib
import json
import platform
import subprocess
from collections import Counter
from datetime import datetime, time
from pathlib import Path
from types import SimpleNamespace

SENTINEL_REV = "0faca33cc58ea62e97a928b67cd3beec7176b408"
TIEM_REV = "f89bc5d8576a29a510143aafeed43a4eef571ba6"
SENTINEL_FILES = (
    "README.md", "server/server.py", "server/eval_harness.py",
    "server/session.py", "server/timing.py", "tests/test_scenario_schema.py",
)
TIEM_FILES = (
    "README.md", "foresight/stores/experience.py", "foresight/reason_loop.py",
    "foresight/config.py", "foresight/stores/text_kg.py",
)


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def snapshot(repo: Path, files: Path, revision: str, names: list[str]):
    if git(repo, "rev-parse", "HEAD") != revision:
        raise ValueError(f"Wrong source revision; expected {revision}")
    entries = {}
    for line in git(repo, "ls-tree", "-r", "--full-tree", revision).splitlines():
        meta, path = line.split("\t", 1)
        mode, kind, oid = meta.split()
        if kind == "blob":
            entries[path] = (mode, oid)
    texts, manifest = {}, []
    for name in sorted(names):
        data = (files / name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if name not in entries or entries[name] != ("100644", blob):
            raise ValueError(f"Source bytes differ from pinned Git blob: {name}")
        texts[name] = data.decode("utf-8")
        manifest.append({"path": name, "bytes": len(data), "git_blob": blob,
                         "sha256": hashlib.sha256(data).hexdigest()})
    return texts, manifest


def functions(source: str, names: tuple[str, ...], namespace: dict):
    """Compile just the inspected functions; strip route registration decorators."""
    parsed = ast.parse(source)
    selected, found = [], set()
    for node in parsed.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            selected.append(copy.deepcopy(node)); found.add(node.name)
        elif isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qualified = node.name + "." + member.name
                    if qualified in names:
                        selected.append(copy.deepcopy(member)); found.add(qualified)
    if found != set(names):
        raise ValueError("Required upstream function is missing")
    for node in selected:
        node.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(module, "<pinned-selected-functions>", "exec"), namespace)
    return namespace


def sentinel_probe(texts: dict):
    cases = []
    for label, elapsed, get_time, post_time, expected in (
        ("silent_exit_at_one_second", 1.0, None, None, True),
        ("no_contact_at_deadline", 630.0, None, None, True),
        ("contact_get_before_deadline", 1.0, 1, None, False),
        ("post_record_without_get_record", 1.0, None, 1, True),
    ):
        session = SimpleNamespace(condition_at=None, eval_sql="", simulation_time=elapsed,
                                  contact_get_time=get_time, contact_post_time=post_time,
                                  contact_message="synthetic" if post_time is not None else None)
        ns = functions(texts["server/server.py"], ("evaluate",), {
            "EvaluateResponse": lambda **kw: kw,
            "_require_session": lambda: session, "STATE_COMPLETED": "completed",
        })
        result = asyncio.run(ns["evaluate"]())
        if result["success"] is not expected:
            raise AssertionError(f"Unexpected scoring result: {label}")
        cases.append({"case": label, "synthetic_session": vars(session),
                      "observed_upstream_success": result["success"]})
    return {
        "method": "Unmodified evaluate() AST with a synthetic session and response stub; no-SQL branch only",
        "cases": cases,
        "not_executed": ["HTTP routes", "browser agent", "subprocess harness", "SQL gates", "event playback"],
        "interpretation": "No-SQL no-op scoring checks contact_get_time, not minimum coverage or contact_post_time. The POST fixture is a scoring-record boundary, not an end-to-end HTTP exploit demonstration.",
        "harness_static_review": "run_task waits for subprocess completion then calls /evaluate; no separate minimum monitoring duration is required on an early exit in this reviewed path.",
    }


def ancestor(identifier="old", resolved="2026-10-05T14:00:00+00:00"):
    return {"source_catalyst_id": identifier, "decision_time": "2026-10-01T14:00:00+00:00",
            "resolve_time": resolved, "outcome_source_hash": "0" * 64,
            "distillation_prompt_hash": "1" * 64}


def memory_probe(texts: dict):
    ns = functions(texts["foresight/stores/experience.py"],
                   ("_ancestor_key", "_union_ancestors", "_parse_pit_time", "_strict_ancestor_pit"),
                   {"datetime": datetime, "time": time})
    gate = ns["_strict_ancestor_pit"]
    before = "2026-10-06T14:00:00+00:00"
    merged = ns["_union_ancestors"]([ancestor()], [ancestor("late", before)])
    bad_hash = ancestor(); bad_hash["outcome_source_hash"] = "unverified-string"
    reversed_dates = ancestor(); reversed_dates["decision_time"] = "2026-10-07T14:00:00+00:00"
    missing_hash = ancestor(); del missing_hash["outcome_source_hash"]
    many = [ancestor(f"old-{i}") for i in range(21)]
    many = ns["_union_ancestors"](many, [ancestor("late-22", before)])
    trials = [
        ("all_outcomes_before_cutoff", [ancestor()], before, True, True),
        ("outcome_equal_to_cutoff", [ancestor(resolved=before)], before, True, False),
        ("outcome_after_cutoff", [ancestor(resolved="2026-10-07T14:00:00+00:00")], before, True, False),
        ("empty_ancestry", [], before, True, False),
        ("missing_required_hash", [missing_hash], before, True, False),
        ("invalid_resolve_time", [ancestor(resolved="invalid")], before, True, False),
        ("merged_late_ancestor", merged, before, True, False),
        ("twenty_two_ancestors_late_last", many, before, True, False),
        ("date_only_prior_day", [ancestor(resolved="2026-10-05")], "2026-10-06", True, True),
        ("date_only_same_day", [ancestor(resolved="2026-10-06")], "2026-10-06", True, False),
        ("date_only_disallowed", [ancestor(resolved="2026-10-05")], "2026-10-06", False, False),
        ("mixed_timezone_awareness", [ancestor(resolved="2026-10-05T14:00:00")], before, True, False),
        ("nonempty_hash_not_authenticated", [bad_hash], before, True, True),
        ("decision_after_resolution_not_rejected", [reversed_dates], before, True, True),
    ]
    cases = []
    for label, ancestry, cutoff, eod, expected in trials:
        skill = {"provenance_ancestors": ancestry}
        actual = gate(skill, cutoff, date_only_eod=eod)
        if actual is not expected:
            raise AssertionError(f"Unexpected ancestry result: {label}")
        cases.append({"case": label, "synthetic_skill": skill, "cutoff": cutoff,
                      "date_only_eod": eod, "observed_upstream_eligible": actual})
    return {
        "method": "Pinned original time/ancestry helper functions only, using synthetic metadata",
        "cases": cases, "merged_ancestor_count": len(merged), "large_union_count": len(many),
        "interpretation": "The helper filters all recorded resolve times and fails closed on missing fields, but does not authenticate hashes, verify that ancestry is complete, or validate decision/resolve chronology. Mixed naive/aware timestamps fail closed. Date-only values use naive end-of-day semantics.",
        "integration_static_review": "retrieve defaults strict_provenance=False, while reason_loop passes CSM_STRICT_PROVENANCE with default '1'; direct helper use and the configured full path are different scopes.",
        "not_executed": ["vector retrieval", "embedding calls", "distillation", "forecasting", "dataset audit"],
    }


def scenario_summary(texts: dict):
    records = [json.loads(text) for name, text in texts.items() if name.startswith("scenarios/")]
    if len(records) != 100 or len({x["id"] for x in records}) != 100:
        raise ValueError("Expected the complete unique 100-task cohort")
    taxonomy = Counter(); environments = Counter(); persistence = Counter(); noop_without_sql = 0
    for row in records:
        environments[row["environment"]] += 1
        persistence[row["taxonomy"]["event_persistence"]] += 1
        condition, kill, end = row["condition_at"], row["kill_at"], row["event_timeline_end"]
        if not (0 < kill <= end):
            raise ValueError(f"Invalid horizon: {row['id']}")
        times = [ev["time"] for ev in row["events"]]
        if times != sorted(times) or any(t < 0 or t > end for t in times):
            raise ValueError(f"Invalid authored event times: {row['id']}")
        if condition is None:
            taxonomy["noop"] += 1
            noop_without_sql += not bool(row.get("eval_sql"))
        else:
            if not (0 < condition <= kill) or not row.get("eval_sql"):
                raise ValueError(f"Invalid positive task: {row['id']}")
            taxonomy[row["taxonomy"]["monitoring_approach"] + "_" + row["taxonomy"]["milestone_type"]] += 1
    return {"tasks": len(records), "environment_counts": dict(sorted(environments.items())),
            "taxonomy_counts": dict(sorted(taxonomy.items())), "event_persistence": dict(persistence),
            "noop_without_sql": noop_without_sql,
            "authored_timing_checks": "All sorted, in authored timeline, and condition <= kill <= end",
            "kill_at_values": sorted({r["kill_at"] for r in records}),
            "event_timeline_end_values": sorted({r["event_timeline_end"] for r in records})}


def evidence_time_probe(texts: dict):
    query = functions(texts["foresight/stores/text_kg.py"], ("TextKG.query",), {})["query"]
    cases = []
    for label, source_time, cutoff, expected in (
        ("uniform_utc_before", "2026-10-06T13:00:00+00:00", "2026-10-06T14:00:00+00:00", True),
        ("uniform_utc_after", "2026-10-06T15:00:00+00:00", "2026-10-06T14:00:00+00:00", False),
        ("missing_timestamp", "", "2026-10-06T14:00:00+00:00", True),
        ("earlier_instant_different_offset", "2026-10-06T13:00:00+00:00", "2026-10-06T10:00:00-04:00", False),
        ("later_instant_different_offset", "2026-10-06T09:00:00-07:00", "2026-10-06T10:00:00-04:00", True),
    ):
        row = {"ts": source_time, "stock": "SYNTHETIC", "content": "synthetic fact", "__score__": 1.0}
        model_stub = SimpleNamespace(embed_one=lambda _: [])
        search_stub = SimpleNamespace(search=lambda _, top_k: [row])
        host = SimpleNamespace(embedder=model_stub, vdb_hyperedge=search_stub)
        observed = bool(query(host, "synthetic", top_k=1, before_ts=cutoff,
                              stock="SYNTHETIC", pit_strict=True))
        if observed is not expected:
            raise AssertionError(f"Unexpected evidence-time result: {label}")
        cases.append({"case": label, "source_time": source_time, "cutoff": cutoff,
                      "observed_upstream_retained": observed})
    return {"method": "Original TextKG.query AST with synthetic one-record retrieval stubs",
            "cases": cases,
            "interpretation": "This method compares nonempty timestamps as strings. Missing timestamps survive this method; offsets must already be normalized for lexical order to represent instant order. These fixtures do not establish that upstream construction emits such records or that full benchmark contexts leaked.",
            "not_executed": ["source construction", "real embeddings", "vector index", "full retrieval pipeline"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentinel-repo", required=True, type=Path)
    parser.add_argument("--sentinel-files", type=Path, help="Byte-identical source snapshot; defaults to the repo")
    parser.add_argument("--tiem-repo", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Existing receipt will not be overwritten")
    if git(args.sentinel_repo, "rev-parse", "HEAD") != SENTINEL_REV:
        raise ValueError(f"Wrong source revision; expected {SENTINEL_REV}")
    if git(args.tiem_repo, "rev-parse", "HEAD") != TIEM_REV:
        raise ValueError(f"Wrong source revision; expected {TIEM_REV}")
    names = [line.split("\t", 1)[1] for line in git(args.sentinel_repo, "ls-tree", "-r", SENTINEL_REV).splitlines()
             if "\t" in line and line.split("\t", 1)[1].startswith("scenarios/")
             and line.endswith(".json") and not line.endswith("/dev.json")]
    st, sm = snapshot(args.sentinel_repo, args.sentinel_files or args.sentinel_repo,
                      SENTINEL_REV, list(SENTINEL_FILES) + names)
    tt, tm = snapshot(args.tiem_repo, args.tiem_repo, TIEM_REV, list(TIEM_FILES))
    result = {"schema_version": 1, "research_date": "2026-10-06", "data_kind": "synthetic_source_function_probe",
              "python_version": platform.python_version(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "sources": [{"repository": "https://github.com/microsoft/sentinel_environments",
                           "revision": SENTINEL_REV, "inputs": sm},
                          {"repository": "https://github.com/QwenQKing/Fin_TIEM",
                           "revision": TIEM_REV, "inputs": tm}],
              "sentinel_scenarios": scenario_summary(st), "sentinel_scoring": sentinel_probe(st),
              "tiem_ancestry": memory_probe(tt), "tiem_evidence_times": evidence_time_probe(tt),
              "limits": "Source semantics only; no model scores, monitoring deployment, original benchmark reproduction, cost savings, independent gold labels or trading results."}
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write("\n")
    print(json.dumps({"source_files": len(sm) + len(tm), "scenarios": result["sentinel_scenarios"],
                      "sentinel_probes": len(result["sentinel_scoring"]["cases"]),
                      "memory_probes": len(result["tiem_ancestry"]["cases"]),
                      "evidence_time_probes": len(result["tiem_evidence_times"]["cases"])}))


if __name__ == "__main__":
    main()
