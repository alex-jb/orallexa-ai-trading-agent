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
