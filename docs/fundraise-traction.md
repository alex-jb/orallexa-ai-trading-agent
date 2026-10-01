# Orallexa — Traction Slide

> Historical draft. Performance figures require the pinned data and reproducible
> scripts specified in [the new evaluation protocol](../eval/PROTOCOL.md).
> Updated 2026-05-07.

---

## What it is, in one sentence

Self-tuning multi-agent AI trading system. Bull/Bear/Judge debate on
Claude Opus 4.7. 8-source signal fusion. 10 ML models including
Kronos foundation model. Adaptive per-source weights.

**Live at https://orallexa-ui.vercel.app** · **Public leaderboard at /leaderboard**

---

## Walk-forward evaluation

The earlier eight-row, 90-pair claim has been withdrawn because the 90-pair
OHLCV inputs and full results were not retained. No strategy has a verified
90-pair adjusted significance result yet. See the [full pending status](evaluation_report.md)
and rerun with the predeclared cohort before making a performance claim.

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

## Production evidence pending

The previously quoted panel agreement, multimodal lift, source-weight change,
and per-run cost figures have no retained input log and reproducible script in
this repository. They should not be presented as verified results.

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
| 9-12 | Recheck multi-modal lift after 50 paired observations | Decide whether vision adds measurable value |

---

## What we want from a seed round

$1.5M for 18 months runway:
- Hire 1 quant eng to extend the strategy library (rule-based 10 → ~40)
- Hire 1 ML eng to land Kronos fine-tuning + DSPy auto-compile pipeline
- Cover 200 paying users worth of API + Alpaca commission
- Founder salary at YC standard for 18 months

Used right, this gets us to: 200 paying retail users at $99/mo,
public verifiable trading record, fundamental moat from 100k+
production debate dataset (DSPy-trained system prompts could be evaluated
on that data). Those targets remain projections, not measured outcomes.

---

## Where to dig deeper

- **Live demo (no key needed):** https://orallexa-ui.vercel.app
- **Public leaderboard:** https://orallexa-ui.vercel.app/leaderboard
- **Source (MIT):** https://github.com/alex-jb/orallexa-ai-trading-agent
- **Architecture diagram:** in repo at `assets/architecture.svg`
- **Full evaluation report:** `docs/evaluation_report.md`
- **Multi-modal lift cron output:** `eval/history/`
- **Email:** alex@vibexforge.com
