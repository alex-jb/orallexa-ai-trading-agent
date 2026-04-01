"""
eval/experiment.py
──────────────────────────────────────────────────────────────────
Comparative experiment harness: ALL_FAST vs ALL_DEEP vs DUAL_TIER.

Runs deep_analysis_lite under different model configurations and
compares cost, latency, decision quality, and stability.

Usage:
    from eval.experiment import run_experiment_matrix, compare_results
    results = run_experiment_matrix(["NVDA", "AAPL"])
    print(compare_results(results))
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional

import llm.claude_client as cc
import llm.call_logger as logger


# ── Model Configurations ──────────────────────────────────────────────────

_ORIGINAL_FAST = cc.FAST_MODEL
_ORIGINAL_DEEP = cc.DEEP_MODEL


class ModelConfig(Enum):
    ALL_FAST = "all_fast"
    ALL_DEEP = "all_deep"
    DUAL_TIER = "dual_tier"


def _apply_config(config: ModelConfig) -> None:
    if config == ModelConfig.ALL_FAST:
        cc.FAST_MODEL = _ORIGINAL_FAST
        cc.DEEP_MODEL = _ORIGINAL_FAST
    elif config == ModelConfig.ALL_DEEP:
        cc.FAST_MODEL = _ORIGINAL_DEEP
        cc.DEEP_MODEL = _ORIGINAL_DEEP
    else:
        cc.FAST_MODEL = _ORIGINAL_FAST
        cc.DEEP_MODEL = _ORIGINAL_DEEP


def _restore_config() -> None:
    cc.FAST_MODEL = _ORIGINAL_FAST
    cc.DEEP_MODEL = _ORIGINAL_DEEP


# ── Result ────────────────────────────────────────────────────────────────

@dataclass
class ExperimentResult:
    config: str
    ticker: str
    run_id: str
    decision: str
    confidence: float
    risk_level: str
    signal_strength: float
    reasoning_summary: str
    total_cost_usd: float
    total_latency_ms: int
    llm_call_count: int
    error: Optional[str] = None


# ── Single Experiment ─────────────────────────────────────────────────────

def run_single_experiment(
    ticker: str,
    config: ModelConfig,
) -> ExperimentResult:
    """Run deep_analysis_lite for one ticker under one model config."""
    run_id = str(uuid.uuid4())[:8]

    _apply_config(config)
    logger.current_run_id = run_id

    try:
        from core.brain import OrallexaBrain
        from engine.deep_analysis_lite import run_deep_analysis_lite
        from models.confidence import guard_decision

        brain = OrallexaBrain(ticker.upper())
        result = run_deep_analysis_lite(brain)
        dec = guard_decision(result["decision_output"])

        # Read back log entries for this run
        entries = logger.load_call_log_by_run(run_id)
        total_cost = sum(e.get("estimated_cost_usd", 0) for e in entries)
        total_latency = sum(e.get("latency_ms", 0) for e in entries)

        reasoning = "; ".join(dec.reasoning[-3:]) if dec.reasoning else ""

        return ExperimentResult(
            config=config.value,
            ticker=ticker.upper(),
            run_id=run_id,
            decision=dec.decision,
            confidence=dec.confidence,
            risk_level=dec.risk_level,
            signal_strength=dec.signal_strength,
            reasoning_summary=reasoning[:200],
            total_cost_usd=round(total_cost, 6),
            total_latency_ms=total_latency,
            llm_call_count=len(entries),
        )

    except Exception as e:
        return ExperimentResult(
            config=config.value, ticker=ticker.upper(), run_id=run_id,
            decision="ERROR", confidence=0, risk_level="HIGH",
            signal_strength=0, reasoning_summary="",
            total_cost_usd=0, total_latency_ms=0, llm_call_count=0,
            error=str(e)[:200],
        )
    finally:
        _restore_config()
        logger.current_run_id = None


# ── Matrix ────────────────────────────────────────────────────────────────

def run_experiment_matrix(
    tickers: list[str],
    configs: list[ModelConfig] = None,
) -> list[ExperimentResult]:
    """Run all config x ticker combinations sequentially."""
    if configs is None:
        configs = list(ModelConfig)

    results = []
    total = len(tickers) * len(configs)
    i = 0
    for ticker in tickers:
        for config in configs:
            i += 1
            print(f"[{i}/{total}] {ticker} × {config.value}...", end=" ", flush=True)
            r = run_single_experiment(ticker, config)
            print(f"→ {r.decision} ({r.confidence:.0f}%) ${r.total_cost_usd:.4f} {r.total_latency_ms}ms")
            results.append(r)
    return results


# ── Comparison ────────────────────────────────────────────────────────────

def compare_results(results: list[ExperimentResult]) -> str:
    """Format results as a comparison table."""
    lines = []
    lines.append(f"{'Config':<12} {'Ticker':<8} {'Decision':<8} {'Conf':>5} {'Signal':>7} {'Risk':<8} {'Cost':>8} {'Latency':>8} {'Calls':>5}")
    lines.append("─" * 80)
    for r in results:
        lines.append(
            f"{r.config:<12} {r.ticker:<8} {r.decision:<8} {r.confidence:>5.0f}% "
            f"{r.signal_strength:>6.0f} {r.risk_level:<8} "
            f"${r.total_cost_usd:>7.4f} {r.total_latency_ms:>6}ms {r.llm_call_count:>5}"
        )

    # Summary by config
    from collections import defaultdict
    by_config = defaultdict(list)
    for r in results:
        by_config[r.config].append(r)

    lines.append("\n── Summary ──")
    lines.append(f"{'Config':<12} {'Avg Cost':>10} {'Avg Latency':>12} {'Avg Conf':>10}")
    lines.append("─" * 48)
    for cfg, rs in by_config.items():
        avg_cost = sum(r.total_cost_usd for r in rs) / len(rs)
        avg_lat = sum(r.total_latency_ms for r in rs) / len(rs)
        avg_conf = sum(r.confidence for r in rs) / len(rs)
        lines.append(f"{cfg:<12} ${avg_cost:>9.4f} {avg_lat:>10.0f}ms {avg_conf:>9.0f}%")

    return "\n".join(lines)
