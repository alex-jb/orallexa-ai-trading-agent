---
name: adversarial-debate
description: Run an Advocate/Critic/Judge debate over any decision with real tradeoffs. Use when the user asks whether to merge a PR, pick an architecture, hire a candidate, ship a feature, or make any judgment where both sides have valid points and a single-model answer would be too confident.
---

# Adversarial Debate

Three-stage debate pattern for high-stakes decisions:

1. **Advocate** (Haiku) — strongest case FOR the proposal
2. **Critic** (Haiku) — strongest case AGAINST, rebutting the advocate
3. **Judge** (Sonnet) — synthesize and return a structured verdict

Cost ~$0.003 per debate. Takes ~10-15 seconds.

## When to use

**Good fits:**
- Should we merge this PR given tests, blast radius, author tenure?
- Postgres vs DynamoDB for this workload?
- Hire or pass after the last round?
- Ship this feature now or wait a week?
- Trading / investment: enter or stay out?
- Any decision with a defensible case on both sides

**Bad fits:**
- Questions with one right answer (use a regular call)
- Pure factual extraction (use a cheap single call)
- Open-ended brainstorming (debate narrows, not expands)
- Low-stakes decisions where $0.003 + 15s isn't worth it

## Usage

```python
from anthropic import Anthropic
from claude_debate import run_debate, DebateConfig

verdict = run_debate(
    proposal="Merge PR #42: adds Redis cache to auth middleware",
    client=Anthropic(),
    context={
        "diff_size": 340,
        "coverage": "85%",
        "author_tenure": "3 weeks",
        "prod_qps": 2400,
    },
    config=DebateConfig(
        decision_options=("APPROVE", "REQUEST_CHANGES", "DEFER"),
        criteria=["correctness", "rollback cost", "perf under load"],
    ),
)

print(verdict.decision)                    # "APPROVE"
print(verdict.confidence)                  # 72.0
print(verdict.reasoning_summary)           # one sentence
print(verdict.strongest_advocate_point)    # what was most convincing for
print(verdict.strongest_critic_point)      # what was most convincing against
```

## Design choices worth knowing

- **Critic sees the advocate's case** — so the critic's points are specific rebuttals, not independent arguments. This is what makes the debate adversarial instead of two parallel monologues.
- **Judge is explicitly asked for its tipping condition** — "what evidence would flip you?" — so the verdict is falsifiable, not just assertive.
- **`decision_options` are bounded** — the judge can't invent a new option. Forces a commit.
- **Confidence is calibrated in the prompt** — 80+ = would bet on it, 50 = genuinely uncertain. Not a vibe.
- **Cost asymmetry matches reasoning asymmetry** — advocate and critic are structured argument generation (Haiku is fine); judge is reasoning over conflicting evidence (Sonnet).

## Anti-patterns

- **Don't run debates on questions where one side is obviously right.** The advocate/critic will manufacture weak arguments and the verdict is noise.
- **Don't skip the `context` dict on non-trivial decisions.** Without facts, both sides speculate and the judge has nothing to weigh.
- **Don't treat the verdict as binding.** It's a structured second opinion — use it to pressure-test your own instinct, not replace it.
