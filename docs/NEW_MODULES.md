# New Modules — Phase 7 & Phase 8

Catalog of modules added during the Apr 2026 signal-fusion expansion.
See `CHANGELOG.md` (2026-04-24) and `FURTHER_UPDATES.md` (Phases 7-8)
for context and shipping notes.

Every module below follows the same conventions:

- **Pure core, thin integration**: the module itself has no network side
  effects except in its one documented fetch function.
- **Graceful degradation**: network failures return an empty/"unavailable"
  result so the caller can continue; exceptions never bubble past the skill.
- **Opt-in wiring**: features that ingest external APIs (PostHog,
  Langfuse, Reddit/X, Polymarket, RSS) activate only when the relevant
  env var / flag is set.
- **≥80% test coverage**: every module ships with `tests/test_<module>.py`.

---

## Signal Sources (added to `engine/signal_fusion.py`)

The fusion engine now aggregates **8 sources**. Each source returns
`{available, score, ...}`; the fuser normalizes weights across available
sources at call time.

### 1. Social Sentiment — `skills/social_sentiment.py`
**What:** Fetches recent Reddit posts (wallstreetbets / stocks / investing)
via the public JSON API. Optional X/Twitter path via tweepy.
Engagement-weighted compound score via the existing FinBERT/VADER pipeline.

**Enable X/Twitter:**
```bash
export TWITTER_BEARER_TOKEN=...
```
Reddit requires no auth.

**API:**
```python
from skills.social_sentiment import analyze_social_sentiment
r = analyze_social_sentiment("NVDA")
# {available, score, n_posts, bullish, bearish, engagement, reddit, x}
```

### 2. Earnings / PEAD — `engine/earnings.py`
**What:** Calendar of upcoming earnings (60-day horizon) + historical
post-earnings 5-day drift, positive rate, and surprise↔drift correlation.
Proximity amplifier (≤3d: 1.3×, ≤7d: 1.1×, ≤14d: 1.0×, ≤30d: 0.7×).

**API:**
```python
from engine.earnings import get_earnings_signal
r = get_earnings_signal("NVDA")
# {ticker, next_date, days_until, eps_estimate, pead: {...}, narrative}
```

### 3. Prediction Markets — `skills/prediction_markets.py`
**What:** Polymarket Gamma API search, filtered to active open markets
with future endDate. Volume-weighted deviation of "Yes" price from 0.5,
sign inferred from question text keywords.

**API:**
```python
from skills.prediction_markets import analyze_prediction_markets
r = analyze_prediction_markets("NVDA")
# {available, score, n_markets, n_directional, total_volume_24hr, markets}
```

No auth required.

---

## Decision Pipeline

### 4. Portfolio Manager — `engine/portfolio_manager.py`
Inspired by TauricResearch/TradingAgents (Apache-2.0). Final-layer
approval between decision generation and execution.

**Rules (all overridable via `rules=` dict):**
- `min_confidence`: 40
- `max_single_position_pct`: 20%
- `max_sector_concentration`: 40%
- `max_same_direction_streak`: 5
- `max_position_pct`: 15% (per-trade cap)

**API:**
```python
from engine.portfolio_manager import Position, approve_decision
verdict = approve_decision(
    ticker="NVDA",
    decision={"decision": "BUY", "confidence": 75, "signal_strength": 60},
    portfolio=[Position("NVDA", 2_500, sector="Tech")],
    portfolio_value=10_000,
    recent_decisions=[{"decision": "BUY"}] * 3,
)
# {approved, scaled_position_pct, reason, warnings, checks}
```

Wired into `core.brain.OrallexaBrain.run_for_mode` as an opt-in final
gate (activated when `portfolio=` is passed). The verdict is mirrored
to `DecisionOutput.extra["portfolio_manager"]` and surfaced by the
`/api/deep-analysis` response.

### 5. Regime Strategist — `engine/regime_strategist.py`
Inspired by AgentQuant. Maps detected market regime to a tailored
strategy + tuned params.

**Recipes:**
- `trending`  → `trend_momentum` (RSI 40-75, ADX≥22, TP 10%)
- `ranging`   → `rsi_reversal`   (RSI 30-70, SL 3%, TP 5%)
- `volatile`  → `dual_thrust`    (k=0.7 both sides, SL 6%)

Feature-aware tweaks: ADX > 35 widens take-profit; ATR/Close > 4%
widens stop-loss.

Optional `use_llm=True` path accepts an injected `llm_fn`; output is
strictly validated (known strategy + numeric param bounds) before use.

**API:**
```python
from core.brain import OrallexaBrain
brain = OrallexaBrain("NVDA")
r = brain.get_regime_strategy()
# {regime, strategy, params, reasoning, source}
```

Exposed as `GET /api/regime/{ticker}`.

---

## Memory

### 6. Layered Memory — `engine/layered_memory.py`
FinMem-inspired tiered prediction store. Records bucket by recency:

| Tier | Age range | Cap |
|------|-----------|-----|
| `short_term` | 0-7 days | 100 records |
| `mid_term`   | 7-30 days | 200 |
| `long_term`  | 30+ days | 500 |

Why: accuracy isn't uniform across time scales. A role might hit 45% on
short-term calls but 72% on long-term. Pooling hides the signal.

**API:**
```python
from engine.layered_memory import LayeredMemory
lm = LayeredMemory()
lm.record("Conservative Analyst", "NVDA", "BULLISH", score=30, conviction=70)
lm.update_outcome("Conservative Analyst", "NVDA", forward_return=0.05)
ctx = lm.get_tiered_context("Conservative Analyst", "NVDA")
narr = lm.narrative("Conservative Analyst", "NVDA")
```

Wired into `llm/perspective_panel.run_perspective_panel`: tier
narratives are injected into per-role prompts, and predictions are
mirrored to the layered store. Exposed as
`GET /api/layered-memory/{role}/{ticker}`.

---

## Data / News

### 7. News Aggregator — `engine/news_aggregator.py`
TrendRadar-inspired multi-platform news ingest. Google News RSS +
Yahoo Finance RSS, parsed via stdlib `xml.etree` (no new dep), deduped
by fuzzy title prefix/containment. On collision, keeps the
higher-ranked provider (Reuters/Bloomberg/WSJ > CNBC/MarketWatch >
Yahoo/Benzinga).

**API:**
```python
from engine.news_aggregator import fetch_aggregated_news
items = fetch_aggregated_news("NVDA", limit=10)
```

**Enable in daily_intel:**
```bash
export DAILY_INTEL_USE_RSS=1
```
Default is off — the existing yfinance path continues to run alone.

---

## Observability

### 8. PostHog LLM Analytics — `llm/call_logger._send_to_posthog`
Every `logged_create()` call mirrors as `$ai_generation` event with
model, tier, latency, tokens, cost, ticker, error, trace_id.

**Enable:**
```bash
export POSTHOG_API_KEY=phc_...
export POSTHOG_HOST=https://eu.i.posthog.com   # optional; default us.i.posthog.com
```

### 9. Langfuse Dual-Write — `llm/call_logger._send_to_langfuse`
Parallel export as `generation-create` batch event to
`/api/public/ingestion`. Complements PostHog with prompt versioning,
evals, and datasets.

**Enable:**
```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://self-hosted.example.com   # optional
```

---

## UI

### 10. `EarningsWatchPanel` — `orallexa-ui/app/components/daily-intel.tsx`
Art Deco card rendering `DailyIntelData.earnings_watchlist`. Proximity
badge (≤3d ruby / ≤7d gold), PEAD drift, win rate, click-through to
ticker detail. Bilingual EN/ZH.

### 11. `RegimeCard` — `orallexa-ui/app/components/regime-card.tsx`
Shows current regime + proposed strategy + parameter pills + reasoning.
Auto-fetched after `/api/deep-analysis-stream` completes (non-blocking).

---

## E2E Smoke Test

`scripts/demo_pipeline_e2e.py` exercises the full pipeline
(`fuse_signals → decision → portfolio_manager`) on real market data
with a mock portfolio. Useful as a PR demo artifact and for spotting
regressions in any of the 8 sources.

```bash
python scripts/demo_pipeline_e2e.py NVDA TSLA AMD
```
