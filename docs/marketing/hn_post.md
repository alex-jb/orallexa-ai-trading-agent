# Hacker News launch post — Orallexa

HN's two unwritten rules: **no marketing speak, lead with substance,
let the work speak**. Title is half the battle. Body should be 2-4
short paragraphs explaining the technical bit that's actually new.

---

## Title options (rank by likely CTR)

**A. "Show HN: Open-source AI trading agent — 8-source signal fusion with adaptive weights"**

**B. "Show HN: Bull/Bear LLM debate before every trade decision (open source)"**

**C. "Show HN: I built a multi-agent trading system that uses Polymarket + Kalshi as alpha"**

**D. "Show HN: Orallexa — self-tuning multi-agent trading agent on Claude Opus 4.7"**

Recommended: **A**. "Show HN" + concrete claim + open-source = highest
HN signal. Avoid "AI trading bot" (too generic, attracts skeptics).

---

## Body — 250-400 words

I've been working on an open-source trading research agent for the past
couple weeks. The architecture worth talking about isn't the LLM debate
(everyone has one now) — it's the **adaptive signal fusion**.

The system pulls 8 independent signal sources for each ticker:

- Technical indicators
- ML model ensemble (10 models including Kronos, the new foundation model
  pretrained on 45+ global exchanges)
- News sentiment (FinBERT + VADER fallback)
- Options flow (put/call, unusual activity, max pain)
- Institutional data (insider transactions, short %)
- Social sentiment (Reddit search API + optional X)
- Earnings calendar + PEAD drift
- Prediction markets (Polymarket + Kalshi merged)

Each source produces a -100..+100 directional score. They fuse with
weighted voting. The interesting part: weights aren't static. There's
a JSONL ledger that records every prediction at decision time, then a
nightly cron pulls forward returns from yfinance and fills in per-source
hit/miss. Sources with rolling accuracy ≥0.70 get a 2× weight multiplier;
sources at ≤0.30 get muted to 0.10×. Renormalized so total weight is
preserved.

Above that sits a Bull/Bear/Judge debate (Claude Opus 4.7 with xhigh effort
on the Judge — the most expensive reasoning hop — and Sonnet for the
adversarial Bull and Bear). Then a Portfolio Manager gate that blocks
trades before they hit Alpaca: max single-position concentration, sector
exposure, direction-streak warnings, conviction-scaled position sizing.

The honest result that might surprise: a synthetic backtest of the 8-source
weights vs the original 5-source legacy weights showed the legacy actually
edges out under low-SNR assumptions for the new sources. Real-world SNR is
unknown — and that's exactly why I built the dynamic weighting layer. If
social sentiment really does have low signal, the system will down-weight
it automatically once enough records accumulate.

Code is MIT. Backend is Python (FastAPI), frontend is Next.js 16 (Art Deco
theme, bilingual EN/ZH). ~800 backend tests, 245 frontend, 83% scoped
coverage, full CI.

**Repo:** https://github.com/alex-jb/orallexa-ai-trading-agent
**Live demo:** https://orallexa-ui.vercel.app (no API key needed)
**Architecture deep-dive:** `docs/NEW_MODULES.md` in the repo

Happy to answer questions about the dynamic weights math, the Polymarket
integration, why I picked Kronos over a custom transformer, or anything
else.

---

## When to post

Tuesday or Wednesday, 8-10am Pacific. Avoid Mondays (high volume),
Fridays (low engagement), weekends (different audience).

If front-paged, expect:
- 100-500 stars in 24h
- 20-50 issues / questions
- 2-5 PR offers (mostly small fixes)

Be prepared to answer for 6+ hours straight in the comments. HN comments
make or break the outcome — quick, technical, no fluff.

## Comment-section preparation

Anticipated tough questions + drafted answers:

**Q: Has this beaten buy-and-hold on real money?**
> No, and I won't claim it has. The synthetic backtest in
> `scripts/backtest_fusion_partial.py` showed mixed results vs the legacy
> weights (honest finding noted in the commit message). The dynamic
> weights are designed to converge on whichever sources actually carry
> alpha for a given ticker/regime — but that needs accumulated forward-
> return data we're still collecting.

**Q: Why so many sources?**
> Diminishing returns at some point, agreed. Each source had to justify
> its addition. Polymarket got in because prediction markets reflect smart-
> money probability estimates that are independent of price. Kronos got
> in because it's pretrained on K-line data from 45 exchanges — different
> training distribution than RF/XGB. The dynamic weighting makes
> "too many sources" a self-correcting problem.

**Q: How is this different from TradingAgents (TauricResearch)?**
> Borrowed their Portfolio Manager pattern (acknowledged in commit
> messages and FURTHER_UPDATES.md). Different in: (1) signal fusion is
> 8 sources not just analyst voices, (2) prediction markets included,
> (3) dynamic weights from accuracy ledger, (4) PM gates actual Alpaca
> orders not just advisory.

**Q: What's the LLM cost per analysis?**
> Per `/api/deep-analysis` call: ~$0.05-0.15 depending on context size
> and whether Opus 4.7 (Judge) fires. TokenBudget enforcer caps callers.
> Watch for OpusOpus 4.7's 35% tokenizer inflation — flagged in the
> PRICING constant.

**Q: License?**
> MIT. Use it, fork it, build on it. PRs welcome.
