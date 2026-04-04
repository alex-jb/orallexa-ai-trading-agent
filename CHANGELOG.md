# Changelog

All notable changes to the Orallexa project will be documented in this file.

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
