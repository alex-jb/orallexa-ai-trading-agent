"""Reaggregate published agent-cost summaries; no inference or provider calls.

Supply a local, pinned lchen001/pricing-reversal checkout containing the two
constant files and 24 current Cybench/GAIA/Terminal-Bench summary files. This
script intentionally does not reproduce the paper's full 12-task experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess

SOURCE_REVISION = "55882d9715ea3cd971abd52a41c2c88e216ba0c1"
MODELS = (
    "gpt-5.4", "gpt-5.4-mini", "gemini-3.1-pro", "gemini-3-flash",
    "claude-opus-4.7", "claude-haiku-4.5", "kimi-k2.6", "minimax-m2.7",
)
COHORTS = (
    ("cybench-react", "cybench", "react", 39),
    ("gaia-react", "gaia", "react", 165),
    ("tb2-terminus2", "terminal-bench", "terminus2", 89),
)
TOLERANCE_USD = 1e-8


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True,
    ).strip()


def number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}: expected a finite nonnegative number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{label}: expected a finite nonnegative number")
    return result


def quantile(values: list[float], probability: float) -> float:
    """Nearest-rank empirical quantile, with no fitted distribution."""
    return sorted(values)[math.ceil(len(values) * probability) - 1]


def reaggregate(root: Path) -> dict:
    if git(root, "rev-parse", "HEAD") != SOURCE_REVISION:
        raise ValueError("source checkout must be at the declared revision")
    inputs: list[dict] = []

    def read(path: str) -> dict:
        content = (root / path).read_bytes()
        expected = git(root, "rev-parse", f"{SOURCE_REVISION}:{path}")
        actual = hashlib.sha1(
            b"blob " + str(len(content)).encode() + b"\0" + content,
        ).hexdigest()
        if actual != expected:
            raise ValueError(f"modified source file: {path}")
        inputs.append({
            "path": path, "git_blob_oid": expected,
            "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
        })
        return json.loads(content)

    info = read("constant/model_info.json")
    config = read("constant/experiment_config.json")
    prices = {item["model_name"]: item for item in info["models"]}
    if set(prices) != set(MODELS) or len(info["models"]) != len(MODELS):
        raise ValueError("unexpected pricing-model cohort")
    if {item["model_name"] for item in config["models"]} != set(MODELS):
        raise ValueError("unexpected experiment-model cohort")
    task_variants = {item["file_prefix"]: (item["dataset_name"], item["split"]) for item in config["datasets"]}
    results: list[dict] = []
    total_records = total_reversals = total_comparisons = total_residuals = 0
    total_raw_outputs = total_prompts = total_ground_truths = 0
    illustrative_row = None
    for prefix, dataset, split, expected_n in COHORTS:
        if task_variants.get(prefix) != (dataset, split):
            raise ValueError(f"unexpected configured task variant: {prefix}")
        rows: list[dict] = []
        expected_ids: set[str] | None = None
        for model in MODELS:
            data = read(f"data/consolidated/{prefix}-{model}.json")
            if (data["model_name"], data["dataset_name"], data["split"]) != (model, dataset, None):
                raise ValueError(f"identity mismatch for {prefix}/{model}")
            records = data["records"]
            ids = [str(item["index"]) for item in records]
            if len(ids) != expected_n or len(set(ids)) != expected_n:
                raise ValueError(f"missing/duplicate records for {prefix}/{model}")
            if expected_ids is not None and set(ids) != expected_ids:
                raise ValueError(f"unpaired query cohort for {prefix}/{model}")
            expected_ids = set(ids)
            costs = [number(item["cost"], "record cost") for item in records]
            scores = [number(item["score"], "record score") for item in records]
            if any(score not in (0.0, 1.0) for score in scores):
                raise ValueError("expected binary reported scores")
            total = math.fsum(costs)
            if not math.isclose(total, number(data["cost"], "top-level cost"), rel_tol=0, abs_tol=TOLERANCE_USD):
                raise ValueError(f"top-level cost does not sum for {prefix}/{model}")
            if not math.isclose(math.fsum(scores) / expected_n, number(data["performance"], "performance"), rel_tol=0, abs_tol=1e-12):
                raise ValueError(f"reported score average mismatch for {prefix}/{model}")
            pricing = prices[model]
            input_rate = number(pricing["input_price_per_MTok"], "input rate")
            output_rate = number(pricing["output_price_per_MTok"], "output rate")
            cache_rate = number(pricing.get("cached_input_price_per_MTok", pricing.get("cached_input_read_price_per_MTok")), "cache-read rate")
            conditional_costs = []
            turns = []
            for record in records:
                conditional_costs.append((
                    number(record["prompt_tokens"], "prompt tokens") * input_rate
                    + number(record["cache_tokens"], "cache tokens") * cache_rate
                    + number(record["completion_tokens"], "completion tokens") * output_rate
                ) / 1e6)
                turns.append(number(record["n_turns"], "turns"))
            residuals = [abs(actual - estimated) for actual, estimated in zip(costs, conditional_costs)]
            residual_count = sum(value > TOLERANCE_USD for value in residuals)
            correct = int(math.fsum(scores))
            nonempty_raw = sum(bool(item.get("raw_output")) for item in records)
            nonempty_prompts = sum(bool(item.get("prompt")) for item in records)
            nonempty_gold = sum(bool(item.get("ground_truth")) for item in records)
            total_records += expected_n
            total_residuals += residual_count
            total_raw_outputs += nonempty_raw
            total_prompts += nonempty_prompts
            total_ground_truths += nonempty_gold
            rows.append({
                "model": model, "records": expected_n,
                "listed_price_index_input_plus_output": input_rate + output_rate,
                "published_record_cost_sum_usd": total,
                "reported_correct": correct,
                "reported_accuracy": correct / expected_n,
                "all_record_cost_per_reported_correct_usd": total / correct if correct else None,
                "cost_on_reported_incorrect_usd": math.fsum(cost for cost, score in zip(costs, scores) if score == 0),
                "published_cost_p50_usd": quantile(costs, 0.5),
                "published_cost_p95_usd": quantile(costs, 0.95),
                "reported_turns_p95": quantile(turns, 0.95),
                "conditional_tariff_residual_count": residual_count,
                "conditional_tariff_max_absolute_residual_usd": max(residuals),
                "nonempty_raw_outputs": nonempty_raw,
            })
            if prefix == "cybench-react" and model == "gpt-5.4-mini":
                illustrative_row = {
                    "dataset": dataset, "model": model, "record_index": ids[0],
                    "published_cost_usd": costs[0],
                    "conditional_metadata_tariff_cost_usd": conditional_costs[0],
                    "prompt_tokens": records[0]["prompt_tokens"],
                    "cache_tokens": records[0]["cache_tokens"],
                    "completion_tokens": records[0]["completion_tokens"],
                }
        reversals = []
        tied_pairs = comparisons = 0
        for left, right in itertools.combinations(rows, 2):
            price_difference = left["listed_price_index_input_plus_output"] - right["listed_price_index_input_plus_output"]
            cost_difference = left["published_record_cost_sum_usd"] - right["published_record_cost_sum_usd"]
            if price_difference == 0 or cost_difference == 0:
                tied_pairs += 1
                continue
            comparisons += 1
            if price_difference * cost_difference < 0:
                low, high = (left, right) if price_difference < 0 else (right, left)
                reversals.append({
                    "lower_listed_price_model": low["model"],
                    "higher_listed_price_model": high["model"],
                    "published_cost_ratio": low["published_record_cost_sum_usd"] / high["published_record_cost_sum_usd"],
                })
        total_reversals += len(reversals)
        total_comparisons += comparisons
        results.append({
            "dataset": dataset, "configured_task_variant": split,
            "published_split_metadata": None, "queries_per_model": expected_n,
            "comparisons": comparisons, "tied_pairs": tied_pairs,
            "reversals": len(reversals), "reversal_rate": len(reversals) / comparisons,
            "models": rows, "reversal_pairs": reversals,
        })
    return {
        "schema_version": 1,
        "report_kind": "published_summary_reaggregation_with_provenance_limits",
        "source_repository": "https://github.com/lchen001/pricing-reversal",
        "source_revision": SOURCE_REVISION,
        "paper_version_reviewed": "https://arxiv.org/html/2603.23971v2",
        "pricing_metadata_last_updated": info["_metadata"]["last_updated"],
        "scope": "3 agentic task subsets, 8 model names; not the full 12-task paper",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "quantile_definition": "nearest rank: sorted values at ceil(n*p)-1",
        "conditional_tariff_assumptions": [
            "prompt_tokens are fresh input; cache_tokens are all cache reads",
            "completion_tokens include reasoning once; no additional charges",
            "the supplied pricing snapshot applies to every summary record",
        ],
        "conditional_tariff_tolerance_usd": TOLERANCE_USD,
        "totals": {
            "source_files": len(inputs), "model_result_files": 24,
            "published_records": total_records, "comparisons": total_comparisons,
            "reversals": total_reversals,
            "reversal_rate": total_reversals / total_comparisons,
            "conditional_tariff_residual_records": total_residuals,
            "nonempty_raw_outputs": total_raw_outputs,
            "nonempty_prompts": total_prompts, "nonempty_ground_truths": total_ground_truths,
        },
        "checks": {
            "source_revision_and_blob_bytes": "passed",
            "complete_unique_paired_query_cohorts": "passed",
            "finite_nonnegative_numbers_and_binary_scores": "passed",
            "top_level_cost_and_reported_accuracy_aggregation": "passed",
            "provider_billing_reconciliation": "not established",
            "independent_regrading_or_model_identity_authentication": "not performed",
        },
        "illustrative_conditional_tariff_residual": illustrative_row,
        "inputs": inputs, "results": results,
        "limitations": [
            "Published cost/score columns are author records, not verified invoices or independent labels.",
            "Conditional tariff residuals do not establish billing errors; cache write/read, model/tariff dates and other provenance remain unresolved.",
            "Empty shared responses/prompts/gold prevent replay and independent answer grading from these files.",
            "Task variants come from experiment_config/file prefixes; the result files' split metadata is null.",
            "The 25/84 subset rate is not a replication of the full paper's rounded 32% statistic.",
            "All costs, including records scored incorrect, stay in the aggregation.",
            "No current price lookup, model call, GPU computation or Orallexa news prediction occurs.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = reaggregate(args.source.resolve())
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(serialized)
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
