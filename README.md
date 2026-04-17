<div align="center">

<img src="assets/logo.svg" alt="Orallexa" width="420">

<br>

### AI Trading Operating System

**9 ML models. Adversarial debate. One-click execution.**<br>
Don't guess the market. Let AI argue about it first.

<br>

[![Stars](https://img.shields.io/github/stars/alex-jb/orallexa-ai-trading-agent?style=for-the-badge&logo=github&color=D4AF37&logoColor=white)](https://github.com/alex-jb/orallexa-ai-trading-agent)
[![Python](https://img.shields.io/badge/Python-3.11+-1A1A2E?style=for-the-badge&logo=python&logoColor=D4AF37)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js_16-1A1A2E?style=for-the-badge&logo=next.js&logoColor=D4AF37)](https://nextjs.org)
[![Claude](https://img.shields.io/badge/Claude_Sonnet_4.6-1A1A2E?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSI+PGNpcmNsZSBjeD0iMTIiIGN5PSIxMiIgcj0iMTAiIGZpbGw9IiNEMkE5NzAiLz48L3N2Zz4=&logoColor=D4AF37)](https://anthropic.com)
[![CI](https://img.shields.io/github/actions/workflow/status/alex-jb/orallexa-ai-trading-agent/ci.yml?style=for-the-badge&logo=githubactions&logoColor=white&label=CI%20—%20Tests%20%26%20Build&color=22c55e)](https://github.com/alex-jb/orallexa-ai-trading-agent/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/698_Tests-Passing-22c55e?style=for-the-badge)](tests/)
[![License](https://img.shields.io/badge/MIT-1A1A2E?style=for-the-badge)](LICENSE)

<br>

[**Live Demo**](https://orallexa-ui.vercel.app) · [**Presentation**](https://alex-jb.github.io/orallexa-ai-trading-agent/presentation.html) · [**Evaluation Report**](docs/evaluation_report.md) · [**中文**](README_CN.md)

<br>

<img src="assets/showcase_demo.png" alt="Market Scan → AI Analysis → Decision" width="720">

</div>

<br>

## What makes this different

Most AI trading projects: feed data into a model, get a signal, done.

Orallexa runs a **multi-agent intelligence pipeline**. 4 AI analysts with different risk profiles debate the trade. A 20-agent swarm simulates market reactions. 5 independent signal sources vote. A bias tracker corrects the system's own mistakes. Then it executes.

```
Market Data → 9 ML Models → 4-Role Panel + Bull/Bear Debate
    → 5-Source Signal Fusion → Judge Verdict → What-If Scenarios
    → Risk Plan → Paper Execution → Dashboard → Social Content
```

Every stage automated. Every stage observable. The system learns from itself.

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

# Terminal 2: UI
cd orallexa-ui && npm install && npm run dev
```

Docker: `docker compose up --build` — that's it.

---

## Walk-Forward Evaluation (Out-of-Sample)

<!-- EVAL_TABLE_START -->
| Strategy | Ticker | OOS Sharpe | Verdict | p-value |
|----------|--------|-----------|---------|---------|
| rsi_reversal | INTC | **1.41** | PASS | 0.002 |
| dual_thrust | NVDA | **0.96** | PASS | 0.001 |
| alpha_combo | NVDA | **0.92** | PASS | 0.016 |
| macd_crossover | NVDA | **0.91** | PASS | 0.003 |
| ensemble_vote | NVDA | **0.90** | PASS | 0.001 |
| trend_momentum | NVDA | **0.74** | PASS | 0.005 |
| double_ma | GOOG | **0.64** | PASS | 0.049 |
| ensemble_vote | META | **0.31** | MARGINAL | 0.324 |
<!-- EVAL_TABLE_END -->

> 90 strategy-ticker pairs across 10 tickers and 9 strategies (including ensemble vote and regime-aware ensemble). 1 STRONG PASS, 7 PASS, 33 MARGINAL. [Full report →](docs/evaluation_report.md)

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
| **4-Role Perspective Panel** | Conservative / Aggressive / Macro / Quant analysts with persistent memory |
| **Adversarial Debate** | Bull/Bear/Judge via Claude Sonnet + Haiku |
| **5-Source Signal Fusion** | Technical + ML + News + Options Flow + Institutional data |
| **What-If Scenarios** | Claude simulates impact of hypothetical events on your portfolio |
| **20-Agent Micro Swarm** | Rule-based Monte Carlo convergence simulation |
| **Bias Self-Correction** | Tracks prediction accuracy, auto-adjusts confidence |
| **Strategy Evolution** | LLM generates Python strategies → sandbox tests → evolves winners |
| **Daily Intel** | 50+ tickers, sector rotation, volume spikes, AI morning brief |

</td>
<td width="50%">

### Execution Layer

| Component | Detail |
|-----------|--------|
| **Paper Trading** | Alpaca bracket orders with auto stop-loss/take-profit |
| **Real-time Stream** | WebSocket prices every 5s + signal change alerts |
| **Dashboard** | Next.js 16, Art Deco theme, EN/ZH bilingual |
| **Desktop Coach** | Floating AI pet with voice input (Whisper) + TTS, API retry + caching |

</td>
</tr>
</table>

---

## Example Output

What one NVDA analysis produces:

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

Not just a number. A structured argument with transparent reasoning and an actionable risk plan.

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

Not every task needs the expensive model:

| Task | Model | Cost |
|------|-------|------|
| Bull/Bear arguments | Haiku 4.5 | ~$0.001 |
| 4-Role perspective panel | Haiku 4.5 | ~$0.002 |
| Judge verdict | Sonnet 4.6 | ~$0.005 |
| Deep market report | Sonnet 4.6 | ~$0.005 |
| What-if scenario | Sonnet 4.6 | ~$0.005 |
| Signal fusion + swarm | Local (no LLM) | $0 |
| Bias tracking | Local (no LLM) | $0 |

**One full analysis: ~$0.005.** One daily intel report: ~$0.05.

> The dual-tier routing pattern (Haiku for structured, Sonnet for reasoning) has been extracted as a standalone Python package + Claude Code skill: **[claude-tier-router](https://github.com/alex-jb/claude-tier-router)** — `pip install claude-tier-router`

---

## Why this architecture

| Problem | Typical Approach | Orallexa |
|---------|-----------------|----------|
| Isolated signals | One model, one prediction | 5 sources fused: technical + ML + news + options + institutional |
| No reasoning | "BUY 73%" — why? | 4 analysts debate, Bull/Bear argue, Judge decides with evidence |
| No self-correction | Same mistakes repeated | Bias tracker detects overconfidence, auto-adjusts future calls |
| Static analysis | Can't test hypotheticals | "What if Fed hikes 50bp?" — scenario simulation with swarm |
| Expensive AI | Every call hits GPT-4 | Haiku for 80%, Sonnet only where reasoning matters |
| Manual workflow | Notebook → read → decide → execute | Automated: signal → debate → risk plan → paper order |
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
| Cost per Analysis | ~$0.03+ (single-tier) | ~$0.003 (80% Haiku, 20% Sonnet) |
| Real-time Dashboard | Basic web UI | Next.js 16 with WebSocket, Art Deco theme |
| Paper Trading | No execution | Alpaca bracket orders (stop-loss + take-profit) |
| Daily Intelligence | No | 50+ tickers, sector rotation, AI morning brief |
| Desktop Assistant | No | Pixel bull with voice (Whisper + TTS) |
| Social Content | No | One-click "Copy for X" on every section |
| Walk-Forward Eval | No | 70 strategy-ticker pairs, OOS Sharpe |
| Tests | Limited | 698 automated (261 frontend + 437 backend) |
| Bilingual | No | EN/ZH |

---

## Tech Stack

<table>
<tr><td><b>Frontend</b></td><td>Next.js 16, React 19, Tailwind CSS 4, PWA</td></tr>
<tr><td><b>Backend</b></td><td>FastAPI, Python 3.11, WebSocket</td></tr>
<tr><td><b>AI</b></td><td>Claude Sonnet 4.6 + Haiku 4.5 (dual-tier routing)</td></tr>
<tr><td><b>ML</b></td><td>scikit-learn, XGBoost, PyTorch (EMAformer, DDPM, GAT, PPO)</td></tr>
<tr><td><b>Data</b></td><td>yfinance (real-time + historical)</td></tr>
<tr><td><b>NLP</b></td><td>FinBERT, VADER, TextBlob</td></tr>
<tr><td><b>Trading</b></td><td>Alpaca paper trading (bracket orders)</td></tr>
<tr><td><b>Orchestration</b></td><td>LangGraph (stateful debate pipeline)</td></tr>
<tr><td><b>Deploy</b></td><td>Docker, GitHub Actions CI/CD, Vercel</td></tr>
</table>

---

## Testing

698 automated tests. 0 failures. CI on every push.

```bash
python -m pytest tests/ -v             # Backend (390 tests)
cd orallexa-ui && npm test             # Frontend (245 unit tests)
cd orallexa-ui && npm run test:coverage # Frontend with coverage
cd orallexa-ui && npx playwright test   # E2E (16+ specs)
```

<details>
<summary><b>Full test breakdown</b></summary>

| Suite | Tests | Coverage |
|-------|-------|----------|
| Engine Core | 62 | Backtest, 9 strategies, market analyst |
| Engine Integration | 34 | TA indicators, strategies, backtest, brain routing |
| ML/RL Signals | 20 | Feature extraction, RL env, PPO trainer |
| ML Regression | 13 | All 9 models — ensures upgrades don't degrade |
| API E2E | 19 | Every endpoint via FastAPI TestClient |
| Unit Tests | 47 | DecisionOutput, BehaviorMemory, risk, scalping |
| Desktop Agent | 30 | Intent detection, ticker/mode/TF extraction |
| Daily Intel | 10 | Price fetch, constants, cache path |
| Backend Other | 67 | Monte Carlo, walk-forward, regime, ensemble, statistics |
| Backend Misc | 88 | Param optimizer, strategy evolver, breaking signals |
| UI Components | 245 | All 14 component suites + hooks + mock data |
| Playwright E2E | 16+ | Dashboard, components, responsive, offline |
| **Total** | **635** | **437 backend + 245 frontend** |

</details>

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

</details>

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
│   ├── multi_agent_analysis.py # Multi-agent pipeline (debate + panel + fusion)
│   ├── signal_fusion.py        # 5-source signal fusion (tech/ML/news/options/institutional)
│   ├── scenario_sim.py         # What-if scenario simulation
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
│   ├── claude_client.py        # Dual-tier model routing
│   ├── debate.py               # Bull/Bear debate (with bias injection)
│   └── perspective_panel.py    # 4-role analyst panel with memory
│
├── orallexa-ui/                # Dashboard (Next.js 16)
│   ├── app/components/         # 11 UI components
│   ├── app/__tests__/          # 200 unit tests (vitest)
│   └── e2e/                    # 14 E2E tests (Playwright)
├── desktop_agent/              # Desktop AI coach
├── bot/                        # Execution layer (Alpaca)
├── tests/                      # ~180 backend tests
└── .github/workflows/          # CI/CD (lint, test, build, E2E)
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
