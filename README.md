<div align="center">

<img src="assets/logo.svg" alt="Orallexa" width="420">

<br>

### Multi-agent AI paper-trading research system with calibration diagnostics

**8-source signal fusion · 10 ML models incl. Kronos · Claude-based Bull/Bear/Judge debate**<br>
Polymarket + Kalshi prediction markets can contribute to signal fusion. Per-source accuracy weighting is optional and needs measured outcomes.

**Research prototype.** Orallexa has multi-agent decision components, Brier-score audit tools, a Risk Sizer that separates direction from sizing, and kill-condition checks. Brier tooling does not establish that forecasts are calibrated or trades have an edge. Broker execution in this repository is **Alpaca paper only**; a Brier threshold cannot enable live orders.

<br>

[![Stars](https://img.shields.io/github/stars/alex-jb/orallexa-ai-trading-agent?style=for-the-badge&logo=github&color=D4AF37&logoColor=white)](https://github.com/alex-jb/orallexa-ai-trading-agent)
[![Python](https://img.shields.io/badge/Python-3.11+-1A1A2E?style=for-the-badge&logo=python&logoColor=D4AF37)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js_16-1A1A2E?style=for-the-badge&logo=next.js&logoColor=D4AF37)](https://nextjs.org)
[![Claude](https://img.shields.io/badge/Claude_Opus_4.7-1A1A2E?style=for-the-badge&logo=anthropic&logoColor=D4AF37)](https://anthropic.com)
[![Multi-Provider](https://img.shields.io/badge/Anthropic_·_OpenAI_·_Gemini-1A1A2E?style=for-the-badge&logoColor=D4AF37)](docs/NEW_MODULES.md)
[![CI](https://img.shields.io/github/actions/workflow/status/alex-jb/orallexa-ai-trading-agent/ci.yml?style=for-the-badge&logo=githubactions&logoColor=white&label=CI&color=22c55e)](https://github.com/alex-jb/orallexa-ai-trading-agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/MIT-1A1A2E?style=for-the-badge)](LICENSE)

<br>

[**Live Demo**](https://orallexa-ui.vercel.app) · [**Presentation**](https://alex-jb.github.io/orallexa-ai-trading-agent/presentation.html) · [**Evaluation Report**](docs/evaluation_report.md) · [**中文**](README_CN.md)

<br>

<img src="assets/showcase_demo.png" alt="Market Scan → AI Analysis → Decision" width="720">

</div>

<br>

## What makes this different

Most AI trading projects: feed data into a model, get a signal, done.

Orallexa has a **multi-agent intelligence pipeline**. A perspective panel and Bull/Bear/Judge debate can inform a decision; a rule-based swarm runs hypothetical scenarios. Signal fusion combines available sources, and a bias tracker records past errors. A separate, explicitly requested execution path can submit an Alpaca paper order.

```
Market Data → 9 ML Models → 4-Role Panel + Bull/Bear Debate
    → 8-Source Signal Fusion → Judge Verdict → What-If Scenarios
    → Risk Plan → Portfolio Manager → Paper Execution → Dashboard → Social Content
```

These components are research tools; their effect on prospective net returns has not been established.

---

## Try it instantly

**[Open Live Demo](https://orallexa-ui.vercel.app)** — demo mode, no API key needed. Click **NVDA**, **TSLA**, or **QQQ** to see a full analysis.

Or run locally:

```bash
git clone https://github.com/alex-jb/orallexa-ai-trading-agent.git
cd orallexa-ai-trading-agent
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=your_key" > .env

# Terminal 1: API
python api_server.py

```

## ⚠️ Educational research, not financial advice

This repository is published for educational and research purposes. Nothing
here is investment, trading, or financial advice. The models, signals, and
outputs shown are experimental and may be wrong. Past performance does not
predict future results. Do not use any output as the basis for a real
trading, investment, or hedging decision without independent professional
verification. The author accepts no liability for losses.

```bash
# Terminal 2: UI
cd orallexa-ui && npm install && npm run dev
```

Docker: `docker compose up --build` — that's it.

---

## Walk-Forward Evaluation (Out-of-Sample)

The former eight-row table claimed results from 90 tests. The repo contains
only a nine-pair NVDA report and an older 21-pair run, without the underlying
OHLCV snapshots for the claimed 90. Those performance numbers are **unverified**.
The new 90-pair protocol is [predeclared here](eval/PROTOCOL.md); evaluation
will use all pairs, net costs, a same-ticker buy-and-hold comparison from each
OOS window's first open, and Bonferroni/BH corrections on paired excess returns.
The one-sided IID p-values remain exploratory. No current pair
has a reproducible result under that protocol.

<!-- EVAL_TABLE_START -->
| Strategy | Ticker | OOS Sharpe | Verdict | Bonferroni excess p |
|----------|--------|-----------|---------|---------------------|
| Pending pinned-data run | — | N/A | NOT EVALUATED | N/A |
<!-- EVAL_TABLE_END -->

> [Full 90-pair status →](docs/evaluation_report.md). Historical results are archived for audit, not evidence of a trading edge.

---

## Architecture

<p align="center">
  <img src="assets/architecture.svg" alt="System Architecture" width="100%">
</p>

<table>
<tr>
<td width="50%">

### Intelligence Layer

| Component | Detail |
|-----------|--------|
| **9 ML Models** | RF, XGB, EMAformer, MOIRAI-2, Chronos-2, DDPM, PPO RL, GNN, LR |
| **4-Role Perspective Panel** | Conservative / Aggressive / Macro / Quant analysts with optional regime-aware role selection; cost effect has not been benchmarked here |
| **CORAL Shared Memory** | Unified read aggregator over per-role + tiered memory; cross-role consensus injected into prompts |
| **Adversarial Debate** | Bull/Bear/Judge via Claude Sonnet + Haiku, full text stashed on `decision.extra` for offline eval-set assembly |
| **8-Source Signal Fusion** | Technical + ML + News + Options + Institutional + Social (Reddit/X) + Earnings/PEAD + Prediction Markets (Polymarket + Kalshi) |
| **10-Model ML Ensemble** | RF, XGB, LR + EMAformer, MOIRAI-2, Chronos-2, DDPM, PPO RL, GNN + **Kronos** (foundation model trained on 45+ global exchanges, 4 sizes) |
| **Adaptive Source Weights** | Optional scaling from recorded per-source outcomes; predictive improvement has not been demonstrated |
| **Regime-Conditional Strategies** | Detects trending / ranging / volatile and proposes a tuned strategy + params (heuristic or LLM-backed) |
| **What-If Scenarios** | Claude Opus 4.7 simulates impact of hypothetical events on your portfolio |
| **20-Agent Micro Swarm** | Rule-based Monte Carlo convergence simulation |
| **Bias Self-Correction** | Tracks prediction accuracy, auto-adjusts confidence |
| **Strategy Evolution** | LLM generates candidate Python strategies for sandbox tests; a sandbox pass is not evidence of future returns |
| **10 Rule-Based Strategies** | Double MA, MACD, Bollinger, RSI reversal, trend-momentum, alpha combo, dual thrust, ensemble vote, regime ensemble, **VWAP reversion** |
| **DSPy Phase B harness** | Compile pipeline ready: synthetic eval set → MIPROv2 → A/B vs hand-tuned baseline → 5%-gate ship/reject. Awaits 100 production debates worth of training data. |
| **Multi-modal Debate** | Optional chart input for a Quant persona. An offline harness can compare vision and text decisions against later outcomes; disabled by default, with no measured cost or lift claimed here. |
| **Daily Intel** | 50+ tickers, sector rotation, volume spikes, earnings watchlist, AI morning brief |

</td>
<td width="50%">

### Execution Layer

| Component | Detail |
|-----------|--------|
| **Portfolio Manager Gate** | Final approval layer — concentration, sector, streak checks + position sizing — runs on `analyze`, `deep-analysis`, AND `alpaca/execute` (rejected trades never hit the broker) |
| **Token & Cost Budgets** | Optional per-request TokenBudget can skip LLM-heavy deep-analysis steps after its configured cap; it does not cover every paid code path |
| **Paper Trading** | Alpaca bracket orders with auto stop-loss/take-profit |
| **Real-time Stream** | WebSocket prices every 5s + signal change alerts |
| **LLM Observability** | Triple sink: JSONL log + PostHog (`$ai_generation` events) + Langfuse (`generation-create` traces, prompt versioning, evals) |
| **Multi-Provider LLM** | Anthropic (default), OpenAI, Gemini all implemented; Ollama/Grok scaffolded. Switch via `ORALEXXA_LLM_PROVIDER` |
| **Dashboard** | Next.js 16, Art Deco theme, EN/ZH bilingual |
| **Desktop Coach** | Floating AI pet with voice input (Whisper) + TTS, API retry + caching |

</td>
</tr>
</table>

---

## Example Output

Illustrative NVDA-shaped output (not a live recommendation or measured forecast):

```
┌─────────────────────────────────────────────────────────────────┐
│  DECISION: BUY                    Confidence: 68%               │
│  Risk: MEDIUM                     Signal: 72/100                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  BULL CASE:                                                     │
│  • Price above MA20 > MA50 — full bullish alignment             │
│  • RSI at 62 — strong momentum, not yet overbought              │
│  • Volume 1.8x average — institutional participation likely     │
│                                                                 │
│  BEAR CASE:                                                     │
│  • ADX at 32 but declining — trend may be exhausting            │
│  • Bollinger %B at 0.85 — extended near upper band              │
│  • Earnings in 12 days — vol crush after event                  │
│                                                                 │
│  JUDGE VERDICT:                                                 │
│  "Bull case is stronger. BUY with tight stop at MA20."          │
│                                                                 │
│  PROBABILITIES: Up 58% | Neutral 24% | Down 18%                │
│  RISK PLAN:                                                     │
│  Entry: $132.50 | Stop: $128.40 | Target: $141.00 | R:R 2.1:1  │
└─────────────────────────────────────────────────────────────────┘
```

The output format contains a structured argument and a hypothetical risk plan; its probabilities are not calibrated by this example.

---

## 9 ML Models — Scored and Ranked

Every analysis runs all available models. The ML Scoreboard shows Sharpe, return, win rate side by side.

| Model | Type | What It Does |
|-------|------|-------------|
| Random Forest | Classification | 28 technical features → 5-day direction |
| XGBoost | Gradient Boosting | Same features, different optimization |
| Logistic Regression | Linear | Regularized baseline |
| **EMAformer** | Transformer | iTransformer + Embedding Armor (AAAI 2026) |
| **MOIRAI-2** | Foundation | Salesforce zero-shot time series forecaster |
| **Chronos-2** | Foundation | Amazon T5-based probabilistic forecaster |
| **DDPM Diffusion** | Generative | 50 possible price paths → VaR and confidence intervals |
| **PPO RL Agent** | Reinforcement | Gymnasium env, Sharpe-based reward |
| **GNN (GAT)** | Graph | 17-stock relationship graph, inter-stock signal propagation |

All models run on CPU.

---

## Dashboard

<p align="center">
  <img src="assets/screenshots/dashboard_preview.png" alt="Dashboard" width="90%">
</p>

**Signal View** — Decision card, probability bars, Bull/Bear debate, ML scoreboard, risk plan.<br>
**Intel View** — Morning brief, gainers/losers, sector heatmap, volume spikes, AI picks, social thread.

Art Deco theme. Polymarket-inspired probability display. Mobile responsive. EN/ZH bilingual.

---

## Desktop AI Coach

A floating pixel bull that lives on your desktop:

- **Voice chat** — Hold K to talk, Whisper transcribes, Claude responds
- **Chart analysis** — Ctrl+Shift+S screenshots any chart for Claude Vision analysis
- **Decision cards** — Entry, stop, target, risk/reward overlaid on screen
- **Market-aware avatar** — Bull changes color based on market conditions

---

## Cost-Aware AI

The debate can route structured steps to Haiku and reasoning steps to Sonnet;
local signal fusion and bias tracking do not call an LLM themselves. Actual
spend depends on enabled features, input/output tokens, retries, and current
provider prices. The earlier per-call and per-report dollar estimates had no
representative token-level input data or stated pricing snapshot, so they are
withdrawn. To inspect *your own* estimated API usage from the local, ignored
`logs/llm_calls.jsonl`, run:

```bash
python -c "from llm.cost_report import print_cost_report; print_cost_report()"
```

The report uses `llm/call_logger.py`'s configured per-token rates and may
differ from provider invoices; publish any future cost benchmark with its
redacted call records, exact model prices, date range, and invocation script.

`ORALLEXA_USE_CACHE=1` enables a cache for supported daily-grain yfinance paths. Intraday and `fast_info` paths intentionally bypass it. Cache hit rates and latency depend on the request and have not been benchmarked here.

`ORALLEXA_MULTIMODAL_SAMPLE=0.0..1.0` controls optional vision-augmented debate sampling; the default is `0` (off). An enabled call can run the Quant Researcher with text and a K-line chart and store a comparison in `decision_log.extra.multimodal_diff` for offline review. No measured lift or cost multiplier is claimed.

> Two patterns from this repo have been extracted as standalone Python packages + Claude Code skills:
> - **[claude-tier-router](https://github.com/alex-jb/claude-tier-router)** — the Haiku/Sonnet dual-tier routing (`pip install claude-tier-router`)
> - **[claude-debate](https://github.com/alex-jb/claude-debate)** — the Bull/Bear/Judge adversarial decision pattern, generalized (`pip install claude-debate`)

---

## Why this architecture

| Problem | Typical Approach | Orallexa |
|---------|-----------------|----------|
| Isolated signals | One model, one prediction | 8 sources fused: technical + ML + news + options + institutional + social + earnings + prediction markets |
| No reasoning | "BUY 73%" — why? | 4 analysts debate, Bull/Bear argue, Judge decides with evidence |
| No self-correction | Same mistakes repeated | Bias tracker records errors and can adjust confidence |
| Static analysis | Can't test hypotheticals | "What if Fed hikes 50bp?" — scenario simulation with swarm |
| Expensive AI | Every call uses one tier | Routes eligible steps by model tier; cost depends on actual token usage |
| Manual workflow | Notebook → read → decide → execute | Analysis and an explicitly requested Alpaca paper order are separate paths |
| No context | Each stock analyzed alone | GNN propagates signals across 17 related stocks |
| Not shareable | Screenshot your terminal | "Copy for X" on every section |

---

## Orallexa vs ai-hedge-fund

Inspired by [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund). We share the multi-agent philosophy but take different approaches:

| Feature | ai-hedge-fund | Orallexa |
|---------|:------------:|:--------:|
| ML Models | 0 (LLM-only) | 9 (RF, XGB, EMAformer, MOIRAI-2, Chronos-2, DDPM, PPO RL, GNN, LR) |
| Model Ranking | No | Auto-ranked by Sharpe ratio |
| LLM Providers | OpenAI, Groq, Anthropic, DeepSeek | Claude Sonnet + Haiku (dual-tier routing) |
| Real-time Dashboard | Basic web UI | Next.js 16 with WebSocket, Art Deco theme |
| Paper Trading | No execution | Alpaca bracket orders (stop-loss + take-profit) |
| Daily Intelligence | No | 50+ tickers, sector rotation, AI morning brief |
| Desktop Assistant | No | Pixel bull with voice (Whisper + TTS) |
| Social Content | No | One-click "Copy for X" on every section |
| Walk-Forward Eval | No | New 90-pair cost-aware evaluation pending pinned data |
| Bilingual | No | EN/ZH |

---

## Tech Stack

<table>
<tr><td><b>Frontend</b></td><td>Next.js 16, React 19, Tailwind CSS 4, PWA</td></tr>
<tr><td><b>Backend</b></td><td>FastAPI, Python 3.11, WebSocket</td></tr>
<tr><td><b>AI</b></td><td>Claude Sonnet 4.6 + Haiku 4.5 (dual-tier routing)</td></tr>
<tr><td><b>ML</b></td><td>scikit-learn, XGBoost, PyTorch (EMAformer, DDPM, GAT, PPO)</td></tr>
<tr><td><b>Data</b></td><td>yfinance (real-time + historical), parquet cache layer (`ORALLEXA_USE_CACHE=1`)</td></tr>
<tr><td><b>NLP</b></td><td>FinBERT, VADER, TextBlob</td></tr>
<tr><td><b>Trading</b></td><td>Alpaca paper trading (bracket orders)</td></tr>
<tr><td><b>Orchestration</b></td><td>LangGraph (stateful debate pipeline)</td></tr>
<tr><td><b>Deploy</b></td><td>Docker, GitHub Actions CI/CD, Vercel</td></tr>
</table>

---

## Testing

Run the current suites to obtain counts and coverage for this checkout. CI
runs on pushes to `master` and pull requests targeting `master`; its backend
job excludes selected long-running or external-call tests. The coverage gate
is **70% over modules included by `.coveragerc`**, not a repository-wide
coverage measurement.

```bash
python -m pytest tests/ -v                     # Backend; environment may require external dependencies
(cd orallexa-ui && npm ci && npm test)         # Frontend unit tests
(cd orallexa-ui && npm run test:coverage)      # Frontend coverage
(cd orallexa-ui && npx playwright test)        # E2E; install browsers if needed
```

---

## API

<details>
<summary><b>Endpoints</b></summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/analyze` | Fast signal analysis (scalp/intraday/swing) |
| `POST` | `/api/deep-analysis` | Multi-agent deep analysis with debate |
| `POST` | `/api/chart-analysis` | Screenshot chart analysis (Claude Vision) |
| `POST` | `/api/watchlist-scan` | Parallel multi-ticker scan |
| `GET` | `/api/daily-intel` | Daily market intelligence (cached) |
| `GET` | `/api/news/{ticker}` | News + sentiment scores |
| `GET` | `/api/profile` | Trader behavior profile |
| `GET` | `/api/journal` | Decision execution log |
| `POST` | `/api/scenario` | What-if scenario simulation |
| `GET` | `/api/bias-profile` | Prediction bias analysis |
| `GET` | `/api/role-memory` | Role learning progress |
| `POST` | `/api/swarm-sim` | Agent swarm simulation |
| `POST` | `/api/evolve-strategies` | LLM strategy evolution |
| `GET` | `/api/alpaca/account` | Paper trading account |
| `POST` | `/api/alpaca/execute` | Execute signal as paper order |
| `WS` | `/ws/live` | Real-time price + signal stream |
| `GET` | `/healthz` | Liveness probe for Docker / K8s (no auth, no I/O) |

</details>

---

## Ships with Claude Code skills

This repo includes `.claude/skills/` — drop the folder into any Claude Code project and the agent learns these patterns automatically:

- `.claude/skills/tier-router/` — route Haiku for structured, Sonnet for reasoning ([standalone](https://github.com/alex-jb/claude-tier-router))
- `.claude/skills/adversarial-debate/` — Advocate/Critic/Judge over any decision ([standalone](https://github.com/alex-jb/claude-debate))

Both skills are self-contained: copy the folder, no install needed.

---

## Project Structure

<details>
<summary><b>Directory layout</b></summary>

```
orallexa/
├── api_server.py               # FastAPI + WebSocket server
├── docker-compose.yml          # One-click deployment
│
├── engine/                     # Trading engine (9 models + intelligence)
│   ├── multi_agent_analysis.py # Multi-agent pipeline (debate + panel + fusion + token-budget gates)
│   ├── signal_fusion.py        # 8-source signal fusion (tech/ML/news/options/institutional/social/earnings/polymarket)
│   ├── source_accuracy.py      # Per-source accuracy ledger (JSONL)
│   ├── dynamic_weights.py      # Accuracy → weight scaling for fusion
│   ├── token_budget.py         # Client-side token + USD budget enforcer
│   ├── context_compressor.py   # Extractive / LLM compression of chained agent text
│   ├── kronos_signal.py        # Kronos foundation-model wrapper (10th ML voice)
│   ├── shared_memory.py        # CORAL-style read aggregator (role + layered memory)
│   ├── historical_cache.py     # Prices / earnings / options cache schema
│   ├── news_aggregator.py      # Google News + Yahoo RSS dedupe
│   ├── layered_memory.py       # FinMem-style short/mid/long memory tiers
│   ├── regime_strategist.py    # Regime → strategy + params recipe
│   ├── portfolio_manager.py    # Final approval gate — concentration, sector, sizing
│   ├── earnings.py             # Earnings calendar + PEAD drift stats
│   ├── scenario_sim.py         # What-if scenario simulation (Opus 4.7 + xhigh)
│   ├── bias_tracker.py         # Prediction bias self-correction
│   ├── role_memory.py          # Persistent role memory & learning
│   ├── micro_swarm.py          # 20-agent Monte Carlo swarm
│   ├── ml_signal.py            # Model comparison framework
│   ├── strategies.py           # 7 rule-based strategies
│   ├── emaformer.py            # EMAformer Transformer
│   ├── diffusion_signal.py     # DDPM probabilistic forecasting
│   ├── gnn_signal.py           # Graph Attention Network
│   ├── rl_agent.py             # PPO reinforcement learning
│   ├── strategy_evolver.py     # LLM strategy evolution
│   └── sentiment.py            # FinBERT / VADER
│
├── llm/                        # AI reasoning
│   ├── claude_client.py        # Tier routing (FAST/DEEP/OPUS) + DEEP_EFFORT=xhigh
│   ├── call_logger.py          # JSONL log + PostHog + Langfuse triple sink
│   ├── provider.py             # Multi-provider abstraction (Anthropic + OpenAI)
│   ├── debate.py               # Bull/Bear debate (Judge on Opus 4.7 + xhigh)
│   ├── perspective_panel.py    # 4-role analyst panel with memory
│   ├── regime_llm.py           # Claude-backed regime strategy llm_fn
│   └── dspy_judge.py           # DSPy Phase A scaffold (lazy import, no compile)
│
├── orallexa-ui/                # Dashboard (Next.js 16)
│   ├── app/components/         # 13 UI components (incl. RegimeCard, PortfolioManagerCard)
│   ├── app/__tests__/          # Vitest unit tests
│   └── e2e/                    # Playwright E2E tests
├── desktop_agent/              # Desktop AI coach
├── bot/                        # Execution layer (Alpaca)
├── tests/                      # Backend tests
├── scripts/                    # Demo + eval + cron utilities
│   ├── demo_pipeline_e2e.py    # Live fusion → decision → PM smoke test
│   ├── compare_fusion_variants.py  # 5-src vs 8-src on identical inputs
│   ├── backtest_fusion_partial.py  # Synthetic time-series weight-policy A/B
│   ├── eval_context_compression.py # Compression safety harness
│   └── update_source_outcomes.py   # Daily forward-return backfill
├── docs/                       # Architecture + module catalogs
│   ├── NEW_MODULES.md          # 11+ Phase 7/8/9 modules with enable steps
│   ├── DSPY_MIGRATION.md       # 3-phase plan to compile prompts via MIPROv2
│   └── SESSION_2026-04-24.md   # Resumable state for continuation work
└── .github/workflows/          # CI (lint/test/build/E2E) + source-outcomes cron
```

</details>

---

## Acknowledgments

[Anthropic Claude](https://anthropic.com) · [yfinance](https://github.com/ranaroussi/yfinance) · [Polymarket](https://polymarket.com) · [Alpaca](https://alpaca.markets)

---

<div align="center">

**MIT License** — see [LICENSE](LICENSE)

> **Disclaimer**: Research and educational project. Not financial advice.

<br>

**Built with conviction, not hype.**

</div>
