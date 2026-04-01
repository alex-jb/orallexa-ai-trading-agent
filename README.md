<div align="center">

<img src="assets/avatar/bull_idle.png" alt="Orallexa — Art Deco Wall Street Bull" width="120">

# Orallexa

### An AI Trading System Where Models Debate Before Making Decisions

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=next.js)](https://nextjs.org)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4-cc785c?style=flat-square)](https://anthropic.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

Most AI trading tools ask one model to predict the market.
**Orallexa makes them argue first.**

A Bull analyst builds the case. A Bear analyst tears it apart.
A Judge weighs both sides and makes the final call.
The result: decisions that survive scrutiny before any capital is at risk.

[English](#example--nvda-analysis) | [中文](README_CN.md) | [Presentation](presentation.html)

---

🚀 [How It Works](#how-it-works) | 📊 [Example Output](#example--nvda-analysis) | ⚡ [Quick Start](#quick-start) | 🔍 [Why Orallexa](#why-orallexa-is-different) | 📡 [API](#api-reference) | 🎓 [Presentation](#presentation) | 🤝 [Contributing](#contributing)

</div>

---

## Example — NVDA Analysis

Here's what Orallexa produces for a single stock analysis. This is real output structure, not a mockup:

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
│  • MACD histogram rising — momentum accelerating                │
│                                                                 │
│  BEAR CASE:                                                     │
│  • ADX at 32 but declining — trend may be exhausting            │
│  • Bollinger %B at 0.85 — extended near upper band              │
│  • Sector (XLK) up 3 days straight — mean reversion risk        │
│  • Earnings in 12 days — vol crush after event                  │
│                                                                 │
│  JUDGE VERDICT:                                                 │
│  "Bull case is stronger — momentum and volume confirm the       │
│   trend. But the Bear's earnings risk is valid. Position         │
│   size should be reduced. BUY with tight stop at MA20."         │
│                                                                 │
│  PROBABILITIES: Up 58% | Neutral 24% | Down 18%                │
│                                                                 │
│  RISK PLAN:                                                     │
│  Entry: $132.50 | Stop: $128.40 | Target: $141.00 | R:R 2.1:1  │
│  Position: 5% of portfolio | Key risk: Earnings vol event       │
└─────────────────────────────────────────────────────────────────┘
```

Every decision comes with bull arguments, bear counterarguments, a reasoned verdict, probability breakdown, and a concrete risk plan. Not a number — a structured argument.

---

## Why Orallexa Is Different

| Approach | Traditional AI Trading | Orallexa |
|----------|----------------------|----------|
| Decision making | ❌ Single model predicts direction | ✅ Bull & Bear debate, Judge decides |
| Reasoning | ❌ Black-box confidence score | ✅ Transparent argument chain you can read |
| Model usage | ❌ One expensive model for everything | ✅ Dual-tier routing — fast model for structure, deep model for reasoning |
| Cost control | ❌ Burn tokens on every call | ✅ Token-optimized with effort tuning and retry handling |
| Output | ❌ "BUY 73% confidence" | ✅ Bull case + Bear case + Judge verdict + risk plan |
| Product layer | ❌ Scripts and notebooks | ✅ Dashboard, desktop assistant, daily intelligence, voice analysis |

---

## Orallexa vs Other AI Trading Agents

| Feature | Typical AI Trading Bots | Orallexa |
|---------|:----------------------:|:--------:|
| Decision making | Single model prediction | Multi-agent adversarial debate |
| Reasoning | Black-box confidence score | Transparent Bull/Bear argument chain |
| ML models | 1-2 models | 9 models (RF, XGB, EMAformer, MOIRAI-2, DDPM, PPO RL, GNN, ...) |
| Model routing | One model for all tasks | Dual-tier: Haiku (fast) + Sonnet (deep) |
| Cost control | Burn tokens on every call | Token-optimized with effort tuning and caching |
| Strategy evolution | Manual parameter tuning | LLM generates, tests, and evolves strategy code |
| Inter-stock signals | Analyze stocks in isolation | GNN graph propagation across 17 related stocks |
| Risk management | Basic stop-loss | Structured investment plan with entry/stop/target/R:R |
| Dashboard | CLI or notebook | Real-time Next.js dashboard, Art Deco theme, EN/ZH bilingual |
| Voice assistant | None | Desktop AI coach with Whisper + TTS + chart screenshot |
| Testing | Ad hoc | 113 automated tests + CI/CD on every push |
| Deployment | Manual setup | Docker one-click + PWA mobile support |
| Live data | REST polling | WebSocket real-time price + signal stream |
| Trade execution | None | Alpaca paper trading with bracket orders |
| Social sharing | None | Per-section "Copy for X" — one-click post to Twitter |

---

## How It Works

<p align="center">
  <img src="assets/architecture.svg" alt="Orallexa Architecture" width="100%">
</p>

Orallexa runs a **5-agent pipeline** for every analysis:

| Agent | Role | Model |
|-------|------|-------|
| **Technical Analyst** | 7 strategies + indicators (RSI, MACD, Bollinger, ADX, MA alignment) | Local |
| **ML Engine** | RF, XGBoost, LR, EMAformer, MOIRAI-2, Chronos-2, DDPM Diffusion, PPO RL | Local |
| **Graph Neural Network** | GAT inter-stock signal propagation (17-stock relationship graph) | Local |
| **Sentiment Analyst** | FinBERT/VADER scoring on live news headlines | Local |
| **Bull + Bear Debate** | Adversarial argument — Bull argues FOR, Bear argues AGAINST | Claude Haiku (fast) |
| **Judge** | Synthesizes both sides → final decision + probabilities + investment plan | Claude Sonnet (deep) |

The first three agents run locally with zero API cost. Only the debate and judgment require LLM calls — and they use dual-tier routing to minimize spend.

### Adversarial Debate Pipeline

<p align="center">
  <img src="assets/multi_agent_debate.svg" alt="Bull/Bear Debate" width="85%">
</p>

Both analysts see the same data. The Bull builds a 300-400 word case with numbered arguments. The Bear directly counters each point. The Judge weighs both, then outputs a structured `DecisionOutput` with decision, confidence, probability breakdown, reasoning chain, and investment plan.

---

## Core Innovations

### 1. Adversarial Debate Reasoning

Instead of asking one model "should I buy?", Orallexa creates a structured argument:

- **Bull** is forced to find the strongest case FOR the trade
- **Bear** must counter with specific risks and weaknesses
- **Judge** can't be lazy — both sides present evidence

This catches blind spots that single-model systems miss.

### 2. Dual-Tier Model Routing

Not every task needs the most expensive model:

| Task | Model | Speed | Why |
|------|-------|-------|-----|
| JSON parsing, quick summaries | **Haiku 4.5** (FAST) | ~0.5s | Structure doesn't need deep reasoning |
| Bull/Bear arguments | **Haiku 4.5** (FAST) | ~1s | Argumentation from data, not deep synthesis |
| Judge verdict, deep analysis | **Sonnet 4** (DEEP) | ~3s | Final decision needs maximum reasoning |
| Signal refinement overlay | **Haiku 4.5** (FAST) | ~0.5s | Quick sanity check on technical signal |

Result: same quality decisions at a fraction of the cost.

### 3. Daily Market Intelligence

Every morning, Orallexa autonomously:
1. Scans 50+ tickers for price movers (parallel, ~5s)
2. Detects volume spikes (2x+ average = institutional activity)
3. Maps sector rotation across 13 ETFs
4. Generates a 300-400 word AI morning brief
5. Picks 3-5 "worth watching" tickers with specific catalysts
6. Produces a ready-to-post social thread

<p align="center">
  <img src="assets/daily_intel_pipeline.svg" alt="Daily Intel" width="90%">
</p>

### 4. Deep Learning Model Zoo

Orallexa runs **9 models** and compares them automatically:

| Model | Type | How It Works | Zero-Shot? |
|-------|------|-------------|:----------:|
| **Random Forest** | Classification | 28 technical features → 5-day direction | No |
| **XGBoost** | Classification | Gradient-boosted trees on same features | No |
| **Logistic Regression** | Classification | Linear baseline with regularization | No |
| **EMAformer** | Transformer | iTransformer + Channel/Phase/Joint embeddings (AAAI 2026) | No |
| **MOIRAI-2** | Foundation | Salesforce zero-shot time series model | Yes |
| **Chronos-2** | Foundation | Amazon T5-based probabilistic forecaster | Yes |
| **DDPM Diffusion** | Generative | Denoising diffusion → 50 price paths → VaR/CI | No |
| **PPO RL Agent** | Reinforcement | Gymnasium env with Sharpe reward + auto stop-loss | No |
| **GNN (GAT)** | Graph | 17-stock relationship graph, inter-stock signal propagation | No |

All models run on CPU. Results are ranked by Sharpe ratio and displayed in the ML Scoreboard.

### 5. LLM Strategy Evolution

Inspired by NVIDIA's AVO research — LLM generates, tests, and evolves trading strategies:

1. Claude generates Python strategy code (vectorized pandas operations)
2. Code is sandbox-executed on training data
3. Backtested on held-out test data
4. Top performers fed back to LLM for mutation/combination
5. Repeat for N generations

### 6. LangGraph Debate Pipeline

The Bull/Bear debate now runs on a LangGraph StateGraph:
- Typed state flowing through nodes
- Conditional routing (WAIT signals skip debate entirely)
- Observable execution for debugging

### 7. System Optimization

Orallexa is built for production reliability and cost efficiency:

| Optimization | What It Does |
|-------------|-------------|
| **max_tokens control** | Each call has a tuned token budget — no waste on verbose responses |
| **Dual-model routing** | Haiku for 80% of calls, Sonnet only where reasoning quality matters |
| **Response caching** | Daily intel cached per day, only regenerates when date changes |
| **Retry handling** | Graceful degradation on API overload — falls back to technical-only signals |
| **Confidence guardrails** | Hard cap at 82% confidence — no model can claim certainty |
| **Edge guards** | Weak, stale, or conflicting signals auto-convert to WAIT |

---

## Dashboard

<p align="center">
  <img src="assets/screenshots/dashboard_preview.png" alt="Dashboard" width="90%">
</p>

Two views in one UI:

- **Signal View** — Run analysis on any ticker. Decision card, probability bars, risk management, multi-timeframe confirmation, watchlist scanning, breaking alerts, live price refresh.
- **Intel View** — Daily market intelligence. Morning brief, gainers/losers, sector heatmap, volume spikes, AI picks, social thread with copy buttons.

Art Deco Gatsby theme — gold on noir, 1920s geometric elegance. Polymarket-inspired probability display. Mobile responsive. Full EN/ZH bilingual.

---

## Desktop AI Coach

A floating desktop assistant for hands-free trading analysis:

- Chat with Claude AI in natural language
- Voice input (Whisper) + voice output (TTS)
- Screenshot any chart → Claude Vision analysis (Ctrl+Shift+S)
- Decision card with entry, stop, target, risk/reward
- System tray for quick ticker/mode switching

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+

### 1. Clone & Install

```bash
git clone https://github.com/alex-jb/orallexa-ai-trading-agent.git
cd orallexa
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

```bash
export ANTHROPIC_API_KEY=...       # Anthropic (Claude) — required
export OPENAI_API_KEY=...          # OpenAI (Whisper/TTS) — optional, voice only
```

| Provider | Get Key | Required |
|----------|---------|----------|
| **Anthropic** | [console.anthropic.com](https://console.anthropic.com/) | Yes |
| **OpenAI** | [platform.openai.com](https://platform.openai.com/) | Desktop voice only |

### 3. Run

```bash
# API server
python api_server.py

# Dashboard (new terminal)
cd orallexa-ui && npm install && npm run dev
```

### Docker (One Command)

```bash
docker compose up --build
# API → localhost:8002 | UI → localhost:3000
```

### Quick Test

```bash
curl -X POST http://localhost:8002/api/analyze \
  -F "ticker=NVDA" -F "mode=intraday" -F "timeframe=15m"
```

---

## Inspiration

Orallexa is inspired by multi-agent trading research. The core idea: **multiple specialized agents produce better trading decisions than any single model.**

We extend this from research into a **deployable product** — with a real-time dashboard, 9 ML models, cost-aware model routing, LLM strategy evolution, voice-enabled desktop assistant, and Docker-ready deployment. The goal isn't just to run experiments, but to build something traders can actually use every day.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 16, React 19, Tailwind CSS 4 |
| **Backend** | FastAPI, Python 3.11 |
| **AI Reasoning** | Claude Sonnet 4 + Claude Haiku 4.5 (dual-tier) |
| **Machine Learning** | scikit-learn, XGBoost, PyTorch (EMAformer, DDPM, GAT, PPO) |
| **Market Data** | yfinance (real-time + historical) |
| **NLP** | FinBERT, VADER, TextBlob |
| **Trading** | Alpaca paper trading (bracket orders) |
| **Real-time** | WebSocket live price + signal stream |
| **Desktop** | Tkinter, OpenAI Whisper + TTS |
| **Deployment** | Docker, Docker Compose, GitHub Actions CI/CD |
| **Mobile** | PWA (installable, standalone) |

---

## Testing

```bash
# Run all tests (108 pass, ~3 min)
python -m pytest tests/ -v

# Fast tests only (~20s)
python -m pytest tests/ -v -k "not ml_regression"

# ML regression tests (~5 min, trains all models)
python -m pytest tests/test_ml_regression.py -v
```

| Suite | Tests | Coverage |
|-------|-------|----------|
| `test_engine_integration` | 34 | TA indicators, 6 strategies, backtest, Brain routing, alerts |
| `test_ml_regression` | 13 | RF, XGB, LR, EMAformer, Diffusion, RL, full pipeline |
| `test_api_e2e` | 19 | All API endpoints via FastAPI TestClient |
| `test_behavior` | 14 | Trade tracking, aggressiveness adaptation |
| `test_decision` | 8 | DecisionOutput dataclass |
| `test_risk_management` | 8 | Position sizing, stop-loss |
| `test_scalping` | 13 | Scalping skill indicators + signals |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/analyze` | Fast signal analysis (scalp/intraday/swing) |
| `POST` | `/api/deep-analysis` | Multi-agent deep analysis with debate |
| `POST` | `/api/chart-analysis` | Screenshot chart analysis (Claude Vision) |
| `POST` | `/api/watchlist-scan` | Parallel multi-ticker scan |
| `GET` | `/api/daily-intel` | Daily market intelligence (cached) |
| `POST` | `/api/daily-intel/refresh` | Force regenerate daily intel |
| `GET` | `/api/live/{ticker}` | Live price + last signal |
| `GET` | `/api/news/{ticker}` | News + sentiment scores |
| `GET` | `/api/breaking-signals` | Probability shift alerts |
| `GET` | `/api/profile` | Trader behavior profile |
| `GET` | `/api/journal` | Decision execution log |
| `POST` | `/api/evolve-strategies` | LLM strategy evolution (gen x pop) |
| `GET` | `/api/alpaca/account` | Paper trading account info |
| `GET` | `/api/alpaca/positions` | Open positions |
| `POST` | `/api/alpaca/execute` | Execute signal as paper order |
| `POST` | `/api/alpaca/close/{ticker}` | Close position |
| `WS` | `/ws/live` | Real-time price + signal stream |

---

## Project Structure

```
orallexa/
├── api_server.py               # FastAPI — 11 REST endpoints
├── docker-compose.yml          # One-click deployment
│
├── engine/                     # Trading engine
│   ├── multi_agent_analysis.py # 5-agent pipeline
│   ├── strategies.py           # 7 technical strategies
│   ├── ml_signal.py            # ML model comparison (9 models)
│   ├── emaformer.py            # EMAformer Transformer (AAAI 2026)
│   ├── diffusion_signal.py     # DDPM probabilistic forecasting
│   ├── gnn_signal.py           # Graph Attention Network
│   ├── rl_agent.py             # PPO reinforcement learning
│   ├── strategy_evolver.py     # LLM strategy evolution
│   ├── sentiment.py            # FinBERT / VADER
│   └── evaluation.py           # Sharpe, drawdown, metrics
│
├── llm/                        # Claude AI
│   ├── claude_client.py        # Dual-tier routing
│   ├── debate.py               # Bull/Bear debate (direct)
│   ├── debate_graph.py         # LangGraph debate pipeline
│   ├── strategy_generator.py   # LLM strategy proposals
│   └── ui_analysis.py          # Analysis prompts
│
├── orallexa-ui/                # React dashboard
│   ├── app/page.tsx            # Signal + Intel views
│   └── app/globals.css         # Art Deco theme
│
├── desktop_agent/              # Desktop AI coach
│   ├── main.py                 # Entry + hotkeys
│   └── chat_popover.py         # Chat window
│
├── bot/                        # Trading bot
│   ├── behavior.py             # Adaptation
│   ├── paper_trading.py        # Paper trading journal
│   ├── alpaca_executor.py      # Alpaca paper order execution
│   └── alerts.py               # Price alert system
│
├── tests/                      # 113 automated tests
│   ├── test_engine_integration.py
│   ├── test_ml_regression.py
│   └── test_api_e2e.py
│
├── .github/workflows/
│   ├── ci.yml                  # Tests + lint + build on push
│   └── pages.yml               # Presentation deploy
│
├── Dockerfile                  # API container
├── docker-compose.yml          # One-click deploy
└── requirements-docker.txt     # Container-specific deps
```

---

## Follow the Project

We publish daily AI-generated market intelligence and development updates:

- **X/Twitter**: [@orallexa](https://x.com/orallexa) *(coming soon)*
- **Daily Intel**: Generated every morning — top movers, volume spikes, AI picks, social-ready threads

---

## Star History

<div align="center">
<a href="https://www.star-history.com/#alex-jb/orallexa-ai-trading-agent&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=alex-jb/orallexa-ai-trading-agent&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=alex-jb/orallexa-ai-trading-agent&type=Date" />
   <img alt="Star History" src="https://api.star-history.com/svg?repos=alex-jb/orallexa-ai-trading-agent&type=Date" style="width: 80%; height: auto;" />
 </picture>
</a>
</div>

---

## Presentation

A 21-slide interactive presentation covering the full system — architecture, ML pipeline, deep learning models, multi-agent debate, and test coverage.

**View locally:**
```bash
# Open in browser
open presentation.html
# or on Windows
start presentation.html
```

**GitHub Pages:** After pushing to GitHub, enable Pages in repo settings and the presentation will be available at `https://alex-jb.github.io/orallexa-ai-trading-agent/presentation.html`

Keyboard controls: Arrow keys or click to navigate. 21 slides, ~15 min talk.

---

## Contributing

Contributions welcome:

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Commit (`git commit -m 'feat: add amazing feature'`)
4. Push (`git push origin feat/amazing-feature`)
5. Open a Pull Request

See [CHANGELOG.md](CHANGELOG.md) for development history.

---

## Acknowledgments

- [Anthropic Claude](https://anthropic.com) — AI reasoning engine
- [TradingAgents](https://github.com/TauricResearch/TradingAgents) — Multi-agent trading research inspiration
- [yfinance](https://github.com/ranaroussi/yfinance) — Market data
- [Polymarket](https://polymarket.com) — Probability-first UI inspiration

---

## License

MIT License — see [LICENSE](LICENSE).

> **Disclaimer**: Orallexa is a research and educational project. It is not financial advice. Always do your own research before making investment decisions.

---

<div align="center">

**If Orallexa helps your research, give it a ⭐**

</div>
