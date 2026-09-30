# Orallexa — 30-day Unblock Plan

> Historical unblock plan. The legacy cron does not produce eligible
> debate rows or paper fills. DSPy Phase B requires a separate,
> budgeted, measured debate collection flow before any timeline can
> be estimated.

---

## Gate 1: collect audited paper fills and independently measured debate rows

The older daily pilot is now **technical-decision logging only**. Running
scripts/run_daily_pilot.py or its launchd job fetches daily market data,
records at most seven technical decisions per invocation, and submits **zero
orders** and makes **zero LLM calls**. Its log marks every row as
technical_only:no_debate. The previous estimate of seven production debates a
day and approximately $38 per month was not backed by a reproducible LLM
usage ledger or a measured cost model and is withdrawn. No elapsed time or
paper fill rate is promised.

For the fixed-rule Alpaca PAPER-only signal/order/fill/ledger loop, review the
separate draft PR #15 and its docs/PAPER_HARNESS.md. The default there is a
dry run. Paper submission is an explicit operation. That harness never calls
an LLM, so its *scoped* model cost is $0/week by construction. It does not
create debate rows or unblock DSPy Phase B.

To inspect the legacy technical decision log without any paid LLM or broker
order:

    python scripts/run_daily_pilot.py --tickers NVDA,AAPL --dry-run

The output JSONL contains mode=technical_only_no_debate, debate_rows=0,
orders_submitted=0, llm_calls=0, llm_cost_usd=0. The separate
memory_data/decision_log.json rows are labeled
run_daily_pilot:technical_only:no_debate. Market data can still be fetched
from Yahoo Finance; log writes are local. Do not count these rows toward the
100 eligible **production debate** rows. That gate remains blocked until a
separate, instrumented and budgeted debate flow accumulates qualified rows
and their forward outcomes.

## Gate 2: DSPy Phase B compile (≥100 production debates)

**Status:** Harness done — `scripts/compile_judge_dspy.py` + `scripts/build_dspy_eval_set.py`
both work end-to-end. Synthetic mode validates the pipeline. Real
compile is gated on `decision_log.json` accumulating ≥100 eligible
records (with `extra.debate` populated + ≥5 trading days of forward
return data available).

**Only after 100 eligible measured debate rows and their forward returns exist:**

```bash
# Inspect eligibility before any compile attempt
python scripts/build_dspy_eval_set.py --days 5
# Output: memory_data/dspy_eval_set.jsonl
#         <eligible count> rows ready
# Wait for eligible >= 100 before running compile.

# Once threshold cleared:
pip install dspy-ai  # one-time
python scripts/compile_judge_dspy.py --auto light

# Output: Phase B status: SHIPPED — compiled prompt clears +5% gate
#   OR
# Phase B status: REJECTED — compiled fails gate, baseline stays
```

**Historical workflow proposal (do not schedule paid compilation until its
data and budget gates are implemented):**

Add to `.github/workflows/dspy-compile.yml` (new file):

```yaml
name: DSPy Phase B Compile (monthly)
on:
  schedule: [{cron: "0 4 1 * *"}]  # 1st of month, 04:00 UTC
  workflow_dispatch:
jobs:
  compile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11"}
      - run: pip install -r requirements.txt dspy-ai
      - name: Build eval set
        run: python scripts/build_dspy_eval_set.py --days 5
      - name: Check eligibility
        id: gate
        run: |
          ELIG=$(jq -s 'map(select(.eligible == true)) | length' memory_data/dspy_eval_set.jsonl)
          echo "eligible=$ELIG" >> $GITHUB_OUTPUT
          [ "$ELIG" -ge 100 ] && echo "go=true" >> $GITHUB_OUTPUT || echo "go=false" >> $GITHUB_OUTPUT
      - name: Compile (only if eligible >= 100)
        if: steps.gate.outputs.go == 'true'
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python scripts/compile_judge_dspy.py --auto light
      - uses: actions/upload-artifact@v4
        with:
          name: dspy-compile-output
          path: memory_data/dspy_judge_compiled.json
        if: steps.gate.outputs.go == 'true'
```

---

## Cost budget for the month

| Line | Cost |
|---|---|
| Daily deep-analysis × 7 tickers × 30 days × $0.18 | $38 |
| DSPy compile (one-time, monthly) | $5 |
| Existing infra (Vercel + Anthropic baseline) | $200 |
| **Total** | **$243** |

For **~$50 in marginal cost**, both gates clear in 14-30 days.

---

## After both gates clear

Path is wide open:
- DSPy compiled judge prompt becomes production default (if +5% gate clears)
- Multi-modal vision turned on (50-pair lift gate likely cleared in same window)
- Adaptive source weights have real sample size, no longer noisy
- `decision_log.json` becomes the **moat dataset** — gradient-derived prompts compounded weekly that competitors literally can't replicate without 100+ days of similar production traffic

This is the dataset bet. $50/month for 30 days is a cheap option on a defensible alpha.

---

## Where to push next

After Gate 1 + Gate 2 both clear, the **next-most-valuable** missing piece is
**1 real outside paper trader** — not Alex. Someone willing to point Orallexa
at their watchlist for 30 days and report back. That's the testimonial that
turns a "990 tests + 1.41 OOS Sharpe" deck slide into a "trader-X used this
for 30 days, here's what they thought" slide. Fundraise + warm referral combined.

Distribution drafts for finding that trader are already in
`~/.marketing_agent/queue/pending/20260507T053417Z-orallexa-*.md` —
specifically the **r/algotrading** post. That subreddit has the right
audience (traders curious enough to try a new engine, technical enough
to handle paper-trading setup).
