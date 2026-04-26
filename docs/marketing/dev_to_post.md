---
title: "Building a self-tuning multi-agent trading agent in 50 commits"
published: false
description: How adaptive signal weighting, multi-source fusion, and a Portfolio Manager gate interact in an open-source trading agent built on Claude Opus 4.7
tags: ai, opensource, llm, fintech
canonical_url: https://github.com/alex-jb/orallexa-ai-trading-agent
cover_image: https://orallexa-ui.vercel.app/og-image.png
---

I spent the last two weeks building an open-source multi-agent trading
agent. Not a YouTube-ready bot that beats SPY 12% a year (no claim, no
demo of returns). The interesting bit is the architecture, and that's
what this post is about.

**Repo:** [alex-jb/orallexa-ai-trading-agent](https://github.com/alex-jb/orallexa-ai-trading-agent)
**Live demo:** [orallexa-ui.vercel.app](https://orallexa-ui.vercel.app)
**License:** MIT

## The problem with single-source trading agents

Most LLM trading agents I see do one of:
- Pump price + news into Claude/GPT, ask "BUY/SELL/WAIT"
- Run a single ML model + hardcoded RSI rules
- Multi-agent debate but on the same input data each agent sees

All three pool their conviction into one signal source. If that source
is wrong (or the LLM is in a hallucination mood), the whole stack is
wrong.

## The 8-source fusion idea

Pull eight independent sources for each ticker. Score each in [-100, +100].
Weighted vote. Conviction = Σ score_i × weight_i.

| # | Source | What it captures |
|---|--------|------------------|
| 1 | Technical | RSI, MACD, MA cross, ADX |
| 2 | ML ensemble | 10 models (RF, XGB, EMAformer, Chronos-2, MOIRAI-2, DDPM, GNN, RL-PPO, LR, **Kronos**) |
| 3 | News sentiment | FinBERT (financial-domain BERT) + VADER fallback |
| 4 | Options flow | Put/call ratio, max pain, unusual volume |
| 5 | Institutional | Insider transactions, short % |
| 6 | Social | Reddit (wallstreetbets/stocks/investing) + optional X |
| 7 | Earnings/PEAD | Calendar + post-earnings drift |
| 8 | Prediction markets | Polymarket + Kalshi merged |

Each source is independent in the statistical sense — Polymarket's
estimate isn't derived from RSI, Kronos's forecast doesn't see the
news. They genuinely vote.

## The interesting bit: adaptive weights

Static weights are guesses. We have eight guesses. The system fixes
itself:

```python
# engine/source_accuracy.py
class SourceAccuracy:
    def record_scores(self, ticker, scores): ...
    def update_outcomes(self, ticker, forward_return): ...
    def get_rolling_accuracy(self, window=50): ...
```

Every `fuse_signals()` call appends per-source scores to a JSONL ledger.
A nightly cron pulls forward returns from yfinance and fills in
hit/miss verdicts (sign-of-score == sign-of-return). Rolling accuracy
maps to a multiplier:

```python
# engine/dynamic_weights.py
def _accuracy_factor(accuracy):
    if accuracy <= 0.30: return 0.10  # mute
    if accuracy >= 0.90: return 3.00  # cap
    if accuracy < 0.50:
        return 0.10 + (accuracy - 0.30) * (0.90 / 0.20)
    return 1.00 + (accuracy - 0.50) * (2.00 / 0.40)
```

Then renormalize so the total weight stays 1.0 — keeps the conviction
threshold (±15 for direction labels) comparable across runs.

## The honest finding

A synthetic backtest of the 8-source weights vs the legacy 5-source
weights showed the legacy actually edges out under low-SNR assumptions
for the new sources (`scripts/backtest_fusion_partial.py`):

```
5-src legacy:  Sharpe 0.391  Return  0.08%
8-src Phase 8: Sharpe 0.225  Return  0.04%
```

This isn't a bug — it's exactly why the dynamic weighting layer exists.
If social sentiment really does have low signal in 2026, the system
will down-weight it automatically once enough records accumulate. I
flagged it in the commit message rather than burying it.

## Bull/Bear/Judge debate, then Portfolio Manager gate

Above the fusion sits a 3-call debate:

1. **Bull** (Claude Sonnet 4.6) — argue FOR the trade
2. **Bear** (Sonnet 4.6) — argue AGAINST, with Bull's argument visible
3. **Judge** (Claude Opus 4.7 + xhigh effort) — synthesize

Then a Portfolio Manager that runs BEFORE any Alpaca order:

```python
verdict = approve_decision(
    ticker="NVDA",
    decision={"decision": "BUY", "confidence": 75, "signal_strength": 60},
    portfolio=[Position("NVDA", 2_500, sector="Tech")],
    portfolio_value=10_000,
)
# → {approved: True, scaled_position_pct: 5.6, warnings: ["Sector Tech 35%"]}
```

PM rejection returns HTTP 409 from `/api/alpaca/execute` — order never
hits the broker. PM approval caps the caller's requested position at
the PM-scaled value.

## Multi-provider, multi-platform, multi-everything

- **LLM providers**: Anthropic (default), OpenAI, Gemini all real.
  Ollama + Grok scaffolded. Switch with `ORALEXXA_LLM_PROVIDER=openai`.
- **Prediction markets**: Polymarket + Kalshi merged with platform
  attribution in the response.
- **Observability**: JSONL log + PostHog (`$ai_generation`) + Langfuse
  (`generation-create`). Triple sink, all gated on env vars.
- **Memory**: CORAL-style SharedMemory aggregator over per-role +
  recency-tiered stores. Cross-role consensus injection.
- **Topology**: DyTopo regime-aware role selection. Trending markets
  run 2 of 4 perspectives; volatile markets run all 4.

## Tests + CI

~800 backend tests, 245 frontend tests, 83% scoped coverage with a
`fail_under=70` gate enforced in CI. Linux float arithmetic surfaced
exactly the kind of platform-dependent test fragility you'd expect
on this much code:

```python
# Failed CI:
assert sum(adjusted) == pytest.approx(1.0)
# AssertionError: assert 1.0000010000000001 == 1.0 ± 1.0e-06
```

Cause: `round(v, 6)` per-value before summing accumulated to >1e-6 on
Linux float arithmetic, while Windows happened to round the other
way. Fix: don't round inside the math layer — that's a presentation
concern.

## What I won't claim

- This makes money. I have no live performance data, only synthetic
  backtests and unit tests.
- The 8-source fusion is "better" than 5-source. The honest answer is
  "depends on the SNR of the new sources, which we measure as we go".
- The Bull/Bear debate is novel. It isn't — TauricResearch/TradingAgents
  pioneered this pattern. I borrowed the Portfolio Manager idea from
  them (acknowledged in commit messages).

## What I will claim

The architecture is unusually composable. Every module — signal source,
LLM provider, prediction-market platform, memory store — is swappable
behind a thin interface. You can run it with just Polymarket and
Anthropic, or with all 8 sources and OpenAI as primary. The dynamic
weighting layer means you don't need to manually re-tune when sources
get added or removed.

## Try it

```bash
git clone https://github.com/alex-jb/orallexa-ai-trading-agent
cd orallexa-ai-trading-agent
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
python api_server.py
# in another terminal:
cd orallexa-ui && npm install && npm run dev
```

Or skip setup and use the live demo (no key needed): https://orallexa-ui.vercel.app

PRs welcome. Issues open. Architecture deep-dive in `docs/NEW_MODULES.md`.

If you build trading agents and want to talk shop, the comments are
the right place. I'll respond to anything technical for the next 48h.
