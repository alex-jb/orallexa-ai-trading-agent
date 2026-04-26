# Orallexa — Further Updates Roadmap

> Reference document for future upgrades. Inspired by MiroFish multi-agent simulation architecture and other research.

---

## Phase 1: Role-Based Multi-Perspective Analysis ✅ DONE

**Status:** Implemented in `llm/perspective_panel.py`

4 distinct market personas analyze each ticker in parallel:

| Role | Focus | Risk Profile |
|------|-------|-------------|
| Conservative Analyst | Capital preservation, support levels, R/R ratio | Low risk |
| Aggressive Trader | Momentum, breakouts, volume, 1-5 day horizon | High risk |
| Macro Strategist | Sector rotation, rates, geopolitics, regime | Medium risk |
| Quant Researcher | Model consensus, statistical edge, signal alignment | Data-driven |

- Consensus aggregation: conviction-weighted scoring (-100 to +100)
- Agreement metric: how much roles align (0-100%)
- Panel feeds into Risk Manager and Judge for richer decisions
- Runs in parallel with Bull/Bear debate (no added latency)
- Cost: ~4 FAST_MODEL calls (~$0.002)

---

## Phase 2: What-If Scenario Simulation ✅ DONE

**Status:** Implemented
**Inspired by:** MiroFish dynamic variable injection ("God's eye view")

### Concept
Users input hypothetical scenarios ("Fed raises rates 50bp", "NVDA misses earnings by 10%", "China bans AI chip exports"), and the system simulates the impact on their holdings.

### Implementation Plan

1. **New module:** `engine/scenario_sim.py`
   - Input: scenario description (text) + current portfolio/watchlist
   - Use Claude to decompose scenario into market effects:
     - Direct impact (which sectors/tickers affected)
     - Second-order effects (supply chain, competitors)
     - Historical analogy (similar past events and outcomes)
   - Output: per-ticker impact score, portfolio-level risk delta

2. **API endpoint:** `POST /api/scenario`
   ```json
   {
     "scenario": "Fed raises rates by 50bp unexpectedly",
     "tickers": ["NVDA", "AAPL", "TLT", "GLD"]
   }
   ```
   Response:
   ```json
   {
     "scenario": "...",
     "impacts": [
       {"ticker": "NVDA", "impact": -3.2, "reasoning": "..."},
       {"ticker": "TLT", "impact": -5.1, "reasoning": "..."},
       {"ticker": "GLD", "impact": +2.8, "reasoning": "..."}
     ],
     "portfolio_delta": -2.1,
     "historical_analog": "Dec 2018 surprise hike: S&P fell 7% over 2 weeks",
     "hedging_suggestions": ["Increase GLD allocation", "Add TLT puts"]
   }
   ```

3. **Frontend:** scenario input card in daily intel page
   - Text input with preset templates (rate hike, earnings miss, geopolitical event)
   - Impact visualization: bar chart of per-ticker effects
   - "Run again with different assumption" loop

### Technical Notes
- 1-2 Claude calls per scenario (decompose + analyze)
- Cache common scenarios (rate decisions, CPI surprise, etc.)
- No need for full OASIS-style agent simulation — Claude's reasoning is sufficient for our scale

---

## Phase 3: Prediction Bias Self-Correction ✅ DONE

**Status:** Implemented
**Inspired by:** MiroFish persistent memory + belief evolution

### Concept
Track historical predictions vs actual outcomes. Identify systematic biases (e.g., consistently too bullish on tech, underestimates volatility). Feed bias awareness back into the analysis pipeline.

### Implementation Plan

1. **Extend `bot/memory.json`** with prediction tracking:
   ```json
   {
     "predictions": [
       {
         "date": "2026-04-01",
         "ticker": "NVDA",
         "predicted": "BUY",
         "confidence": 72,
         "actual_return_5d": -3.2,
         "was_correct": false
       }
     ],
     "bias_profile": {
       "overall_accuracy": 0.58,
       "bull_accuracy": 0.52,
       "bear_accuracy": 0.67,
       "sector_biases": {"tech": +12, "energy": -5},
       "confidence_calibration": "overconfident by ~15%"
     }
   }
   ```

2. **New module:** `engine/bias_tracker.py`
   - Auto-check predictions after 5 trading days
   - Calculate rolling accuracy by direction, sector, confidence level
   - Detect patterns: "model is 20% too bullish on tech stocks above RSI 65"

3. **Feed into analysis pipeline:**
   - Add bias context to Judge prompt: "Historical note: your BUY calls on tech at RSI>65 have 42% accuracy (below average)"
   - Auto-adjust confidence: if model is consistently overconfident, scale down
   - Weekly bias report in daily intel

### Data Requirements
- Need 30+ predictions to detect meaningful patterns
- Use `engine/decision_log.py` (already logging decisions) as data source
- Compare against actual 5-day returns from yfinance

---

## Phase 4: Agent Memory & Personality Evolution ✅ DONE

**Status:** Implemented
**Inspired by:** MiroFish Zep Cloud memory + social dynamics

### Concept
Each perspective panel role develops persistent "memory" — remembering what worked and what didn't for each stock/sector. Over time, the Conservative Analyst becomes more cautious on stocks that burned it before; the Aggressive Trader learns which breakout patterns work.

### Implementation Ideas
- Store per-role prediction history in `memory_data/role_memory.json`
- Before each analysis, inject role-specific history: "Last 3 times you analyzed NVDA at similar RSI, you said X and the result was Y"
- Allow roles to update their confidence calibration based on track record
- Meta-analysis: which role is most accurate for which stock/condition?

### Why Later
- Needs Phase 3 (bias tracking) as foundation
- Value compounds over time (useless with <50 predictions)
- More complex prompt engineering for memory injection

---

## Phase 5: Multi-Source Signal Fusion ✅ DONE

**Status:** Implemented
**Inspired by:** MiroFish GraphRAG knowledge grounding

### Concept
Fuse signals from heterogeneous sources into a unified conviction score:

| Source | Current | Upgrade |
|--------|---------|---------|
| Technical indicators | ✅ 8 indicators | Add order flow, dark pool signals |
| News sentiment | ✅ VADER/FinBERT | Add social media (X/Reddit), earnings call NLP |
| ML models | ✅ 9 models | Add ensemble meta-learner that weights models dynamically |
| Options flow | ❌ | Unusual options activity, put/call ratio, max pain |
| Institutional data | ❌ | 13F filings, insider transactions, fund flows |

### Implementation
- New skill: `skills/options_flow.py` — scrape or API for unusual options
- New skill: `skills/institutional.py` — SEC EDGAR 13F + insider buys/sells
- Meta-learner in `engine/signal_fusion.py` — dynamic Bayesian weighting of all sources
- Each source gets a reliability score based on recent accuracy

---

## Phase 6: Lightweight What-If Agent Swarm ✅ DONE

**Status:** Implemented
**Inspired by:** MiroFish OASIS simulation (simplified)

### Concept
Instead of MiroFish's 1M agent simulation, run a lightweight "mini swarm" of 10-20 agents with simple behavioral rules for scenario testing. No LLM needed — pure rule-based agents.

### Agent Types
- **Momentum traders** (5): buy on breakout, sell on breakdown
- **Mean reversion traders** (5): fade extremes
- **News reactors** (3): amplify or fade news sentiment
- **Institutional** (3): slow, large, trend-following
- **Retail** (4): herding behavior, FOMO/panic

### Simulation
- Inject scenario variable (price shock, news event)
- Run 100 time steps of agent interaction
- Measure: convergence direction, speed, volatility of convergence
- Output: "70% of agents converge on sell within 20 steps → high conviction bear signal"

### Why Later
- Research-grade feature, needs validation
- Value unclear vs. simpler LLM-based scenario analysis (Phase 2)
- Fun to build but may not improve accuracy

---

## Implementation Priority

| Phase | Feature | Priority | Effort | LLM Cost Impact |
|-------|---------|----------|--------|----------------|
| 1 | Perspective Panel | ✅ DONE | — | +$0.002/call |
| 2 | What-If Scenarios | ✅ DONE | — | +$0.005/scenario |
| 3 | Bias Self-Correction | ✅ DONE | — | +$0 (local) |
| 4 | Agent Memory | ✅ DONE | — | +$0.001/call |
| 5 | Multi-Source Fusion | ✅ DONE | — | +$0 (data) |
| 6 | Mini Agent Swarm | ✅ DONE | — | +$0 (local) |

---

## References

- **MiroFish** — https://github.com/666ghj/MiroFish — multi-agent swarm prediction engine (AGPL-3.0)
- **OASIS** — Open Agent Social Interaction Simulations framework
- **OpenSpace** — https://github.com/HKUDS/OpenSpace — self-evolving skill engine
- **GraphRAG** — knowledge graph + RAG for grounding agent beliefs

---

## Phase 7: Follow-up Signal Upgrades ✅ DONE (2026-04-23)

Three upgrades shipped:

**A. Social sentiment (`skills/social_sentiment.py`)**
- Reddit public JSON API (no auth) across wallstreetbets / stocks / investing
- Optional X/Twitter via `TWITTER_BEARER_TOKEN` (tweepy)
- Plugged into `signal_fusion.py` as 6th source with 0.10 default weight
- Engagement-weighted compound score (upvotes + comments boost)

**B. Earnings module (`engine/earnings.py`)**
- Calendar: upcoming earnings dates + EPS estimates (60-day horizon)
- PEAD stats: avg 5-day drift + positive rate + surprise↔drift correlation
- Combined narrative: "NVDA reports in 7 days, PEAD avg +1.8% 5d drift, 71% positive → bullish bias"

**C. PostHog LLM observability (`llm/call_logger.py`)**
- Every `logged_create()` call mirrors to PostHog as `$ai_generation` event
- Tracks: model, tier, latency, tokens, cost, ticker, error, trace_id
- Opt-in via `POSTHOG_API_KEY` env var; `POSTHOG_HOST` override for EU
- Zero overhead when key unset; failures silently swallowed

---

## Phase 8: Trending-Repo Integrations ✅ DONE (2026-04-24)

Three Tier-1 borrowings shipped, each as an independent module:

**A. Polymarket prediction markets (`skills/prediction_markets.py`)**
- Gamma API `public-search` (no auth) → active, open markets per ticker
- Bullish/bearish sign inferred from question text keyword match
- Volume-weighted deviation from 0.5 → conviction score
- Wired as **8th `signal_fusion` source** at default weight 0.06
- Especially valuable for earnings / policy / M&A event-driven tickers

**B. Portfolio Manager gate (`engine/portfolio_manager.py`)**
- Inspired by TauricResearch/TradingAgents (Apache-2.0)
- Final-layer approval between decision engine and execution
- Gates: min confidence, single-ticker concentration ≤20%, sector ≤40%,
  direction streak detection, conviction-scaled position sizing
- Pure module: caller injects portfolio + recent-decision history
- Returns {approved, scaled_position_pct, reason, warnings, checks}

**C. Langfuse LLM observability (`llm/call_logger._send_to_langfuse`)**
- Dual-write alongside PostHog — Langfuse handles prompts/evals/datasets
- Event type: `generation-create` with model, usage, cost, error level,
  metadata (ticker, action, confidence)
- Opt-in via `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY`;
  `LANGFUSE_HOST` overrides for self-hosted / EU cloud

---

## Phase 9: Adaptive Weights, Opus 4.7, Multi-Provider, DSPy Scaffold ✅ DONE (2026-04-25)

The Phase 7/8 fusion is now self-tuning, vendor-portable, and budget-aware.

**A. Adaptive feedback loop**
- `engine/source_accuracy.py` — JSONL ledger records every fuse_signals
  call; `update_outcomes(ticker, forward_return)` fills per-source hit/miss
- `engine/dynamic_weights.py` — accuracy → multiplier (0.30→0.10×, 0.50→1×,
  0.70→2×, 0.90+→3×); preserves total weight via renormalization
- `scripts/update_source_outcomes.py` + GitHub Action cron at 02:00 UTC
- Opt-in: `fuse_signals(use_dynamic_weights=True)`. Default static.

**B. Claude Opus 4.7 selective routing**
- New `OPUS_MODEL = "claude-opus-4-7"` alongside FAST/DEEP. Only
  Judge synthesis + scenario_sim upgrade — Bull/Bear stay on Sonnet
  to keep cost manageable
- `effort="xhigh"` plumbing in `logged_create` with TypeError fallback
  for older SDKs
- $5/$25 pricing + `NEW_TOKENIZER_INFLATION = 1.35` constant for
  budget projections (new tokenizer uses ~35% more tokens)

**C. TokenBudget enforcer (`engine/token_budget.py`)**
- Thread-safe; both token + USD ceilings; `consume(record)` charges any
  logged_create result; `guarded_call(budget, fn)` short-circuits on
  exhaustion
- Wired into `multi_agent_analysis` — debate / panel / risk / report
  steps SKIPPED gracefully when cap hits
- `/api/deep-analysis` form params `token_cap` + `cost_cap_usd`

**D. Multi-provider LLM (`llm/provider.py`)**
- `ChatProvider` Protocol + `AnthropicProvider` (existing path) +
  `OpenAIProvider` (full implementation, lazy `openai` import)
- Effort kwarg portable: xhigh/max → OpenAI `reasoning_effort=high`
- `ORALEXXA_LLM_PROVIDER` env var picks active; default anthropic

**E. Context engineering (`engine/context_compressor.py`)**
- Three modes: extractive / llm / auto (gate at 1500 chars)
- Opt-in `compress_context` on `run_multi_agent_analysis`
- `scripts/eval_context_compression.py` — A/B safety harness; defined
  threshold (≥95% agreement, ≤5pt conf delta) before enabling

**F. DSPy Phase A scaffold (`llm/dspy_judge.py` + `docs/DSPY_MIGRATION.md`)**
- One Signature for Judge, lazy-import dspy, head-to-head compare helper
- No eval set, no compile yet — Phase B/C still pending
- dspy intentionally NOT a project dependency

**G. Bug fixes that mattered**
- Float-rounding accumulation in dynamic_weights tripping CI on Linux
- SignalToast useEffect leaked an 8s timer → JSDOM-teardown crash
- ADX calc had unsatisfiable ternary (`= 0 if False else …`) — symmetric
  zeroing was a no-op, biased ADX upward
- `decision.confidence is None` crashed PM conversion in brain
- Polymarket `_yes_index` fallback returned 0 for non-Yes/No binary
  outcomes, flipping signs on ticker-vs-ticker markets
