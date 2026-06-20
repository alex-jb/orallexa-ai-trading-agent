"""benchmark_provider_ab.py — A/B benchmark across LLM providers.

Drives the 5 representative quant prompts (extracted from real call sites
in llm/debate.py / llm/perspective_panel.py / llm/strategy_generator.py)
through every available provider in llm/provider.py, logs cost + latency +
JSON-conformance to a JSONL file, and emits a Markdown summary.

Surfaced by the 2026-06-20 daily-brief-distill cron (§3 row 6):
"GPT-4o vs GLM-5.2 quant A/B (5 prompt 对比)". Today we cover the three
provider families that have implementations in llm/provider.py:
  - anthropic (haiku-4-5 / sonnet-4-6)
  - openai (gpt-4.1 / o4-mini)
  - glm (glm-4.6 / glm-5.2)  — needs commit a6750a9 (GlmProvider)

A run with all three keys present takes ~30s and ~$0.05-$0.15 depending
on chosen models. Skips providers gracefully if their API key is unset —
single-provider runs are useful for harness verification.

Scoring is deterministic (no LLM-as-judge): JSON parse success, required
schema fields present, output length, provider-reported cost + latency.
Quality grading is human / Brier-resolution work — not in scope here.

Usage:
    # Default: all providers, default models, full prompt set
    python eval/benchmark_provider_ab.py

    # Subset of providers
    python eval/benchmark_provider_ab.py --providers anthropic,glm

    # Override models
    python eval/benchmark_provider_ab.py \\
        --anthropic-model claude-haiku-4-5-20251001 \\
        --openai-model gpt-4.1-mini \\
        --glm-model glm-4.6

    # Dry-run (validate prompts + provider availability, no API calls)
    python eval/benchmark_provider_ab.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from llm.provider import get_provider, _REGISTRY  # noqa: E402


# ────────────────────────────────────────────────────────────────────
# Synthetic fixture — keeps the benchmark deterministic across runs
# (no yfinance calls, no time-of-day variance).
# ────────────────────────────────────────────────────────────────────

FIXTURE_TICKER = "NVDA"
FIXTURE_CONTEXT = """\
MARKET DATA (synthetic snapshot for benchmark):
- Close: $172.40
- MA20: $168.15 (close above)
- MA50: $159.80 (close above)
- MA20 slope: +0.8%/week
- RSI(14): 58.4 (neutral, room to run)
- MACD: +1.20 (above signal +0.80, bullish crossover 3 days ago)
- Volume: 51.2M (1.3x 20-day avg)
- ATR(14): $4.85 (2.8% of price)
- 50-day high: $176.20 (3 days ago)
- 50-day low: $148.30 (28 days ago)
- Sector: 🧠 AI Infra
- Insider trades (90d): 0 buys, 2 sells totalling $1.2M (CFO + VP Eng)
"""

FIXTURE_INITIAL_DECISION = {
    "decision": "BUY",
    "confidence": 62.0,
    "signal_strength": 55.0,
    "reasoning": [
        "Close above MA20 and MA50, both sloping up",
        "MACD bullish crossover 3 days ago, holding above signal line",
        "Volume confirming with 1.3x 20-day average",
    ],
}


# ────────────────────────────────────────────────────────────────────
# Prompt set — extracted from real Orallexa LLM call sites
# ────────────────────────────────────────────────────────────────────

@dataclass
class PromptSpec:
    """One benchmark prompt + how to score the output."""
    id: str
    description: str
    request_type: str
    user_message: str
    max_tokens: int
    expected_format: str  # "text" or "json"
    required_json_fields: list[str] = field(default_factory=list)


def _bull_prompt() -> str:
    init = FIXTURE_INITIAL_DECISION
    return (
        "You are a Bull Analyst. Build a compelling, evidence-based case FOR "
        "entering a long position on this stock.\n\n"
        f"{FIXTURE_CONTEXT}\n"
        f"Initial signal: {init['decision']} (confidence {init['confidence']:.0f}%, "
        f"signal strength {init['signal_strength']:.0f})\n"
        f"Initial reasoning: {'; '.join(init['reasoning'])}\n\n"
        "Structure your argument with numbered points:\n\n"
        "1. **Momentum & Trend** — What does price action, moving averages, and MACD tell us?\n"
        "2. **Entry Setup** — Why is now a good time? Reference specific indicator values.\n"
        "3. **Catalyst / Context** — Any news, sector strength, or volume confirmation?\n"
        "4. **Risk/Reward** — Why is the upside worth the risk? Quantify if possible.\n\n"
        "Write 3-4 detailed paragraphs (300-400 words). Use specific data from the indicators above. "
        "Be persuasive but grounded in evidence."
    )


def _bear_prompt() -> str:
    init = FIXTURE_INITIAL_DECISION
    return (
        "You are a Bear Analyst. Build a compelling, evidence-based case AGAINST this trade.\n\n"
        f"{FIXTURE_CONTEXT}\n"
        f"Initial signal: {init['decision']} (confidence {init['confidence']:.0f}%)\n\n"
        "The Bull Analyst argues that momentum is intact and the MACD crossover plus volume "
        "confirmation justify entry. The CFO/VP Eng insider sales are dismissed as routine.\n\n"
        "Directly counter the bull's argument with numbered points:\n\n"
        "1. **Trend Risks** — What bearish signals is the bull ignoring? Divergences, exhaustion, overhead resistance?\n"
        "2. **Timing Concerns** — Why might this NOT be the right entry? Overbought conditions, low volume?\n"
        "3. **Downside Scenario** — What happens if the trade goes wrong? Key support levels to watch.\n"
        "4. **Macro / Context Risk** — Insider selling, sector beta, broader market headwinds?\n\n"
        "Write 3-4 detailed paragraphs (300-400 words). Counter specific claims from the bull. "
        "Be persuasive but grounded in evidence."
    )


def _judge_prompt() -> str:
    init = FIXTURE_INITIAL_DECISION
    return (
        "You are a senior portfolio manager making the final trading decision.\n\n"
        f"{FIXTURE_CONTEXT}\n\n"
        f"Initial signal: {init['decision']} (confidence {init['confidence']:.0f}%)\n\n"
        "BULL CASE: Price above MA20/MA50, MACD bullish crossover 3 days ago, volume 1.3x avg, "
        "sector AI Infra strong, RSI 58.4 has room to run.\n\n"
        "BEAR CASE: $176.20 50-day high is 3 days away — overhead resistance; CFO + VP Eng insider "
        "selling $1.2M is a credibility signal; MACD crossover is 3 days old (late), RSI 58 means "
        "the easy gains are gone; ATR 2.8% means a stop is wide and the entry is expensive.\n\n"
        "Synthesize both arguments. Weigh the evidence. Make a decisive call.\n\n"
        "Output ONLY valid JSON (no markdown):\n"
        "{\n"
        '  "decision": "BUY",\n'
        '  "confidence": 65.0,\n'
        '  "risk_level": "MEDIUM",\n'
        '  "up_probability": 0.60,\n'
        '  "neutral_probability": 0.25,\n'
        '  "down_probability": 0.15,\n'
        '  "reasoning_summary": "one sentence explaining the final call",\n'
        '  "reasoning_detail": "2-3 sentences expanding on the key factors"\n'
        "}\n\n"
        "Rules:\n"
        '- decision: "BUY", "SELL", or "WAIT"\n'
        '- risk_level: "LOW", "MEDIUM", or "HIGH"\n'
        "- probabilities sum to 1.0\n"
        "- confidence: 0-100"
    )


def _perspective_prompt() -> str:
    return (
        "You are a Technical Analyst on a trading desk. Your edge is reading "
        "price/volume patterns and indicator confluence; you do not look at fundamentals.\n\n"
        f"Analyze {FIXTURE_TICKER} from your perspective. Focus on: trend direction, momentum, "
        "entry setup quality, key support/resistance levels.\n\n"
        f"{FIXTURE_CONTEXT}\n"
        "Output ONLY valid JSON (no markdown):\n"
        "{\n"
        '  "bias": "BULLISH",\n'
        '  "score": 40,\n'
        '  "conviction": 65,\n'
        '  "reasoning": "2-3 sentences explaining your view with specific data points",\n'
        '  "key_factor": "single most important factor driving your view"\n'
        "}\n\n"
        "Rules:\n"
        '- bias: "BULLISH", "BEARISH", or "NEUTRAL"\n'
        "- score: -100 (max bearish) to +100 (max bullish)\n"
        "- conviction: 0-100 (how confident in your view)\n"
        "- reasoning: reference specific indicator values from the data\n"
        "- key_factor: one concise phrase"
    )


def _strategy_gen_prompt() -> str:
    return (
        "You are an AI quant strategy designer. Generate parameters for a 5-minute scalping "
        f"strategy on {FIXTURE_TICKER} given current market conditions.\n\n"
        f"{FIXTURE_CONTEXT}\n"
        "Output ONLY valid JSON (no markdown):\n"
        "{\n"
        '  "rsi_min": 30,\n'
        '  "rsi_max": 70,\n'
        '  "stop_loss": 0.02,\n'
        '  "take_profit": 0.04,\n'
        '  "lookback_minutes": 60,\n'
        '  "volume_threshold": 1.2,\n'
        '  "rationale": "one sentence linking the parameter choices to the market data"\n'
        "}\n\n"
        "Rules:\n"
        "- rsi_min < rsi_max, both in [0, 100]\n"
        "- stop_loss + take_profit are decimals (e.g. 0.02 = 2%)\n"
        "- take_profit > stop_loss (positive risk:reward)\n"
        "- lookback_minutes >= 15\n"
        "- volume_threshold >= 1.0"
    )


PROMPTS: list[PromptSpec] = [
    PromptSpec(
        id="bull",
        description="Bull analyst long-form persuasive argument",
        request_type="ab_bench_bull",
        user_message=_bull_prompt(),
        max_tokens=800,
        expected_format="text",
    ),
    PromptSpec(
        id="bear",
        description="Bear analyst counter-argument",
        request_type="ab_bench_bear",
        user_message=_bear_prompt(),
        max_tokens=800,
        expected_format="text",
    ),
    PromptSpec(
        id="judge",
        description="Judge multi-input synthesis to strict JSON",
        request_type="ab_bench_judge",
        user_message=_judge_prompt(),
        max_tokens=600,
        expected_format="json",
        required_json_fields=[
            "decision", "confidence", "risk_level",
            "up_probability", "neutral_probability", "down_probability",
            "reasoning_summary", "reasoning_detail",
        ],
    ),
    PromptSpec(
        id="perspective",
        description="Single-role perspective panel JSON",
        request_type="ab_bench_perspective",
        user_message=_perspective_prompt(),
        max_tokens=400,
        expected_format="json",
        required_json_fields=["bias", "score", "conviction", "reasoning", "key_factor"],
    ),
    PromptSpec(
        id="strategy_gen",
        description="Numeric parameter generation for scalping strategy",
        request_type="ab_bench_strategy_gen",
        user_message=_strategy_gen_prompt(),
        max_tokens=400,
        expected_format="json",
        required_json_fields=[
            "rsi_min", "rsi_max", "stop_loss", "take_profit",
            "lookback_minutes", "volume_threshold", "rationale",
        ],
    ),
]


# ────────────────────────────────────────────────────────────────────
# Provider matrix
# ────────────────────────────────────────────────────────────────────

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai":    "gpt-4.1",
    "glm":       "glm-5.2",
}

PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai":    "OPENAI_API_KEY",
    "glm":       "GLM_API_KEY",
}


def provider_available(name: str) -> bool:
    env_var = PROVIDER_KEY_ENV.get(name)
    if env_var is None:
        return True
    return bool(os.environ.get(env_var))


# ────────────────────────────────────────────────────────────────────
# Scoring (deterministic — no LLM-as-judge)
# ────────────────────────────────────────────────────────────────────

def _extract_text(response) -> str:
    """Pull text from the provider-wrapped response object."""
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "".join(parts).strip()


def _strip_codefence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # remove leading ```lang
        t = t.split("\n", 1)[1] if "\n" in t else t
        # remove trailing ```
        if "```" in t:
            t = t.rsplit("```", 1)[0]
    return t.strip()


def score_output(spec: PromptSpec, text: str) -> dict:
    """Return scoring dict — fields depend on expected_format."""
    word_count = len(text.split())
    result: dict[str, Any] = {
        "word_count": word_count,
        "char_count": len(text),
    }

    if spec.expected_format == "text":
        result["json_parsed"] = None
        result["schema_pct"] = None
        return result

    # JSON path
    cleaned = _strip_codefence(text)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    parsed: Optional[dict] = None
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            parsed = None

    result["json_parsed"] = parsed is not None
    if parsed is None or not spec.required_json_fields:
        result["schema_pct"] = 0.0 if parsed is None else 1.0
        return result

    present = sum(1 for f in spec.required_json_fields if f in parsed)
    result["schema_pct"] = round(present / len(spec.required_json_fields), 3)
    return result


# ────────────────────────────────────────────────────────────────────
# Runner
# ────────────────────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    provider: str
    model: str
    prompt_id: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    word_count: int
    char_count: int
    json_parsed: Optional[bool]
    schema_pct: Optional[float]
    error: Optional[str]
    text_sample: str  # first 240 chars for human spot-check


def run_one(
    provider_name: str,
    model: str,
    spec: PromptSpec,
) -> BenchmarkResult:
    text = ""
    error: Optional[str] = None
    latency_ms = 0
    in_tokens = 0
    out_tokens = 0
    cost = 0.0

    try:
        provider = get_provider(provider_name)
        t0 = time.monotonic()
        response, record = provider.complete(
            model=model,
            max_tokens=spec.max_tokens,
            messages=[{"role": "user", "content": spec.user_message}],
            request_type=spec.request_type,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        text = _extract_text(response)
        in_tokens = getattr(record, "input_tokens", 0)
        out_tokens = getattr(record, "output_tokens", 0)
        cost = float(getattr(record, "estimated_cost_usd", 0.0) or 0.0)
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:200]}"

    scored = score_output(spec, text)

    return BenchmarkResult(
        provider=provider_name,
        model=model,
        prompt_id=spec.id,
        latency_ms=latency_ms,
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        estimated_cost_usd=round(cost, 6),
        word_count=scored["word_count"],
        char_count=scored["char_count"],
        json_parsed=scored["json_parsed"],
        schema_pct=scored["schema_pct"],
        error=error,
        text_sample=text[:240],
    )


def run_benchmark(
    providers: list[str],
    models: dict[str, str],
    prompts: list[PromptSpec],
    output_dir: Path,
    *,
    dry_run: bool = False,
) -> list[BenchmarkResult]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    jsonl_path = output_dir / f"ab_{ts}.jsonl"
    md_path = output_dir / f"ab_{ts}.md"

    skipped: list[tuple[str, str]] = []
    runnable: list[str] = []
    for p in providers:
        if p not in _REGISTRY:
            skipped.append((p, "not in registry"))
        elif not provider_available(p):
            skipped.append((p, f"{PROVIDER_KEY_ENV[p]} unset"))
        else:
            runnable.append(p)

    if dry_run:
        print(f"[dry-run] would write to {jsonl_path}")
        print(f"[dry-run] runnable providers: {runnable}")
        print(f"[dry-run] skipped: {skipped}")
        print(f"[dry-run] prompts ({len(prompts)}): {[p.id for p in prompts]}")
        return []

    results: list[BenchmarkResult] = []
    with jsonl_path.open("w") as f:
        for provider_name in runnable:
            model = models.get(provider_name) or DEFAULT_MODELS[provider_name]
            for spec in prompts:
                print(f"[benchmark] {provider_name}/{model} → {spec.id} …", flush=True)
                r = run_one(provider_name, model, spec)
                results.append(r)
                f.write(json.dumps(asdict(r)) + "\n")
                if r.error:
                    print(f"  ERROR: {r.error}")
                else:
                    json_tag = (
                        ""
                        if r.json_parsed is None
                        else f" json={r.json_parsed} schema={r.schema_pct}"
                    )
                    print(
                        f"  OK {r.latency_ms}ms ${r.estimated_cost_usd:.4f} "
                        f"in={r.input_tokens} out={r.output_tokens} "
                        f"words={r.word_count}{json_tag}"
                    )

    _write_markdown_summary(md_path, results, runnable, skipped, models)
    print(f"\n[benchmark] wrote {jsonl_path}")
    print(f"[benchmark] wrote {md_path}")
    return results


def _write_markdown_summary(
    path: Path,
    results: list[BenchmarkResult],
    runnable: list[str],
    skipped: list[tuple[str, str]],
    models: dict[str, str],
) -> None:
    lines: list[str] = []
    lines.append(f"# Provider A/B benchmark — {datetime.now(timezone.utc).isoformat()}\n")
    lines.append(f"**Runnable providers:** {', '.join(runnable) or 'none'}")
    if skipped:
        lines.append(f"**Skipped:** {', '.join(f'{p} ({why})' for p, why in skipped)}")
    lines.append("")
    lines.append(f"**Models used:** " + ", ".join(
        f"`{p}={models.get(p, DEFAULT_MODELS[p])}`" for p in runnable
    ))
    lines.append("")
    lines.append("## Per-prompt × provider")
    lines.append("")
    lines.append("| Prompt | Provider/Model | Latency | Cost | In/Out tokens | Words | JSON | Schema |")
    lines.append("|---|---|---:|---:|---:|---:|:---:|---:|")
    for r in results:
        json_cell = "—" if r.json_parsed is None else ("✅" if r.json_parsed else "❌")
        schema_cell = "—" if r.schema_pct is None else f"{r.schema_pct:.0%}"
        err = f" 🚨 {r.error}" if r.error else ""
        lines.append(
            f"| {r.prompt_id} | {r.provider}/{r.model} | "
            f"{r.latency_ms}ms | ${r.estimated_cost_usd:.4f} | "
            f"{r.input_tokens}/{r.output_tokens} | {r.word_count} | "
            f"{json_cell} | {schema_cell} |{err}"
        )
    lines.append("")
    lines.append("## Aggregate per provider")
    lines.append("")
    by_provider: dict[str, list[BenchmarkResult]] = {}
    for r in results:
        by_provider.setdefault(r.provider, []).append(r)
    lines.append("| Provider | Calls | Total cost | Total latency | Avg words | JSON pass rate |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for p, rs in by_provider.items():
        json_calls = [r for r in rs if r.json_parsed is not None]
        json_pass = sum(1 for r in json_calls if r.json_parsed) / len(json_calls) if json_calls else 0
        lines.append(
            f"| {p} | {len(rs)} | ${sum(r.estimated_cost_usd for r in rs):.4f} | "
            f"{sum(r.latency_ms for r in rs)}ms | "
            f"{sum(r.word_count for r in rs) // len(rs)} | "
            f"{json_pass:.0%} |"
        )
    lines.append("")
    lines.append("## Text samples (first 240 chars)")
    lines.append("")
    for r in results:
        lines.append(f"### {r.prompt_id} — {r.provider}/{r.model}")
        lines.append("")
        lines.append("```")
        lines.append(r.text_sample or "[empty]")
        lines.append("```")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--providers",
        default="anthropic,openai,glm",
        help="Comma-separated provider names. Default: anthropic,openai,glm",
    )
    parser.add_argument("--anthropic-model", default=DEFAULT_MODELS["anthropic"])
    parser.add_argument("--openai-model", default=DEFAULT_MODELS["openai"])
    parser.add_argument("--glm-model", default=DEFAULT_MODELS["glm"])
    parser.add_argument(
        "--prompts",
        default="bull,bear,judge,perspective,strategy_gen",
        help="Comma-separated prompt ids to run.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_ROOT / "eval" / "history" / "provider-ab"),
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate setup without making API calls.")
    args = parser.parse_args(argv)

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    models = {
        "anthropic": args.anthropic_model,
        "openai":    args.openai_model,
        "glm":       args.glm_model,
    }
    requested_ids = {p.strip() for p in args.prompts.split(",") if p.strip()}
    prompts = [p for p in PROMPTS if p.id in requested_ids]
    if not prompts:
        print(f"[benchmark] no matching prompts in {sorted(requested_ids)}", file=sys.stderr)
        return 2

    run_benchmark(
        providers=providers,
        models=models,
        prompts=prompts,
        output_dir=Path(args.output_dir),
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
