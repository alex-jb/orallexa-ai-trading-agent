# Orallexa — 30-day Unblock Plan

> Concrete operational steps to clear the two infrastructure gates
> currently choking traction. Both gates exist because **production
> data hasn't accumulated** — not because code is missing.

---

## Gate 1: Alpaca paper trading pilot (`memory_data/decision_log.json`)

**Status:** `bot/alpaca_executor.py` is done. `memory_data/` is empty —
zero production decisions logged. The whole self-improvement loop
(DSPy Phase B + multi-modal lift gate + adaptive weights with real
sample size) is downstream of this dataset existing.

**5-step setup (one-time, ~15 min):**

```bash
# 1. Alpaca paper account (free)
open https://app.alpaca.markets/signup
# Generate keys: dashboard → API Keys → Paper Trading → Generate

# 2. Add to .env (gitignored)
cat >> .env <<'EOF'
ALPACA_API_KEY=PK_PASTE_HERE
ALPACA_SECRET_KEY=PASTE_SECRET_HERE
EOF

# 3. Verify connection
python -c "from bot.alpaca_executor import AlpacaExecutor; e = AlpacaExecutor(); print(e.get_account())"
# Expected: { equity: 100000.00, ... } — paper account starts at $100k

# 4. Smoke-trade NVDA
python -c "
from bot.alpaca_executor import AlpacaExecutor
from core.brain import OrallexaBrain
brain = OrallexaBrain()
decision = brain.run_prediction('NVDA')
result = AlpacaExecutor().execute_signal(decision, ticker='NVDA')
print(result)
"

# 5. Wire daily cron — copy this launchd plist
```

**Daily auto-execute cron** (`~/Library/LaunchAgents/com.alexji.orallexa-paper-daily.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.alexji.orallexa-paper-daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>-c</string>
        <string>cd $HOME/Desktop/orallexa-ai-trading-agent && source .env && python scripts/run_daily_pilot.py 2>&amp;1 | tee -a logs/pilot.log</string>
    </array>
    <!-- 9:35 AM ET = market open + 5min, in PT this is 6:35 (no DST) or 7:35 -->
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>35</integer></dict>
    <key>StandardOutPath</key><string>/Users/alexji/Desktop/orallexa-ai-trading-agent/logs/pilot.stdout.log</string>
    <key>StandardErrorPath</key><string>/Users/alexji/Desktop/orallexa-ai-trading-agent/logs/pilot.stderr.log</string>
</dict>
</plist>
```

**Watchlist for the pilot** (file: `scripts/run_daily_pilot.py`, write this):
- 7 tickers: NVDA, AAPL, TSLA, GOOG, META, INTC (the STRONG-PASS ticker), QQQ
- Each gets a `run_prediction(ticker)` deep-analysis
- Decision logged to `memory_data/decision_log.json`
- Paper trade executed iff confidence > 60% AND PortfolioManagerGate passes
- Result appended to `logs/pilot.log`

**Expected accumulation rate:**
- 7 tickers × 1 deep-analysis/day = 7 decisions/day
- 1-2 of those typically clear the 60% confidence gate → paper trade
- Each deep-analysis writes a debate row to `decision_log.json`

After 14 days: ~100 debate rows. **Gate 2 (DSPy Phase B) unblocks.**

**Cost:** ~$0.18 per deep-analysis × 7 × 30 days = **~$38 for the month**.

---

## Gate 2: DSPy Phase B compile (≥100 production debates)

**Status:** Harness done — `scripts/compile_judge_dspy.py` + `scripts/build_dspy_eval_set.py`
both work end-to-end. Synthetic mode validates the pipeline. Real
compile is gated on `decision_log.json` accumulating ≥100 eligible
records (with `extra.debate` populated + ≥5 trading days of forward
return data available).

**14-day path (after Gate 1 cron is running):**

```bash
# Day 14: compile attempt #1
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

**Trigger this monthly via existing cron infrastructure:**

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
