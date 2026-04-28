# DSPy Migration Plan — Programmatic Prompt Optimization

> Status: **planning only.** Not started in code. Estimated 2-3
> dedicated sessions before any production benefit.

## Why DSPy

We hand-tuned ~15 prompts across `llm/` and `engine/` (Bull, Bear,
Judge, Risk Manager, Perspective Panel × 4 roles, Scenario Sim,
Strategy Generator, Strategy Explainer, Market Report, Pre-Market
Playbook, AI Picks, Daily Summary, Regime LLM, Compression). Each
was tuned by reading outputs and hand-editing strings. That doesn't
scale and doesn't measure.

[DSPy](https://dspy.ai) (Stanford NLP, MIT-licensed) compiles
`Signature` declarations into prompts using Bayesian-optimized
selection of instructions and few-shot examples, scored by an
evaluation metric we provide. Two practical wins:

1. **Cross-model portability** — same DSPy program targets Claude
   Sonnet 4.6, Opus 4.7, GPT-5, Gemini 3 with one config change.
   Our [`llm/provider.py`](../llm/provider.py) shim positions us
   for this; DSPy is the next step.
2. **Measured optimization** — instead of "this prompt feels better,"
   we get "MIPROv2 found this prompt scores 0.71 on the eval set vs
   0.62 for the hand-written one."

## Three migration phases

### Phase A — bootstrap (1 session)
- Install: `pip install dspy-ai==2.x`
- Configure backend: `dspy.configure(lm=dspy.LM("anthropic/claude-haiku-4-5-20251001"))`
- Build the **first** signature for `_call_judge` (debate.py:147):
  ```python
  class JudgeSignature(dspy.Signature):
      """Synthesize Bull and Bear arguments into a final verdict."""
      bull_argument: str = dspy.InputField()
      bear_argument: str = dspy.InputField()
      ticker: str = dspy.InputField()
      decision: Literal["BUY", "SELL", "WAIT"] = dspy.OutputField()
      confidence: int = dspy.OutputField(desc="0-100")
      reasoning_detail: str = dspy.OutputField(desc="2-3 sentences")
  ```
- Wrap in `dspy.Predict(JudgeSignature)` and run head-to-head against
  the hand-tuned prompt on 50 historical Bull/Bear pairs from the
  decision_log. Compare confidence calibration, decision agreement,
  reasoning quality.

### Phase B — eval set + first compile (1 session) — **harness shipped 2026-04-27**
- Build the eval dataset: 100 (Bull, Bear, ticker, "ground truth"
  decision) examples drawn from `decision_log.jsonl` where the eventual
  5-day return clearly favored BUY/SELL/WAIT.
- Define metric: `metric(example, prediction) → bool` checking
  decision match + confidence within ±15 of ground truth.
- Run `MIPROv2` optimizer:
  ```python
  optimizer = dspy.MIPROv2(metric=judge_metric, auto="medium")
  compiled_judge = optimizer.compile(dspy.Predict(JudgeSignature),
                                      trainset=train, valset=val)
  ```
  Expected cost: 100-500 LLM calls, ~$5-20 one-time.

**Phase B status (as of 2026-04-27):** the *harness* is shipped and tested
end-to-end against synthetic data. It cannot be run on real data yet — the
debate-text stash on `decision.extra` only started in Phase 10, so the
294-record `decision_log.json` has 0 rows with bull/bear arguments. The
harness short-circuits with `Phase B status: below_threshold` until the
production runtime accumulates 100 eligible records.

What's already in:
- `scripts/build_dspy_eval_set.py --synthesize N` — deterministic, label-balanced
  synthetic rows for harness validation. Each ground_truth has matching narrative
  strength so a working compile should improve on the baseline.
- `scripts/compile_judge_dspy.py` — load eval set → filter eligible → 80/20
  split → MIPROv2 compile (when ≥100 records and dspy installed) → evaluate
  baseline vs compiled on holdout → save artifact + ship-or-reject verdict
  against the 5% gate. Status field stable: `no_eval_data | below_threshold |
  dry_run | dspy_not_installed | compiled`.
- `llm.dspy_judge.load_compiled_judge(path)` — production hook that loads a
  saved artifact and returns a predictor matching `judge_dspy`'s API. Per-path
  cache; `reset_compiled_cache()` for tests.

What still triggers Phase B's real run:
- 100 production deep-analyses with `extra.debate` populated (each new
  `multi_agent_analysis` call adds one).
- Then: `pip install dspy-ai>=2.5`, `export ANTHROPIC_API_KEY=...`,
  `python scripts/build_dspy_eval_set.py --days 5`,
  `python scripts/compile_judge_dspy.py --auto medium`. The harness handles
  the rest.

### Phase C — broaden + ship (1 session)
- Convert remaining high-value prompts in priority order:
  Risk Manager → Perspective Panel roles → Scenario Sim → Strategy
  Generator. Skip the 1-shot utility prompts (compression, narrative).
- Each compiled program saved as JSON; reload at runtime.
- Wire compiled-or-fallback toggle: `if dspy_artifacts_present()
  use compiled, else fall back to current path` so we ship gradually.

## Risk / cost considerations

- **Compile cost**: 100-500 LLM calls per signature × 5 signatures
  = ~$25-100 one-time. Recompile only when the eval set or model
  changes meaningfully.
- **Evaluation noise**: financial outcomes are noisy. Need ≥100
  examples per class, and the metric should be robust to that
  (e.g., mean of last-K Sharpe rather than single-period return).
- **Anthropic-specific features** (xhigh effort, task budgets) are
  harder to control through DSPy — initial migration may give up
  some Opus 4.7 niceties for portability.

## What we're NOT doing yet

- No DSPy import in production code. The framework adds startup time
  and pulls heavy deps (litellm, optuna, joblib). Wait until at least
  one signature has a measurably better compiled prompt.
- No Phase A code in this PR. This document is the plan; the work
  belongs in a dedicated branch named `feat/dspy-judge`.

## Success criterion

Compiled Judge prompt scores **>5% absolute** improvement on the
agreement metric vs the hand-tuned baseline, on a 50-example holdout.
Below that threshold, the compile cost isn't justified and we
keep the hand-tuned prompts.

---

## Cross-references

- Provider abstraction: [`llm/provider.py`](../llm/provider.py)
- Token budget enforcer: [`engine/token_budget.py`](../engine/token_budget.py)
- Context compressor: [`engine/context_compressor.py`](../engine/context_compressor.py)
- Prompt sites enumerated above live mostly in [`llm/`](../llm/) — `grep -rn "logged_create" llm/`
