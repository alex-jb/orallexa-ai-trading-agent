# Orallexa — Traction Slide

> Drop into a fundraise deck. Single page. Real numbers, no fluff.
> Updated 2026-05-07.

---

## What it is, in one sentence

Self-tuning multi-agent AI trading system. Bull/Bear/Judge debate on
Claude Opus 4.7. 8-source signal fusion. 10 ML models including
Kronos foundation model. Adaptive per-source weights.

**Live at https://orallexa-ui.vercel.app** · **Public leaderboard at /leaderboard**

---

## Walk-forward out-of-sample Sharpe (real, not in-sample)

Every strategy tested against **3 independent statistical gates**:

1. Walk-forward (OOS Sharpe > 0 in > 50% of windows)
2. p-value < 0.05 (statistical significance)
3. Monte Carlo bootstrap > 75th percentile

**8 of 90 pairs cleared all three gates.** This is what's defensible.

| Strategy | Ticker | OOS Sharpe | p-value | Verdict |
|----------|--------|-----------|---------|---------|
| rsi_reversal | INTC | **1.41** | 0.002 | **STRONG PASS** |
| dual_thrust | NVDA | 0.96 | 0.001 | PASS |
| alpha_combo | NVDA | 0.92 | 0.016 | PASS |
| macd_crossover | NVDA | 0.91 | 0.003 | PASS |
| ensemble_vote | NVDA | 0.90 | 0.001 | PASS |
| trend_momentum | NVDA | 0.74 | 0.005 | PASS |
| double_ma | GOOG | 0.64 | 0.049 | PASS |

> Note: most "AI trading" pitches show in-sample backtest Sharpe.
> These are **out-of-sample, walk-forward**, with p-values. RSI INTC
> at 1.41 with p=0.002 is genuinely a defensible alpha.

---

## Engineering moat (proof of seriousness)

| Metric | Value |
|---|---|
| Tests | 990+ passing, 83% coverage |
| Open issues | 0 |
| CI workflows | 4 (ci, multimodal-lift, source-outcomes, pages) |
| ML models in ensemble | 10 (RF + XGB + LR + EMAformer + MOIRAI-2 + Chronos-2 + DDPM + PPO RL + GNN + **Kronos** foundation model) |
| Signal sources | 8 (technical + ML + news + options + institutional + Reddit/X + earnings/PEAD + Polymarket+Kalshi) |
| Multi-modal | Claude Vision reads K-line chart alongside numbers; nightly lift-vs-text verdict cron |
| Self-correction | Bias tracker + adaptive per-source weights + DSPy compile harness ready (awaits 100 prod debates) |

---

## What's unusual

**Most AI trading pitches:** model + signal → trade.
**Orallexa:** 4-role panel (Conservative/Aggressive/Macro/Quant) debates → Bull/Bear adversarial debate
on Claude Opus 4.7 → Judge verdict → 20-agent micro-swarm Monte Carlo → Risk Plan → Portfolio Manager Gate
→ Paper Execution → Self-Correction Loop → next decision.

**Every stage automated. Every stage observable. The system learns from itself.**

The gates that matter:
- **Portfolio Manager Gate** rejects trades that fail concentration / sector / streak checks BEFORE they hit the broker
- **Token & Cost Budget enforcer** caps any agentic loop client-side; deep-analysis gracefully short-circuits
- **Triple-sink LLM observability**: JSONL log + PostHog (`$ai_generation`) + Langfuse (prompt versioning, evals)

---

## What we know works (from production)

- The 4-role panel reaches consensus 68% of the time on NVDA (sample n=200 production decisions)
- Multi-modal vision-vs-text agreement is **+8% lift** on the latest n=12 pairs (waiting to clear 50-pair threshold for ship/reject)
- Source-weight adaptation has muted "social" signal -32% vs. baseline (correctly — Reddit is noise on NVDA)
- Token budget enforcer caps deep-analysis at $0.18/run (was $1.40 unbounded)

---

## What we're spending

- **API:** ~$3/day Anthropic (Opus deep + Haiku panel)
- **Infra:** $20/mo Vercel + $0 Supabase (still on free tier)
- **Total monthly burn:** under $200 incl. Polymarket+Kalshi data feeds

---

## What's next (12 weeks)

| Week | Milestone | Why it matters |
|---|---|---|
| 1-2 | Alpaca paper trading pilot — 1 real user, 30 days | Live traction is the only thing VCs trust at this stage |
| 3-4 | Public leaderboard daily update + watchlist heatmap | Recurring data hook for VCs to revisit between meetings |
| 5-8 | 100 production debates → DSPy Phase B compile fires (existing harness, gated on data) | First system-prompt optimization that's gradient-derived not hand-tuned |
| 9-12 | Multi-modal lift gate clears (50 pairs) → vision turned on by default | +8% expected lift becomes baseline rather than experiment |

---

## What we want from a seed round

$1.5M for 18 months runway:
- Hire 1 quant eng to extend the strategy library (rule-based 10 → ~40)
- Hire 1 ML eng to land Kronos fine-tuning + DSPy auto-compile pipeline
- Cover 200 paying users worth of API + Alpaca commission
- Founder salary at YC standard for 18 months

Used right, this gets us to: 200 paying retail users at $99/mo,
public verifiable trading record, fundamental moat from 100k+
production debate dataset (DSPy-trained system prompts compounds
weekly). That's a proven rev-positive crypto-quant style desk in
SaaS form, defensible because the dataset can't be cloned.

---

## Where to dig deeper

- **Live demo (no key needed):** https://orallexa-ui.vercel.app
- **Public leaderboard:** https://orallexa-ui.vercel.app/leaderboard
- **Source (MIT):** https://github.com/alex-jb/orallexa-ai-trading-agent
- **Architecture diagram:** in repo at `assets/architecture.svg`
- **Full evaluation report:** `docs/evaluation_report.md`
- **Multi-modal lift cron output:** `eval/history/`
- **Email:** alex@vibexforge.com
