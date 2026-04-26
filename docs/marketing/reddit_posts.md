# Reddit launch posts — Orallexa

**Hard rule**: each subreddit gets a tailored post. Cross-posting the same
copy gets you removed by mods. Always read 5 recent posts in the sub
before submitting to match tone and avoid auto-removal triggers.

---

## r/algotrading (~270k members)

**Best slot**: Tue-Thu 8-11am ET. Mods strict on self-promo — frame as
discussion, not launch.

### Title

`Open-source signal fusion engine: 8 sources, adaptive weights from accuracy ledger, code & paper-style writeup`

### Body

I've been building an open-source signal fusion engine for the past couple
weeks. Wanted to share the architecture and ask for feedback on the
weighting approach since this sub will spot the holes.

**The setup:**
- 8 independent sources: technical, ML ensemble (10 models incl. Kronos
  foundation model), news sentiment, options flow (P/C, max pain),
  institutional (insider txns + short %), social (Reddit), earnings/PEAD
  drift, prediction markets (Polymarket + Kalshi)
- Each emits a directional score in [-100, +100]
- Weighted vote → final conviction in [-100, +100]
- Bull/Bear/Judge LLM debate refines the call
- Portfolio Manager gate: concentration, sector, sizing, streak

**The interesting bit — adaptive weights:**

JSONL ledger records every fuse_signals call's per-source scores. Nightly
cron pulls forward returns from yfinance, fills in per-source hit/miss
verdicts. Rolling accuracy → multiplier:

```
0.30 → 0.10×  (mute the source)
0.50 → 1.00×  (random — no change)
0.70 → 2.00×
0.90 → 3.00×  (cap)
```

Renormalized so total weight is preserved (conviction scale stays
comparable).

**Honest finding from synthetic backtest** (no historical Polymarket/
Reddit data exists): under low-SNR assumptions for social sentiment,
the legacy 5-source weights actually edge out 8-source. The dynamic
weighting is designed to fix this in real-world data — sources that
don't earn alpha get muted automatically.

**Questions for you:**
1. Is the ±2% return threshold for outcome labelling too narrow on
   small-cap tickers? Considering adaptive threshold from ATR.
2. Would weight scaling per-(source, regime) instead of just per-source
   capture more of the edge? Adds combinatorial complexity but probably
   matches reality better.
3. Anyone tried Kronos in production? Curious about its 5-day forecast
   stability vs Chronos-2 on US equities.

**Code:** github.com/alex-jb/orallexa-ai-trading-agent (MIT)
**Architecture writeup:** `docs/NEW_MODULES.md` in repo

Happy to answer technical questions. Not selling anything, no
subscription, no Discord paywall.

---

## r/quant (~50k members)

**Tone**: more academic, expects citations + math. Avoid the LLM debate
angle (this sub is skeptical of LLM-driven trading).

### Title

`Multi-source signal fusion with rolling per-source accuracy weighting — open source implementation, benchmark vs static weights`

### Body

Sharing an open-source implementation of multi-source signal fusion with
a feedback loop on per-source accuracy. Looking for sanity checks on the
weighting math.

**Setup:**

Eight signal sources s_i ∈ [-100, 100], each producing scores at decision
time t. Weights w_i scale by accuracy a_i ∈ [0, 1] computed from a
rolling window:

    f(a) = clip(map([0.30, 0.50, 0.70, 0.90+] → [0.10, 1.00, 2.00, 3.00]), 0.10, 3.00)
    w'_i = w_i × f(a_i)
    w_i^(adj) = w'_i × Σw_i / Σw'_i    [preserve total weight]

Conviction = Σ s_i × w_i^(adj). Direction labels at ±15 cutoff.

a_i is computed from a JSONL ledger that records (source, ticker, score,
timestamp) at fuse_signals time, then has forward N-day returns filled
in by an offline job. Hit/miss is sign(score) == sign(forward_return)
with a ±2% return threshold for the neutral outcome.

**Sanity checks I'm looking for:**

1. The piecewise-linear factor function — is there a principled reason
   to use Bayesian shrinkage toward 1.0 instead?
2. Renormalization preserves Σw_i exactly. But the per-source distortion
   isn't uniform — high-accuracy sources steal more weight than
   low-accuracy ones lose. Effectively this concentrates conviction
   on a small number of "trusted" sources over time. Is this desirable
   or pathological?
3. Sample-size threshold (min_samples=5) for accuracy reporting — too
   low? At 5 samples you're getting stat power 0.4 ish for detecting
   55% accuracy.

**Code:** github.com/alex-jb/orallexa-ai-trading-agent
**Math is in:** `engine/dynamic_weights.py`

The paper-style writeup is `docs/NEW_MODULES.md`. Test fixtures
in `tests/test_dynamic_weights.py` if you want to play with the
threshold values.

---

## r/MachineLearning (very strict, low promo tolerance)

**Tone**: research-paper. Use [P] flair for project. Skip if you can't
back claims with data.

### Title

`[P] CORAL-style shared persistent memory aggregator for multi-agent LLM debate — open source`

### Body

We have a 4-role perspective panel (Conservative / Aggressive / Macro /
Quant analysts) that produces parallel takes on a stock before a Bull/
Bear/Judge debate synthesizes. Two memory systems:

1. RoleMemory — per-role rolling accuracy + bias profile
2. LayeredMemory — recency tiers (short ≤7d, mid 7-30d, long 30+d)

Replaced the dual call path in the panel runner with a SharedMemory
aggregator (CORAL-paper-inspired, shared persistent memory across agents).
The aggregator returns a multi-line context including:

- This role's accuracy on this ticker
- Per-tier breakdown
- **Cross-role consensus** — "Other roles on NVDA: 8 BULLISH / 2 BEARISH;
  Aggressive: 75% acc"

The cross-role line is what changed downstream behavior most. Without
it, each role generated independently and the Judge had to reconcile.
With it, individual roles already know what siblings concluded recently
and can argue against / build on rather than restating.

Also added DyTopo-style dynamic role selection — pick 2-4 of the 4
roles based on detected market regime. Saves ~50% of LLM calls in
trending/ranging markets without measurable degradation.

**Repo:** github.com/alex-jb/orallexa-ai-trading-agent
**Code:** `engine/shared_memory.py` + `llm/perspective_panel.py`
**License:** MIT

Citations:
- CORAL: arxiv.org/abs/[CORAL paper id]
- DyTopo: arxiv.org/abs/[DyTopo paper id]
(filling in with actual arxiv IDs from VoltAgent/awesome-ai-agent-papers)

---

## r/ClaudeAI (~50k, very growable, low spam pressure)

### Title

`Built an AI trading agent on Claude Opus 4.7 — selective routing keeps cost manageable`

### Body

Sharing how I'm using Opus 4.7 selectively in a multi-agent trading system
without blowing through the budget.

**The setup:**

Bull/Bear/Judge debate. Bull and Bear stay on Sonnet 4.6 (~$0.003 per
debate). Judge — the synthesis hop where reasoning quality matters most —
upgrades to Opus 4.7 with `effort="xhigh"`.

`logged_create()` in `llm/call_logger.py` passes `output_config={"effort":
"xhigh"}` to the SDK with TypeError fallback for older versions. Pricing
table updated for Opus 4.7's $5/$25 per 1M with a NEW_TOKENIZER_INFLATION
= 1.35 constant since the new tokenizer uses ~35% more tokens for the
same fixed text.

**TokenBudget enforcer** caps any agentic loop client-side:
```python
b = TokenBudget(cap_tokens=100_000, cap_usd=0.50)
if b.allow():
    resp, rec = logged_create(...)
    b.consume(rec)
```
Wired into deep-analysis: when budget is exhausted, debate / panel /
risk manager / report steps are SKIPPED gracefully and the response
includes `budget_skipped: ["risk_manager", "deep_market_report"]` so
the caller sees what got dropped.

Triple observability sink: JSONL log + PostHog (`$ai_generation` events)
+ Langfuse (`generation-create` traces). All gated on env vars.

**Repo:** github.com/alex-jb/orallexa-ai-trading-agent
MIT license, ~50 commits this week landing the Opus 4.7 routing,
adaptive signal weights, Polymarket+Kalshi integration, and DSPy
Phase A scaffold.

---

## r/learnpython, r/Python — skip

These subs disallow self-promo of personal projects unless they're
specifically educational. Submit to `r/coolgithubprojects` or
`r/SideProject` instead.
