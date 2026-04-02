# I built an AI trading system where a Bull and Bear analyst debate before every trade decision

**TL;DR:** Open-source trading intelligence system with 9 ML models, adversarial LLM debate, and a real-time dashboard. Not a black box -- every decision comes with transparent reasoning from both sides.

GitHub: https://github.com/alex-jb/orallexa-ai-trading-agent

---

## The problem with most AI trading systems

Most projects follow the same pattern: data in, signal out, done. You get a BUY or SELL with no explanation, no counterargument, no risk context. You're trusting a black box.

I wanted something different -- a system that **argues with itself** before making a decision.

## How the debate works

Every analysis spawns two LLM agents:

- **Bull analyst** -- builds the strongest case for why this trade should happen
- **Bear analyst** -- tears that case apart with counterarguments

Then a **Judge agent** weighs both arguments and produces a structured verdict with:
- Decision (BUY / SELL / WAIT)
- Confidence score
- Probability breakdown (up / neutral / down)
- Full risk plan (entry, stop, target, R:R ratio, position sizing)

It's not just vibes. The debate is grounded in real data from 9 ML models running underneath.

## The ML stack

The system runs these models and feeds their outputs into the debate:

| Model | Type | Role |
|-------|------|------|
| Random Forest | Classification | Baseline signal |
| XGBoost | Gradient boosting | Feature importance + signal |
| EMAformer | Transformer (AAAI 2026) | Temporal pattern recognition |
| MOIRAI-2 | Foundation model | Zero-shot time series forecasting |
| Chronos-2 | Foundation model | Probabilistic forecasting |
| DDPM Diffusion | Generative | Distribution-aware predictions |
| PPO RL | Reinforcement learning | Learned trading policy |
| GNN (GAT) | Graph neural network | Inter-stock signal propagation |
| Logistic Regression | Linear | Calibrated probability baseline |

The GNN component is particularly interesting -- it models relationships across 17 related stocks (sector peers, supply chain, macro ETFs) and propagates signals between them. So if NVDA moves, the system picks up implications for AMD, SMCI, etc.

## LLM strategy evolution

Inspired by NVIDIA's AVO paper -- the LLM doesn't just analyze, it **generates new trading strategies**, backtests them, and evolves the best performers. Think genetic algorithms but with an LLM as the mutation operator.

## Cost efficiency

Claude API calls use dual-tier routing:
- **Haiku** for fast tasks (data formatting, simple classification) -- ~$0.001/call
- **Sonnet** for deep reasoning (debate, strategy generation) -- ~$0.003/call

Full analysis of one ticker costs about $0.003. Running 50 tickers daily is under $0.15.

## Evaluation harness

Every strategy is tested with:
- **Walk-forward validation** (expanding window, per-window indicator computation with warmup buffer to prevent leakage)
- **Monte Carlo simulation** (1,000 iterations on trade returns only, not sparse daily returns)
- **Statistical significance** (t-test, bootstrap CI, Deflated Sharpe Ratio)

70 strategy-ticker pairs across 10 tickers. Auto-generated evaluation report with charts: https://github.com/alex-jb/orallexa-ai-trading-agent/blob/master/docs/evaluation_report.md

## Infrastructure

- Next.js real-time dashboard with WebSocket live data
- Alpaca paper trading integration for bracket orders
- Docker deployment, 127 automated tests, CI/CD pipeline
- Voice input (Whisper) + TTS for hands-free operation
- Desktop assistant with Art Deco theme (because why not)

## What I learned

1. **Adversarial debate > single model consensus.** The Bear agent catches risks that a single-pass analysis misses consistently.
2. **Foundation models (MOIRAI-2, Chronos-2) are surprisingly good** at zero-shot financial time series, but they need calibration against traditional models.
3. **LLM-generated strategies** occasionally produce creative approaches that a human wouldn't think of, but most are garbage. The evolution loop filters aggressively.
4. **GNN signal propagation** adds real alpha on sector rotation days.

---

Open source, MIT license. Feedback welcome -- especially on the debate mechanism and whether anyone has tried similar adversarial approaches.

https://github.com/alex-jb/orallexa-ai-trading-agent
