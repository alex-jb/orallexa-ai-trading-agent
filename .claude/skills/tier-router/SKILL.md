---
name: tier-router
description: Route Claude API calls to the right tier — Haiku for structured/fast tasks, Sonnet for reasoning. Use when building any Python app or Claude Code tool that makes multiple Claude API calls and you want to cut cost without losing quality.
---

# Tier Router

A two-tier routing pattern for Claude API calls. Default for 80% of calls is Haiku — fast, cheap, and sufficient for structured work. Escalate to Sonnet only when the task needs real reasoning.

## When to use each tier

**FAST (Haiku) — use by default:**
- JSON extraction / structured output
- Summarization of a paragraph into a sentence
- Parameter generation with constraints
- Classification (sentiment, category, intent)
- Turning freeform text into a known schema
- "Which of these is X" single-choice selection

**DEEP (Sonnet) — use only when:**
- The task requires chains of reasoning over multiple facts
- The output quality is user-facing and visibly matters (final report, strategy critique)
- The decision has downstream cost if wrong (trade signal, architectural choice)
- The input requires synthesizing information the model must weigh and trade off

When in doubt, start with FAST and only escalate if the output is visibly worse.

## Cost math

| Model | $/1M input | $/1M output | Relative cost |
|---|---|---|---|
| Haiku 4.5 | $0.80 | $4.00 | 1x |
| Sonnet 4.6 | $3.00 | $15.00 | ~3.75x |

Typical Claude Code session: ~80% structured tasks + ~20% reasoning.
- All-Sonnet cost: `1.0 * $3.75 = $3.75 units`
- Tiered cost: `0.8 * $1 + 0.2 * $3.75 = $1.55 units`
- **Savings: ~59%** with no quality loss on the fast tier.

Real usage (orallexa trading agent) saw ~10x reduction because many calls are pure JSON parsing where Haiku is indistinguishable from Sonnet.

## Install

```bash
pip install claude-tier-router
```

## Usage

```python
from anthropic import Anthropic
from tier_router import TierRouter

router = TierRouter(Anthropic())

# Structured -> Haiku
resp = router.fast(messages=[{"role": "user", "content": "Extract ticker as JSON: ..."}])

# Reasoning -> Sonnet
resp = router.deep(messages=[{"role": "user", "content": "Critique this strategy: ..."}])

# Inspect cost
print(router.cost_breakdown())
# {'fast_calls': 3, 'deep_calls': 1, 'fast_cost_usd': 0.002, ...}
```

## Anti-patterns

- **Don't** use DEEP for JSON extraction — Haiku handles schemas reliably and costs 4x less.
- **Don't** use FAST for open-ended critique or strategy review — Haiku produces vague output.
- **Don't** hardcode model strings across your codebase. Import `FAST_MODEL` / `DEEP_MODEL` from `tier_router` so model upgrades land in one place.
