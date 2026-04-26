# Changelog

All notable changes to the Orallexa project will be documented in this file.

## [2026-04-26] — Phase 10: Kronos, Kalshi, DyTopo, CORAL — and the wiring that made them live

The previous session added scaffolding for adaptive weights, multi-provider
LLMs, DSPy, and a token budget. This session built on that foundation by
landing four new external integrations from the latest GitHub trending
sweep, then **actually wiring them into the runtime paths** so they're not
dormant infrastructure.

### Added — External integrations

- **Kronos** (shiyu-coder/Kronos, MIT) — first open-source foundation model
  for financial K-lines, pretrained on 45+ global exchanges. Wrapped in
  `engine/kronos_signal.py` as a 10th ML model candidate. Lazy-imports the
  Kronos package; clear RuntimeError with install hint when missing.
- **Kalshi** prediction markets — `skills/prediction_markets.fetch_kalshi_markets`
  hits `api.elections.kalshi.com/trade-api/v2` (no auth despite the
  'elections' subdomain — Kalshi docs confirm it covers all categories).
  Now merged with Polymarket in `analyze_prediction_markets` for unified
  multi-platform consensus; `n_by_platform` field surfaces breakdown.
- **GeminiProvider** (`llm/provider.py`) — symmetric to OpenAIProvider:
  lazy-imports google-genai, translates Anthropic-style messages to
  Gemini's `{role, parts:[{text}]}` format, maps system role to
  system_instruction, pricing table for gemini-3-{pro,flash,flash-lite}
  + 2.5-pro, thinking_budget heuristic from effort knob.

### Added — Research patterns

- **DyTopo dynamic role selection** — `llm/perspective_panel.select_roles_for_context`
  picks 2-4 of the 4 perspectives based on detected regime:
    trending → Aggressive + Quant; ranging → Conservative + Quant;
    volatile → all 4 (uncertainty deserves diversity); default →
    Conservative + Macro + Quant. Saves ~50% of LLM calls on routine
    analysis. Inspired by 2026 'DyTopo: Dynamic Topology Routing' paper.
- **CORAL shared memory aggregator** (`engine/shared_memory.py`) — read
  aggregator over RoleMemory + LayeredMemory. `summary_for(role, ticker)`
  returns one multi-line context fusing per-role accuracy + tier
  breakdown + cross-role consensus. Inspired by 2026 'CORAL' paper
  showing shared persistent memory beats fixed baselines 3-10×.

### Changed — Wiring

The infrastructure above was ineffectual until plugged in:

- `engine/multi_agent_analysis._add_kronos_to_ml` — appends Kronos's
  forecast as `results["kronos"]` to ml_result before fusion. Silent
  no-op when Kronos isn't installed.
- `engine/signal_fusion._score_ml` — registry now includes "kronos"
  alongside the existing 9 ML voices.
- `llm/perspective_panel.run_perspective_panel` — now consumes
  `SharedMemory.summary_for()` instead of separately calling
  RoleMemory and LayeredMemory. The dual-call path was redundant
  and missed cross-role signal.
- `engine.multi_agent_analysis` — detects current regime via
  `engine.strategies._detect_regime` and passes `dynamic=True,
  regime=...` to `run_perspective_panel`. DyTopo is on by default
  in deep-analysis now; static 4-role mode preserved as opt-out.

### Added — Decision pipeline polish

- **TokenBudget UI badge** (`orallexa-ui/app/components/token-budget-badge.tsx`)
  — surfaces the `token_budget` snapshot from `/api/deep-analysis`
  with a usage bar (token + USD), exhausted pill, and per-skipped-step
  pills. Wired into page.tsx above SignalFusionCard.
- **Watchlist portfolio editor** (`orallexa-ui/app/page.tsx`) —
  collapsible details with `TICKER:value:sector` input + NAV field;
  state persists to localStorage. When non-empty, watchlist-scan
  request includes portfolio_json so PM-preview pills actually populate.
- **Multi-platform UI badges** in `signal-fusion.tsx` — each prediction
  market shows a Polymarket/Kalshi tag (purple/green pills); top of
  the prediction-markets section shows aggregated `n_by_platform`.

### Added — DSPy + backtest scaffolds

- `llm/debate.py` — stash full Bull/Bear/Judge text on
  `decision.extra['debate']` so decision_log captures it. Past records
  don't have it; future deep-analysis calls will.
- `scripts/build_dspy_eval_set.py` — extract candidate records, pull
  yfinance forward returns, label ground_truth via ±2% threshold,
  emit JSONL. Reports the ≥100-eligible Phase B trigger condition.
  `judge_metric()` ready to plug into MIPROv2.
- `engine/historical_cache.py` — file-backed cache schema (parquet for
  prices, JSON for earnings + options snapshots) with a metadata
  freshness ledger. Honest about what's cacheable: prices + earnings
  yes; options point-in-time only; social/polymarket/news no
  (no public historical APIs).
- `scripts/eval_context_compression.py` — new `--from-log` flag pulls
  real (Bull, Bear) pairs from decision_log once accumulated.

### Added — CI

- **Coverage gate** (`.coveragerc` + `--cov-fail-under=70` in
  `.github/workflows/ci.yml`) — scoped to core logic modules
  (PM, dynamic_weights, source_accuracy, token_budget, compressor,
  aggregators, memory, regime, earnings, factor_engine, decision_log,
  strategies, ensemble, evaluation, backtest, micro_swarm, param
  optimizer, eval/{daily, regime, monte_carlo, statistical_tests},
  models/{confidence, decision}). Excludes orchestration / heavy DL /
  live-data paths. Local: 83.4% on the scoped surface.
- **Source-outcomes cron** (`.github/workflows/source-outcomes.yml`) —
  daily at 02:00 UTC, runs `scripts/update_source_outcomes.py` with
  actions/cache for ledger persistence. workflow_dispatch + dry-run
  smoke test always at the end.

### Fixed

- `engine/dynamic_weights` removed premature `round(v, 6)` that
  accumulated to 1.0000010000000001 on Linux float arithmetic, failing
  the `pytest.approx(..., abs=1e-6)` test that passed locally on Windows.
- `orallexa-ui/app/components/signal-toast.tsx` had an 8-second
  setTimeout with no cleanup; late firing after JSDOM teardown showed
  up as `ReferenceError: window is not defined` and failed CI even
  though all 245 assertions passed. Cleanup function added.
- `skills/prediction_markets.fetch_kalshi_markets` initial draft
  accepted bid/ask outside [0, 100] cents as long as the midpoint
  landed in [0, 1]; a malformed payload with bid=-50 / ask=200 would
  pass. Per-leg validation added.

### Tests

- +71 (kronos_signal: 11, shared_memory: 11, kalshi_markets: 9,
  perspective_panel_dytopo: 7, historical_cache: 21, plus token_budget
  and provider extensions)
- 245 UI tests still green
- All ~800 backend tests pass on Linux CI after the float-rounding fix
- Scoped coverage 83.4% (≥70% gate)

### Verification

- E2E: `python scripts/demo_pipeline_e2e.py NVDA TSLA AMD` runs the
  full chain (live data, no mocks) and exits clean
- Multi-platform prediction markets verified with mocked Kalshi
  responses; integration test covers the merged shape end-to-end
- DyTopo: `select_roles_for_context()` returns the right subset for
  each regime; `run_perspective_panel(dynamic=True)` exercised in unit
  tests with 7 specific regime cases
- Coverage gate: `--cov-fail-under=70` enforces locally and in CI

---

## [2026-04-25] — Phase 9: Adaptive Weights, Opus 4.7, Multi-Provider, DSPy Scaffold

21 commits across two days extending the Phase 7/8 fusion work into a
self-tuning, observable, vendor-portable system. None of it adds new
hard dependencies — every adapter and feature is either lazy-imported,
opt-in via env var, or gated behind a runtime flag.

### Added — Adaptive feedback loop

- **`engine/source_accuracy.py`** — append-only JSONL ledger that
  records every fuse_signals call's per-source scores, then has them
  filled in with hit/miss verdicts once a forward window passes.
  Append on read at fusion time, no extra calls.
- **`engine/dynamic_weights.py`** — maps each source's rolling
  accuracy to a multiplier (0.30→0.10×, 0.50→1.00×, 0.70→2.00×,
  0.90+→3.00×) and rebuilds the weights dict so total preservation
  holds. Result of integration: under-performing sources get muted,
  consistent winners get amplified.
- **`scripts/update_source_outcomes.py`** — daily backfill job that
  pulls forward returns from yfinance and calls update_outcomes on
  pending records; exposes `--dry-run` and `--days` knobs.
- **`.github/workflows/source-outcomes.yml`** — scheduled cron at
  02:00 UTC + workflow_dispatch with optional dry-run; uses
  `actions/cache` to persist the ledger across runs since it's
  local state. Production deployments run their own cron.
- `fuse_signals(use_dynamic_weights=True, record_for_accuracy=True)`
  knobs to opt into adaptive weights and ledger writes; default
  remains static + recording so existing callers see the same
  behavior with one extra side effect.

### Added — Claude Opus 4.7 selective routing (released 2026-04-16)

- New `OPUS_MODEL = "claude-opus-4-7"` constant in `llm/claude_client`
  alongside FAST_MODEL (haiku) and DEEP_MODEL (sonnet 4-6). Only the
  highest-value reasoning hops upgrade — Bull/Bear stay on sonnet, but
  Judge synthesis (`llm/debate._call_judge`) and what-if scenario
  simulation (`engine/scenario_sim`) jump to Opus 4.7 + xhigh effort.
- `logged_create(effort=...)` plumbing — passes `output_config={"effort": ...}`
  to the Anthropic SDK with a TypeError fallback for older SDKs that
  don't recognize the kwarg.
- PRICING table updated: claude-opus-4-7 at $5/$25 per 1M, plus a
  `NEW_TOKENIZER_INFLATION = 1.35` constant since the Opus 4.7 tokenizer
  uses ~35% more tokens for the same fixed text.
- `get_tier()` now returns `OPUS` / `DEEP` / `FAST` (was DEEP/FAST).

### Added — Token & cost ceilings

- **`engine/token_budget.py`** — thread-safe TokenBudget with both
  token and USD ceilings. `consume(record)` charges any logged_create
  result; `allow()` checks remaining headroom; `report()` returns a
  full snapshot. `guarded_call(budget, fn, *args)` helper short-circuits
  when exhausted.
- Wired into `engine.multi_agent_analysis.run_multi_agent_analysis` —
  when budget is exhausted, debate / perspective panel / risk manager /
  deep market report are SKIPPED gracefully and the partial pipeline
  finishes with `result.budget_skipped` listing what was dropped.
- `/api/deep-analysis` form params `token_cap` + `cost_cap_usd`
  surface this control to API callers; response gains `token_budget`
  + `budget_skipped` fields.

### Added — Multi-provider LLM abstraction

- **`llm/provider.py`** — `ChatProvider` Protocol + concrete
  `AnthropicProvider` (delegates to existing `logged_create`) and
  `OpenAIProvider` (full implementation: lazy imports `openai` SDK,
  translates response shape to Anthropic-compatible
  `.content[0].text` / `.usage.input_tokens` form, builds
  `LLMCallRecord` so PostHog + Langfuse exporters fire identically).
  Includes 2026 OpenAI pricing table for gpt-5/4.1/o3/o4-mini and
  fallback rates for unknown models.
- Effort kwarg portability: `effort="xhigh"` maps to OpenAI
  `reasoning_effort="high"` on o-series; falls back without when the
  SDK rejects the param.
- `gemini` / `ollama` / `grok` keep `_UnimplementedProvider` sentinels
  so attempts fail loud with an install hint, not silently return
  Anthropic.
- `ORALEXXA_LLM_PROVIDER` env var picks the active provider (default
  `anthropic`, no behavior change for existing deployments).

### Added — Context engineering

- **`engine/context_compressor.py`** — three modes:
    - `extractive`: pure-Python sentence selection (first/last + numbers
      + directional keywords); zero cost, deterministic
    - `llm`: single FAST_MODEL summary call (~$0.0005); falls back to
      original on any error
    - `auto`: extractive < 1500 chars, llm above
- Optional `compress_context` parameter on
  `run_multi_agent_analysis` and `/api/deep-analysis` (default off);
  shrinks market_report / news_report / ml_report before Risk Manager
  consumes them.
- **`scripts/eval_context_compression.py`** — A/B safety harness with
  --offline (mock Judge) and live modes. Documented threshold:
  agreement ≥ 95% AND mean |conf delta| ≤ 5 pts before enabling. The
  offline run on synthetic prompts revealed extractive compression can
  flip 50% of decisions when prompts are keyword-padded — exactly the
  reason it's off by default.

### Added — DSPy Phase A scaffold (no compile yet)

- **`docs/DSPY_MIGRATION.md`** — three-phase plan to migrate the 15+
  hand-tuned prompts to DSPy Signatures with MIPROv2 optimizer. Phase
  A scope kept tight: bootstrap one Signature for Judge, run head-to-
  head, no eval set yet, no compile yet.
- **`llm/dspy_judge.py`** — `JudgeSignature` + `judge_dspy()` predictor
  + `compare_judges()` head-to-head. Lazy-imports `dspy`; raises a
  clear RuntimeError pointing at `pip install dspy-ai>=2.5` when
  missing. dspy is intentionally NOT a project dependency.

### Fixed

- **engine/dynamic_weights.py**: removed premature `round(v, 6)` in the
  per-value normalization step. Linux's float arithmetic accumulated
  to 1.0000010000000001 vs Windows landing on the safe side of the
  1e-6 tolerance — classic platform-dependent test fragility. Internal
  math now stays full-precision; display layers handle rounding.
- **orallexa-ui/app/components/signal-toast.tsx**: 8-second auto-dismiss
  setTimeout had no cleanup. After test teardown the late-firing
  callback poked into a torn-down JSDOM, surfacing as `ReferenceError:
  window is not defined` and failing CI even though all 245 assertions
  passed. Captured timer handles, return cleanup function from the
  useEffect.
- **engine/multi_agent_analysis**: same fix-pattern applied to track
  which steps the budget gate skipped, so the response doesn't lie
  about why a section is empty.

### Tests

- +29 dynamic_weights + source_accuracy
- +12 token_budget + effort kwarg + pricing
- +29 context_compressor + provider
- +13 dspy_judge (with sys.modules['dspy'] stub)
- +5 OpenAIProvider (response translation, effort mapping, lazy
  import, fallback pricing)
- All 245 UI tests still green; all ~800 backend tests pass on Linux
  CI after the float-rounding fix.

### Verification

- Live `fuse_signals("NVDA")` end-to-end: 6/8 sources active, conviction
  +9 NEUTRAL, all eight new modules connect cleanly
- E2E pipeline test (`tests/test_pipeline_e2e.py`, 8 tests): brain →
  PM → executor seam, including PM rejection blocking executor entirely
- Synthetic fusion backtest (`scripts/backtest_fusion_partial.py`):
  honest result that 8-source weights underperform 5-source legacy
  under the SNR assumptions tested — flagged in commit message rather
  than buried, since the SNRs are guesses
- `scripts/compare_fusion_variants.py`: NVDA flips BULLISH+21 → NEUTRAL+8
  going from 5-src to 8-src on identical live inputs

---

## [2026-04-24] — 8-Source Signal Fusion + Portfolio Manager + LLM Observability

Two back-to-back upgrade phases (Phase 7 + Phase 8 in FURTHER_UPDATES.md)
lifting the signal fusion engine from 5 sources to 8, adding a final
approval gate, and wiring dual LLM observability.

### Added — New Signal Sources (5 → 8)

- **Social sentiment** (`skills/social_sentiment.py`) — Reddit public JSON API
  (wallstreetbets / stocks / investing, no auth) + optional X/Twitter via
  `TWITTER_BEARER_TOKEN` (tweepy). Engagement-weighted compound score via
  existing FinBERT/VADER pipeline.
- **Earnings / PEAD** (`engine/earnings.py`) — yfinance earnings calendar
  (60-day horizon) + historical post-earnings 5-day drift, positive rate,
  and surprise↔drift correlation. Score amplified by proximity (≤3d: 1.3×).
- **Prediction markets** (`skills/prediction_markets.py`) — Polymarket Gamma
  API (no auth) filtered to active, open markets with future endDate.
  Volume-weighted deviation of Yes-price from 0.5, sign inferred from
  question text keywords.

Rebalanced `signal_fusion.DEFAULT_WEIGHTS` to seven sources with meaningful
coverage; prediction markets join at 0.06 default weight.

### Added — Decision Pipeline

- **Portfolio Manager gate** (`engine/portfolio_manager.py`, inspired by
  TauricResearch/TradingAgents, Apache-2.0) — final approval layer between
  decision generation and return. Rules (all overridable): min confidence,
  single-ticker concentration ≤20%, sector ≤40%, direction-streak warning
  at 5+, conviction-scaled position sizing capped at `max_position_pct`.
- Wired into `core/brain.run_for_mode` as opt-in layer: activated when
  caller passes `portfolio` + `portfolio_value`. Rejections downgrade the
  decision to WAIT with reasoning; warnings append to reasoning; the full
  verdict is surfaced via `DecisionOutput.extra["portfolio_manager"]`.
- `DecisionOutput` gained an `extra: dict` carrier field for optional
  metadata (backward-compatible: emitted only when non-empty).

### Added — LLM Observability

- **PostHog LLM Analytics export** — every `logged_create()` call mirrors
  to PostHog as `$ai_generation` event. Tracks model, tier, latency,
  tokens, cost, ticker, error, trace_id. Opt-in via `POSTHOG_API_KEY`.
- **Langfuse dual-write** — parallel export as `generation-create` batch
  event to `/api/public/ingestion` with full usage/cost/error metadata.
  Opt-in via `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY`. Langfuse
  complements PostHog with prompt versioning, evals, and datasets.

### Added — UI

- `EarningsWatchPanel` in `daily-intel.tsx` — Art Deco card rendering the
  new `earnings_watchlist` field from `/api/daily-intel`. Proximity badge
  (≤3d ruby / ≤7d gold), PEAD drift %, win rate, click-through to ticker.
- `SignalFusionCard` — new `SOURCE_LABELS` entries for `social_sentiment`
  (💬), `earnings` (📅), `prediction_markets` (🔮). Per-source detail rows
  show n_posts/bull/bear, days-until/PEAD/win-rate, and top Polymarket
  questions with Yes-price coloring.
- `types.ts` — new `EarningsEvent` and `PredictionMarket` interfaces;
  `SignalSource` extended with optional fields for the three new sources
  (all additive, backward-compatible).

### Changed

- `engine/daily_intel.py` — new `_generate_earnings_watchlist` helper and
  `earnings_watchlist` key in output, populated from top movers.
- `engine/demo_data.py` — 3 mock earnings events so the new UI card
  renders in demo mode.
- `llm/call_logger.py` — `_append_record` path now calls `_send_to_posthog`
  then `_send_to_langfuse`. All three are fire-and-forget, wrapped in
  `try/except pass` — telemetry never breaks the main flow.

### Fixed

- `engine/earnings.py` — leap-year crash on `now.replace(year=now.year - 2)`
  when today is Feb 29 and the target year isn't a leap year. Switched to
  `timedelta(days=365 * lookback_years)`.
- `skills/social_sentiment.py` — added Reddit-spec regex guard
  (`^[A-Za-z0-9_]{1,21}$`) on subreddit names before URL interpolation
  (SSRF mitigation for when the param is user-controlled).
- `orallexa-ui/app/components/signal-fusion.tsx` — `SOURCE_LABELS` had
  no entries for the two new keys added to fusion, so the UI rendered
  raw snake_case with a generic fallback icon.

### Research / Integrations

- Evaluated trending repos (Apr 2026): TauricResearch/TradingAgents,
  sandy1709/poly_data, langfuse/langfuse, sansan0/TrendRadar, FinMem,
  AgentQuant, QuantAgent. Tier-1 borrowings (Portfolio Manager layer,
  Polymarket alpha source, Langfuse observability) shipped; Tier-2
  candidates (multi-platform news, layered memory, regime-conditional
  strategies) queued for next session.

### Tests

- +64 new backend tests across `test_social_sentiment`, `test_earnings`,
  `test_posthog_export` (+Langfuse), `test_prediction_markets`,
  `test_portfolio_manager`, `test_engine_integration` (new PM cases).
- 245 frontend (vitest) tests still green — `EarningsWatchPanel` added
  without regression.

### Verified Live

Unmocked `fuse_signals("NVDA")` end-to-end with 6/8 sources active:
`conviction=+5 NEUTRAL confidence=64`. Polymarket fetched 8 markets
($21k 24h volume), earnings source active 26 days pre-report with
PEAD −3.78%, Reddit returned 18 posts (6 bull / 3 bear).

---

## [2026-04-03b] — Optimization Sprint & Test Coverage Expansion (698 Tests)

### Adaptive Walk-Forward Optimization
- **Optuna integration** — Per-window Bayesian parameter search in walk-forward evaluation
- **Adaptive trial count** — Base 20 + 8 per parameter dimension (e.g., rsi_reversal gets 52 trials)
- **CLI flag** — `--no-adaptive` to disable and use fixed default params

### Desktop Agent Hardening
- **API retry with exponential backoff** — Claude, Whisper, TTS calls retry 3x on transient errors (timeout, 429, 503)
- **Thread safety** — `threading.Lock` on voice_handler recording flag
- **Chart analysis cache** — SHA256-based cache with 5-min TTL, LRU eviction (max 20 entries)
- **Model name configurable** — `CLAUDE_MODEL` constant, overridable via `BULL_CLAUDE_MODEL` env var
- **Timer cleanup** — Batch-cancel all pending `after()` callbacks on rapid state changes

### Strategy Evolver Overfitting Protection
- **Early stopping** — Halt if best Sharpe stagnates for 2+ generations
- **Diversity enforcement** — Reject signals with >0.9 correlation to existing strategies
- **Sharpe cap** — Cap unrealistic Sharpe (>4.0) as suspicious
- **Trade count penalty** — Strategies with <5 trades penalized proportionally

### Performance
- **Monte Carlo vectorized** — Numpy batch operations replace Python for-loop (10-50x speedup)
- **RL Agent multi-seed** — Train 3 seeds, pick best; gradient clipping, convergence check
- **Multi-Agent timeout** — 60s guard on LLM calls with graceful fallback
- **Particle effects** — Batch-delete dead canvas items, skip off-screen early

### Testing — 424 → 698 (+274 tests)
- **test_engine_core** (62) — backtest, 9 strategies, market analyst
- **test_engine_extras** (47) — decision_log, demo_data, factor_engine, multi_strategy
- **test_ml_rl_signals** (20) — ML features/labels, RL env/trader
- **test_brain_bridge** (30) — intent detection, ticker/mode/TF extraction
- **test_daily_intel** (10) — price fetch, constants, cache path
- **components.spec.ts** (16) — Playwright E2E: watchlist, market strip, decision card, mobile layout

### CI/CD
- **Coverage reporting** — `pytest --cov` with XML output in CI
- **test:coverage script** — Added to orallexa-ui/package.json

### Docs
- **README** — Test count 424→698, architecture table updated with Optuna, comparison table updated

---

## [2026-04-03] — Quality, Testing, CI/CD, Performance & Deployment

### Code Quality
- **Lint zero warnings** — Resolved all 7 ESLint warnings: unused imports, `<img>` → `next/image`, ternary expressions, exhaustive-deps
- **React hooks fixes** — `useState` → `useRef` for seen-set in signal-toast, `useSyncExternalStore` for localStorage in offline page, missing `useCallback` dependencies
- **ErrorBoundary** — Global error boundary wrapping app in layout.tsx with Art Deco-styled error page and reload button

### Testing — 230 Frontend + 14 E2E + ~180 Backend = 424 Total
- **New unit tests** — price-chart (11 tests: chart rendering, period switching, indicator toggles, mock data), signal-toast (12 tests: auto-dismiss timeout, dismiss stopPropagation, badge types), service-worker-registrar (8 tests: SW registration, sendLocalNotification, SW_UPDATED event dispatch)
- **Expanded coverage** — atoms (BrandMark, Mod, GoldRule, DecoFan), signal-toast timeout behavior, ServiceWorkerRegistrar granted permission path
- **Coverage 73% → 86%** — Installed `@vitest/coverage-v8`, overall line coverage 86.4%
- **Playwright E2E** — 14 tests: page load, ticker input, strategy/horizon buttons, language toggle, Claude overlay, responsive mobile menu, offline page retry/navigation

### CI/CD Pipeline
- **ESLint added to CI** — `npm run lint` step in build-ui job
- **E2E job added** — Playwright Chromium in GitHub Actions, depends on build-ui, uploads artifacts on failure
- **CI badge** — Added to README

### Performance
- **Lazy-load heavy components** — `PriceChart` (lightweight-charts ~414KB) and `DailyIntelView` dynamically imported with `ssr: false`
- **Lighthouse audit** — Accessibility 96, Best Practices 96, SEO 100, FCP 0.9s, CLS 0.058

### Backend API Fix
- **Backtest endpoint** — Fixed `MarketDataSkill` constructor (missing `ticker` arg), added 70/30 train/test split for walk-forward analysis, corrected result parsing from `all_results` dict

### Deployment
- **Vercel production** — Deployed to [orallexa-ui.vercel.app](https://orallexa-ui.vercel.app) with latest build
- **.env.example** — Added `orallexa-ui/.env.example` with `NEXT_PUBLIC_API_URL`
- **.gitignore** — Added Playwright artifacts (test-results/, playwright-report/)

### Files Changed
- Tests: 3 new test files + 4 expanded, playwright.config.ts, e2e/dashboard.spec.ts
- Components: error-boundary.tsx, atoms.tsx (next/image), signal-toast.tsx (useRef), offline/page.tsx (useSyncExternalStore + Link), page.tsx (lazy imports + deps)
- CI: .github/workflows/ci.yml (+ESLint +E2E)
- Backend: api_server.py (backtest endpoint fix)
- Docs: README.md (test counts, CI badge, structure), .env.example

---

## [2026-04-02] — Design System, Component Architecture & Full Test Coverage

### Design System & Branding
- **DESIGN.md** — Full Art Deco design system spec: 4-font system (Poiret One / Josefin Sans / Lato / DM Mono), gold palette, component patterns, spacing, motion, a11y
- **Pixel Bull mascot** — NFT-style pixel art bull on standby screen (5 market-color variants, 26 sprite frames)
- **Art Deco avatar redesign** — Geometric bull brand mark with gold diamond accents
- **Chat popover redesign** — Welcome greeting, pixel decorations, new layout
- **Chinese market colors** — Red = up, Green = down (matching Chinese market convention)
- **Logo regenerated** — Art Deco gold style PNG
- **Desktop agent fonts** — Josefin Sans + Lato + DM Mono TTFs aligned with web app

### Next.js Component Architecture (page.tsx 1574→751 lines, 52% reduction)
- **types.ts** (88 lines) — All interfaces + helper functions extracted
- **atoms.tsx** (148 lines) — DecoFan, GoldRule, Heading, Mod, Row, Toggle, BullIcon, BrandMark, CopyBtn
- **decision-card.tsx** (210 lines) — DecisionCard + ProbBar + BullBearPanel + InvestmentPlanCard
- **daily-intel.tsx** (168 lines) — DailyIntelView with all sections
- **watchlist.tsx** (64 lines) — WatchlistGrid
- **breaking.tsx** (65 lines) — BreakingBanner with EN/ZH explanations
- **market-strip.tsx** (46 lines) — MarketStrip with live price support
- **ml-scoreboard.tsx** (27 lines) — MLScoreboard with best-model highlight

### Next.js UX Improvements
- **a11y**: aria-expanded on Toggle, role=checkbox on Claude toggle, prefers-reduced-motion
- **Keyboard shortcuts**: Ctrl+Enter (run), Ctrl+D (deep), Ctrl+1/2 (tab switch), Escape (clear)
- **next/font**: Zero-CLS font loading (replaced external Google Fonts CDN)
- **Error UX**: Retry button, connection status indicator, last-signal timestamp, offline banner
- **SEO**: OG meta tags, auto-dismiss errors, colorScheme: dark
- **Brand**: Gold-only gradient (removed leftover blue/purple)

### Testing — 139 Frontend Tests (vitest + @testing-library/react)
- **vitest.config.ts** — jsdom environment, React plugin, setup file
- **types.test.ts** (28 tests) — displayDec, sigLabel, confLabel, riskLabel, decColor, nsSummary
- **atoms.test.tsx** (12 tests) — Heading, Row, Toggle, CopyBtn render + behavior
- **mock-data.test.ts** (31 tests) — All mock generators: analyze, deep, news, profile, journal, watchlist, chart, dailyIntel
- **decision-card.test.tsx** (17 tests) — Empty/BUY/SELL states, investment plan, bull/bear debate, toggles
- **breaking.test.tsx** (11 tests) — All signal types, EN/ZH explanations, severity styling
- **market-strip.test.tsx** (10 tests) — Live price, RSI, H/L, flash animation, live indicator
- **ml-scoreboard.test.tsx** (7 tests) — Headers, best model highlight, sharpe/return/win%
- **watchlist.test.tsx** (9 tests) — Click handler, error display, probability bars
- **daily-intel.test.tsx** (14 tests) — Mood, movers, sectors, AI picks, volume spikes, thread
- **CI pipeline**: vitest added to GitHub Actions Next.js build job

### ML & Evaluation
- **Optuna hyperparameter optimizer** — Bayesian optimization for strategy parameters
- **Strategy ensemble framework** — Combine multiple strategies with weighted voting
- **LLM explainer** — Natural language explanation of optimized parameters
- **Eval charts** — matplotlib visualizations for walk-forward results
- **Strategy evolver** — Improved LLM-driven strategy generation pipeline
- **Daily eval pipeline** — Automated daily evaluation runs

### Other
- **CORS fix** — Added Vercel production URL to allowed origins
- **ASSETS.md** — Image catalog with upload guide
- **Figma brand assets** — Logo variants created (avatar states pending)
- **Gitignore** — Runtime data files excluded (memory_data/*.json)

### Files Changed (32 files in commit 03c07f2)
- Design: DESIGN.md, globals.css, layout.tsx, fonts.py, character_window.py, chat_popover.py
- Components: types.ts, atoms.tsx, decision-card.tsx, daily-intel.tsx, watchlist.tsx, breaking.tsx, market-strip.tsx, ml-scoreboard.tsx, index.ts, page.tsx
- Tests: vitest.config.ts, vitest.setup.ts, 9 test files
- ML: strategy evolver, daily eval, Optuna optimizer
- Config: ci.yml, package.json, ASSETS.md

---

## [2026-04-01] — Cloud Deployment & Final Polish

### Cloud Infrastructure
- **Cloud Deploy** — Live demo: [Vercel](https://orallexa-aa9zjelyu-alex-jbs-projects.vercel.app) (frontend) + [Railway](https://orallexa-ai-trading-agent-production.up.railway.app) (backend, demo mode)
- **Demo Mode** — `DEMO_MODE=true` runs full UI with simulated data, zero API cost
- **Lightweight Docker** — `Dockerfile.railway` for cloud: no PyTorch, <1GB image
- **README Rewrite** — Repositioned as "AI Trading Operating System", live demo links
- **New Logo** — Blue wings + gold/blue text, deployed to README, PWA icons, presentation, dashboard

### Experience Fixes
- **API Startup** — Removed blocking warmup, now starts instantly
- **7 Silent Exceptions** — All bare `except: pass` replaced with debug logging
- **Viewport Warning** — Fixed Next.js metadata deprecation

---

## [2026-04-01] — Deep Learning Models & Testing

### New ML Models (9 total)
- **#014 EMAformer** — AAAI 2026 Transformer with Embedding Armor (Sharpe 1.24, +4.3% return)
- **#015 PPO RL Agent** — Reinforcement learning, Sharpe optimized from -2.76 to +4.86
- **#016 LLM Strategy Evolution** — Claude generates/tests/evolves Python strategy code across generations
- **#017 GNN (GAT)** — Graph Attention Network, 17-stock relationship graph, inter-stock signals
- **#018 DDPM Diffusion** — Probabilistic forecasting, 50 price paths, VaR/confidence intervals
- **#019 LangGraph** — Bull/Bear debate migrated to StateGraph with typed state + conditional routing

### Quality & DevOps
- **#020 Test Suite** — 113 tests (integration + ML regression + API E2E), 108 passed, 0 failed
- **#021 Social Posts** — Per-section "Copy for X" button, plain-language Twitter-ready content
- **#022 CI/CD** — GitHub Actions: lint + test + build on every push (3 jobs, ~1 min)
- **#023 Docker** — `docker compose up` one-click deploy with healthcheck
- **#024 Alpaca Paper Trading** — Execute signals as bracket orders with auto stop-loss/take-profit
- **#025 WebSocket** — `/ws/live` real-time price stream + signal change detection
- **#026 PWA** — Installable mobile app with custom icons

---

## [2026-04-01] — Production Readiness: Docker + README + Deploy Fixes

### Added
- **`Dockerfile`** (API) — Python 3.11-slim, uvicorn entrypoint, port 8002
- **`orallexa-ui/Dockerfile`** (Frontend) — Node 20 Alpine, standalone Next.js build, port 3000
- **`docker-compose.yml`** — one-click `docker compose up` for API + Frontend
- **`.dockerignore`** + `orallexa-ui/.dockerignore` — exclude node_modules, .env, .git
- **`.env.example`** — full template with all env vars documented
- **`README.md`** — GitHub-grade English README with: badges, architecture diagram, feature tables, quickstart, project structure, tech stack, API reference, cost breakdown
- **`README_CN.md`** — Complete Chinese translation with language toggle link

### Changed
- **API URL**: `page.tsx` now reads `NEXT_PUBLIC_API_URL` env var (was hardcoded `localhost:8002`)
- **CORS**: `api_server.py` reads `CORS_ORIGINS` env var (was hardcoded whitelist)
- **requirements.txt**: added `fastapi`, `uvicorn[standard]`, `python-dotenv`, `python-multipart`
- **next.config.ts**: added `output: "standalone"` for Docker builds
- **Error messages**: removed localhost URL from user-facing errors

### Files Changed
- `Dockerfile` (new), `orallexa-ui/Dockerfile` (new), `docker-compose.yml` (new)
- `.dockerignore` (new), `orallexa-ui/.dockerignore` (new), `.env.example` (updated)
- `README.md` (full rewrite), `README_CN.md` (new)
- `api_server.py`, `orallexa-ui/app/page.tsx`, `orallexa-ui/next.config.ts`, `requirements.txt`

---

## [2026-04-01] — Orallexa Social-Grade Daily Intel Upgrade

### Changed (engine/daily_intel.py — major rewrite)
- **LLM upgraded**: Haiku → **Sonnet (DEEP_MODEL)** for all 3 AI calls — dramatically better writing quality, sharper opinions, specific data references
- **Volume spike detection**: scans 50+ tickers (was 30), detects unusual volume (≥2x 20-day average) as potential institutional activity. Uses `yf.Ticker.history(1mo)` for avg volume baseline
- **Expanded watchlist**: added 20 extra tickers for volume scanning (RIVN, NIO, BABA, SOFI, AI, IONQ, etc.)
- **Richer prompts**: summary prompt now demands conviction, specific numbers, no filler. Picks prompt requires contrarian picks and opinionated theses.
- **Temperature 0.3→0.5** for thread generation (more creative writing)

### Added
- **`_generate_orallexa_thread()`** — 1 Sonnet call generating a 6-7 post social thread:
  - Post 1: Hook with market mood + biggest move
  - Post 2: Top movers with $TICKER format and why
  - Post 3: Volume alerts (institutional activity)
  - Post 4: Sector rotation theme
  - Post 5: AI picks with bull/contrarian calls
  - Post 6-7: Risk + CTA with hashtags
  - Each post enforced ≤280 chars
- **`volume_spikes` field** in API response — tickers with ≥2x average volume, sorted by ratio
- **`orallexa_thread` field** in API response — array of ready-to-post strings
- **Volume Spikes section** in DailyIntelView — shows tickers with unusual volume + badge (e.g. "5x vol")
- **Orallexa Thread section** in DailyIntelView — numbered posts with:
  - Per-post "Copy" button (hover to reveal)
  - "Copy Full Thread" button at bottom
  - Gold accent on first post (hook)
- All branding changed from "Twitter" to **"Orallexa"** — this is our own analysis platform

### Cost
- Total: ~$0.05/day (3 Sonnet calls) — up from $0.002 but dramatically higher quality

### Files Changed
- `engine/daily_intel.py` — full rewrite: volume spike scanner, Sonnet upgrade, thread generator, expanded watchlist
- `orallexa-ui/app/page.tsx` — DailyIntelData type updated, Volume Spikes component, Orallexa Thread component with copy buttons

---

## [2026-04-01] — Daily Market Intelligence Dashboard

### Added
- **`engine/daily_intel.py`** (new) — autonomous daily market intelligence orchestrator:
  - **Step 1: Top Movers** — parallel scan of 30 tickers (mega-cap tech, growth/AI, ETFs, crypto) via `yfinance.fast_info`, returns top 5 gainers + top 5 losers by |change%|
  - **Step 2: Sector Heatmap** — 11 sector ETFs (XLK, XLF, XLE, etc.) with change% for rotation analysis
  - **Step 3: News Scan** — fetches headlines for top movers + SPY via existing `NewsSkill`, scores with sentiment engine, returns top 15 by |impact|
  - **Step 4: AI Summary** — 1 Haiku call (~$0.001): 200-300 word morning brief covering market mood, movers, sector rotation, key risks
  - **Step 5: AI Picks** — 1 Haiku call (~$0.001): 3-5 "worth watching" tickers with direction, reason, catalyst
  - **Step 6: Cache** — saves to `memory_data/daily_intel.json`, only regenerates if date changed or force=True
- **`GET /api/daily-intel`** — serves cached daily intel, generates on first request per day
- **`POST /api/daily-intel/refresh`** — force regenerate daily intel
- **View toggle** in header bar: `Signal | Intel` pill toggle switches between analysis and intel views
- **DailyIntelView component** with 6 sections:
  - **Market Mood Banner** — large RISK-ON / RISK-OFF / MIXED with color-coded background
  - **Morning Brief** — AI-generated summary in Mod card with timestamp
  - **Top Movers Grid** — 2-column gainers (green) / losers (red) with click-to-analyze
  - **Sector Heatmap** — horizontal bar chart with centered zero-line, green/red color coding
  - **AI Picks** — worth watching cards with direction badge + reason + catalyst
  - **Headlines** — top 15 sentiment-scored news with clickable URLs and provider
- **Auto-fetch** — intel loads automatically when tab first switches to "Intel"
- **Refresh button** — force regenerate with loading spinner
- **Click-to-analyze** — clicking any ticker in intel view switches to Signal mode with that ticker
- **i18n** — all labels in EN + ZH (morningBrief, topMovers, sectorMap, aiPicks, etc.)
- **Skeleton loader** — shown while daily intel is loading

### Cost
- Total: ~$0.002/day (2 Haiku calls) + ~5s yfinance (free)

### Files Changed
- `engine/daily_intel.py` (new) — 230 lines, full orchestrator
- `api_server.py` — 2 new endpoints
- `orallexa-ui/app/page.tsx` — DailyIntelData type, DailyIntelView component (~150 lines), view toggle, state + fetch logic, i18n

---

## [2026-04-01] — Full UX/UI Audit Upgrade (Dashboard + Desktop Agent)

### Dashboard — Mobile Responsive
- **3-column → responsive layout**: `flex-col lg:flex-row` — sidebars collapse on mobile/tablet
- **Mobile top bar**: brand + hamburger menu button, toggles left sidebar visibility
- **Left sidebar**: hidden on mobile by default, `max-h-[80vh]` scrollable when open
- **Right sidebar**: `hidden lg:block` — only visible on desktop (1024px+)
- **Center content**: `p-4 lg:p-6` responsive padding
- **Header bar**: desktop-only details hidden on mobile with `hidden lg:flex`

### Dashboard — Accessibility (WCAG 2.1 AA)
- **ARIA labels** on all interactive elements: asset input, strategy/horizon buttons (`aria-pressed`), language toggle (`role="radiogroup"`, `aria-checked`), Run Signal/Deep Intel (`aria-busy`), error alerts (`role="alert"`), loading (`role="status"`, `aria-live="polite"`)
- **Semantic landmarks**: `role="application"` on root, `role="main"` on center, `role="navigation"` on left sidebar, `role="complementary"` on right sidebar
- **Focus indicators**: global `*:focus-visible` with gold outline + box-shadow in globals.css
- **Touch target sizes**: strategy/horizon buttons increased from `py-0.5` to `py-1`, font 8px→9px; language toggle `py-1.5` → `py-2`, font 9px→10px
- **Keyboard support**: Enter key on asset input triggers Run Signal
- **Disabled states**: added `disabled:cursor-not-allowed` to all buttons

### Dashboard — Loading States & Error Handling
- **Inline loading spinners**: gold spinning circle inside Run Signal and Deep Intel buttons during loading
- **Deep analysis step indicator**: 5-step progress chips (Technicals → News → ML Models → AI Debate → Risk Mgmt) shown during deep analysis
- **Skeleton loaders**: news feed and capital profile show animated skeleton placeholders instead of "Loading..." text
- **Error banner upgrade**: red shake animation (`anim-error`), dismiss button (✕), `role="alert"`, improved contrast (#FF6666)

### Dashboard — CSS Animations (globals.css)
- **New keyframes**: `fadeIn`, `slideInRight`, `slideInLeft`, `errorShake`, `spin`, `skeletonPulse`, `priceTick`, `breakingPulse`
- **Utility classes**: `.anim-fade-in`, `.anim-slide-right`, `.anim-slide-left`, `.anim-error`, `.anim-spin`, `.anim-skeleton`, `.anim-price-tick`, `.anim-breaking`
- **Skeleton loader**: `.skeleton` class with gold shimmer gradient
- **Tooltip system**: `[data-tooltip]` CSS-only tooltips on hover with fade-in
- **Print stylesheet**: `@media print` hides sidebars, switches to white background
- **Accessibility CSS vars**: `--text-muted-safe`, `--text-dim-safe` for WCAG-compliant muted text

### Desktop Agent — Accessibility
- **Font size**: `MIN_PT` increased from 8→10 (WCAG AA minimum for body text)
- **Contrast fix**: `FG_HINT` changed from `#4B5E75` (3.2:1) to `#6B7E95` (4.5:1+) on dark backgrounds

### Desktop Agent — Risk Management Card
- **New risk metrics row** in decision card: Entry, Stop, Target, R:R — color-coded (stop=red, target=green)
- **`_show_risk_mgmt()` method** on ChatPopover — callable after any analysis to display entry/stop/target/risk-reward

### Desktop Agent — i18n Completeness
- **Risk levels**: `risk_low`, `risk_medium`, `risk_high` (EN + ZH)
- **Risk management labels**: `entry`, `stop`, `target`, `risk_reward`
- **Error categories**: 6 new keys — `error_api_key_missing`, `error_network`, `error_service_unavailable`, `error_timeout`, `error_invalid_ticker`, `error_generic`
- **Loading steps**: 5 new keys — `step_fetching_data`, `step_computing`, `step_analyzing`, `step_ai_overlay`, `step_complete`
- **Startup validation**: `startup_checking`, `startup_ready`, `startup_api_missing`

### Desktop Agent — Tray Icon Sync
- **`update_state()` method** on TrayIcon — dynamically updates tooltip to show current ticker, mode, timeframe, and last decision (e.g. "Bull Coach · NVDA · Intraday (15m) → BUY")

### Desktop Agent — Startup Validation
- **API key checks** on startup: warns in log if ANTHROPIC_API_KEY or OPENAI_API_KEY is missing
- Allows app to launch in limited mode (no crash on missing keys)

### Files Changed
- `orallexa-ui/app/globals.css` — full rewrite with animations, focus, skeleton, tooltip, responsive, print
- `orallexa-ui/app/page.tsx` — mobile responsive layout, ARIA labels, loading spinners, step indicator, skeleton loaders, error banner, tooltips, keyboard support
- `desktop_agent/chat_popover.py` — MIN_PT 8→10, FG_HINT contrast fix, risk management row + method
- `desktop_agent/i18n.py` — 20+ new translation keys (risk, errors, loading steps, startup)
- `desktop_agent/tray_icon.py` — `update_state()` method for dynamic tooltip
- `desktop_agent/main.py` — startup API key validation

---

## [2026-04-01] — Claude AI Overlay for Fast Analysis

### Added
- **`_fast_claude_overlay()`** function in `api_server.py` — single Haiku call (~0.5s, ~$0.0005) that reviews and refines a technical-only signal. Can adjust confidence ±15 points and probabilities ±10%. Returns a one-sentence refinement explanation
- **`use_claude` parameter** on `POST /api/analyze` — when true, runs the Claude overlay after technical analysis (only on non-WAIT signals)
- **Claude AI Overlay toggle** — checkbox-style button in sidebar to enable/disable LLM refinement on Run Signal. Gold highlight when active
- Source field shows `+claude` suffix when overlay is applied (e.g. `intraday+claude`)

### Design
- Guardrails: LLM cannot flip BUY↔SELL, only adjust within ±15 confidence and ±10% probability bounds
- Graceful degradation: if Claude call fails, original technical signal is returned unchanged
- Cost: ~$0.0005 per call (Haiku), compared to ~$0.003 for full debate

### Files Changed
- `api_server.py` — `_fast_claude_overlay()` function + `use_claude` form param
- `orallexa-ui/app/page.tsx` — `useClaude` state, toggle button, form param in runSignal

---

## [2026-04-01] — Multi-Ticker Watchlist Scan

### Added
- **POST /api/watchlist-scan** endpoint — accepts comma-separated tickers (up to 10), runs fast technical analysis in parallel (ThreadPoolExecutor, 4 workers), returns sorted signal cards (strongest signals first). No LLM calls — pure technical scoring
- **WatchlistGrid component** — Kalshi/Manifold-inspired compact signal cards in a responsive grid (2-3 columns). Each card shows:
  - Ticker + live price + daily change %
  - Hero probability number (up% or down% based on direction)
  - Decision badge (BULLISH/BEARISH/NEUTRAL) with accent color
  - Mini probability bar (green/gold/red segments)
  - Confidence progress bar
- **Watchlist sidebar panel** — input field for tickers + "Scan All" button
- **Click-to-select** — clicking a watchlist card sets it as the active asset and clears the grid
- **i18n** — watchlist labels in EN + ZH

### Files Changed
- `api_server.py` — new `/api/watchlist-scan` endpoint with parallel execution
- `orallexa-ui/app/page.tsx` — WatchlistItem type, WatchlistGrid component, sidebar panel, state + scan logic

---

## [2026-04-01] — Auto-Refresh Live Price

### Added
- **GET /api/live/{ticker}** endpoint — lightweight live price via yfinance fast_info (sub-second response). Returns: price, change%, prev_close, day high/low, volume, and last signal from decision log
- **Auto-refresh toggle** — sidebar button to enable/disable live data polling (30-second interval)
- **Live price polling** — when enabled, fetches `/api/live/{ticker}` every 30s and updates MarketStrip in real-time
- **Price flash animation** — MarketStrip price cell briefly flashes green (price up) or red (price down) on each update, with background highlight
- **Change% column** — MarketStrip now shows daily change percentage with green/red coloring
- **High/Low column** — MarketStrip shows day high/low when live data is available
- **Live indicator** — pulsing green dot in MarketStrip when live data is active

### Changed
- **MarketStrip** — now accepts `livePrice` and `priceFlash` props; replaced static Vol column with dynamic Chg% and H/L columns when live data flows

### Files Changed
- `api_server.py` — new `/api/live/{ticker}` endpoint
- `orallexa-ui/app/page.tsx` — auto-refresh state + polling, enhanced MarketStrip, toggle button

---

## [2026-04-01] — Breaking Signal Alerts

### Added
- **Breaking Signal detection engine** (`engine/breaking_signals.py`) — compares current analysis vs last logged signal for the same ticker. Three alert types:
  - `decision_flip` (critical): e.g. BUY → SELL
  - `probability_shift` (high): up/down probability shifts >15 percentage points
  - `confidence_shift` (medium): confidence changes >20 points
- **GET /api/breaking-signals** endpoint — returns recent breaking signals within N hours, capped at limit
- **Inline breaking detection** — both `/api/analyze` and `/api/deep-analysis` now detect and return `breaking_signal` in response when thresholds exceeded
- **Deep analysis decision logging** — `/api/deep-analysis` now saves to decision_log.json (enables breaking signal comparison for deep analysis runs)
- **BreakingBanner UI component** — Polymarket-inspired alert banner with severity-coded styling:
  - Critical (decision flip): red pulse with ⚡ icon
  - High (probability shift): gold pulse with △ icon  
  - Medium (confidence shift): green with ● icon
- **Breaking signal polling** — frontend polls `/api/breaking-signals` every 60 seconds + captures inline alerts from signal/deep analysis responses

### Files Changed
- `engine/breaking_signals.py` (new) — detection logic + persistence
- `api_server.py` — breaking detection in analyze + deep-analysis, new GET endpoint
- `orallexa-ui/app/page.tsx` — BreakingSignal interface, BreakingBanner component, state + polling + inline capture

---

## [2026-03-31] — LLM Content Depth & Dashboard Research Upgrade

### Added
- **LLM Deep Market Report** — new `_run_llm_market_report()` in `engine/multi_agent_analysis.py`. Sends local technical data + news + ML results to Claude Sonnet (max_tokens=1500) to generate a structured 500-700 word deep analysis with 5 sections: Market Structure, Catalyst Assessment, ML Consensus, Risk Factors, Actionable Levels
- **Investment Thesis section** — expandable "Investment Thesis" in the InvestmentPlanCard (frontend) showing the risk manager's `analysis_narrative` (200-300 word strategic context)
- **`analysis_narrative` API field** — returned at top level from `/api/deep-analysis`

### Changed
- **Bull analyst** (`llm/debate.py`): max_tokens 400→800, structured 4-point argument template (Momentum & Trend, Entry Setup, Catalyst/Context, Risk/Reward), 300-400 words
- **Bear analyst** (`llm/debate.py`): max_tokens 400→800, structured 4-point counter-argument template, 300-400 words
- **Judge** (`llm/debate.py`): max_tokens 300→600, added `reasoning_detail` field (2-3 sentence expansion beyond the one-line summary)
- **Risk Manager** (`engine/multi_agent_analysis.py`): max_tokens 500→800, `plan_summary` expanded from <100 words to 150-200 words, new `analysis_narrative` field (200-300 word investment thesis)
- **Market Report display** (`orallexa-ui/app/page.tsx`): visible lines before fold increased from 6→12
- **ML Analysis display** (`orallexa-ui/app/page.tsx`): visible lines before fold increased from 6→10
- **Deep analysis pipeline** now uses LLM-generated market report instead of plain-text local indicator summary

### Research
- Conducted competitive analysis of Polymarket, TradingView, Robinhood, Kalshi, Manifold Markets, and Metaculus
- Key findings: probability-first visual hierarchy, progressive disclosure pattern, card-based layouts, breaking alerts on significant shifts
- Validated existing Art Deco UI patterns align well with modern trading platform conventions

### Files Changed
- `llm/debate.py` — richer prompts + higher token limits
- `engine/multi_agent_analysis.py` — new LLM market report function + richer risk manager
- `api_server.py` — `analysis_narrative` field in response
- `orallexa-ui/app/page.tsx` — expanded report displays + investment thesis section
