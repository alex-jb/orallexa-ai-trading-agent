# X (Twitter) launch thread — Orallexa

Style: **builder voice, concrete numbers, no buzzwords, no emojis at the
start of every line**. Each tweet ≤280 chars. Designed to hook on the
specific (Bull/Bear debate + 8-source fusion + Polymarket+Kalshi)
rather than "AI trading agent".

Pin tweet 1 with the demo link + the "what's unique" claim.

---

## Thread A — primary launch (8 tweets)

**1/** I built an open-source AI trading agent where every decision
goes through a Bull/Bear/Judge debate before it executes.

8 signal sources fuse into one conviction score. Polymarket + Kalshi
prediction markets count as a vote alongside ML models.

https://github.com/alex-jb/orallexa-ai-trading-agent

**2/** The 8 sources:
- Technical (RSI, MACD, ADX, MA cross)
- ML ensemble (10 models incl. Kronos foundation model — pretrained on
  45+ exchanges)
- News sentiment (FinBERT + VADER)
- Options flow (P/C ratio, unusual activity)
- Institutional (insider txns, short %)
- Social (Reddit + optional X)
- Earnings/PEAD drift
- Prediction markets (Polymarket + Kalshi)

**3/** Each source's weight isn't static. There's an accuracy ledger
that scores every prediction against the eventual N-day return,
then dynamically scales weights:
- 0.50 accuracy → 1.0× (random)
- 0.70 → 2.0×
- 0.30 → 0.10× (mute)

Sources that earn their seat amplify. Ones that don't get muted.

**4/** Decisions go through a Portfolio Manager gate before any
Alpaca order:
- Min confidence
- Max single-position concentration (20%)
- Max sector exposure (40%)
- Direction-streak warnings
- Conviction-scaled position sizing

Rejections return HTTP 409. Real risk control, not advisory.

**5/** Bull/Bear/Judge runs on Claude Sonnet 4.6 by default. The
Judge — most expensive reasoning hop — upgrades to Claude Opus 4.7
with xhigh effort. Token budgets short-circuit the chain when caps hit.

DSPy Phase A scaffold ready when we have 100+ eval records.

**6/** Multi-provider abstraction baked in. Anthropic default;
OpenAI + Gemini are real adapters; Ollama + Grok scaffolded.

Switch with `ORALEXXA_LLM_PROVIDER=openai`. Same pricing table, same
JSONL log + PostHog + Langfuse triple sink.

**7/** ~800 backend tests + 245 frontend tests. Coverage gate at 70%
on core logic (actual: 83.4%). CI green. ~50 commits this week
landing the 8-source fusion + adaptive weights + Opus 4.7 routing
+ Kalshi merge + DyTopo dynamic role selection.

**8/** Live demo: https://orallexa-ui.vercel.app (no API key needed,
demo mode)

Code: https://github.com/alex-jb/orallexa-ai-trading-agent
MIT license. Issues + PRs open.

If you build trading agents, the architecture in `engine/signal_fusion.py`
is worth a read.

---

## Thread B — alt opening focused on prediction markets

**1/** Prediction markets are the most under-used alpha source for
trading agents.

Polymarket says NVDA has a 12% chance to hit $200 by Friday. That's
not noise — it's smart money's actual probability estimate. Treat
it as a vote alongside RSI and earnings drift.

I built this. Open source.

**2/** github.com/alex-jb/orallexa-ai-trading-agent

8-source signal fusion. Polymarket + Kalshi merged into one
"prediction markets" vote. Bullish/bearish sign inferred from
question text keywords (volume-weighted on collision).

Then Bull/Bear/Judge debate on Claude Opus 4.7.

[continue with 3-7 from Thread A]

---

## Single tweet — for replies / retweets

The one-line pitch:

> Open-source AI trading agent: Bull and Bear debate every decision,
> 8 sources vote (Polymarket + 10 ML models incl. Kronos),
> dynamic weights adapt to accuracy, Portfolio Manager gates orders
> before they hit Alpaca. ~50 commits this week.
> https://github.com/alex-jb/orallexa-ai-trading-agent

---

## Builder-bait (catches eng audience)

> Wrote a CORAL-inspired SharedMemory aggregator over per-role +
> tiered memory. The cross-role consensus injection ('Other roles
> on NVDA: 8 BULLISH / 2 BEARISH; Aggressive 75% acc') made the
> Bull/Bear arguments measurably more grounded.
>
> github.com/alex-jb/orallexa-ai-trading-agent
> engine/shared_memory.py

> DyTopo dynamic topology routing in our 4-role perspective panel:
> trending markets → Aggressive + Quant only.
> Ranging → Conservative + Quant.
> Volatile → all 4 (uncertainty deserves diversity).
>
> ~50% LLM call reduction on routine analysis. Code in llm/perspective_panel.py

---

## When to post

- **Best slots**: Tue-Thu 9-11am PT (US dev audience)
- Pin Thread A as profile pin
- Reply to your own thread 24h later with: "Update: X new stars, Y issues
  opened. Next: [specific feature]"
- Quote-tweet anyone discussing TradingAgents, FinMem, AgentQuant —
  position as "we ship this" not "competing"

## Hashtags (use sparingly — max 2)

`#opensource #ai` — broad reach, low spam signal
`#fintech` — if specifically courting finance audience
`#claude` `#anthropic` — Claude community amplification

Avoid: #cryptocurrency #stockmarket — attracts spam reply guys
