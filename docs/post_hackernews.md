# Show HN: Orallexa -- AI trading system where Bull and Bear agents debate before every decision

https://github.com/alex-jb/orallexa-ai-trading-agent

Instead of one model producing a signal, Orallexa spawns adversarial Bull/Bear LLM agents that argue over every trade. A Judge agent synthesizes both cases into a structured decision with confidence, probabilities, and a risk plan.

The debate is grounded in outputs from 9 ML models: RF, XGBoost, EMAformer (AAAI 2026 transformer), MOIRAI-2, Chronos-2, DDPM Diffusion, PPO RL, GNN with attention, and logistic regression as a calibration baseline.

A few things that might interest this crowd:

**LLM strategy evolution.** Inspired by NVIDIA's AVO -- the LLM generates trading strategies as Python functions, backtests them, and evolves the best performers through iterative mutation. Most generated strategies are bad, but the selection pressure produces interesting survivors.

**GNN inter-stock propagation.** A graph attention network models relationships across 17 related stocks (sector peers, supply chain links, macro ETFs). When one stock moves, the GNN propagates signals to correlated nodes. Adds meaningful edge on sector rotation days.

**Dual-tier Claude routing.** Haiku handles fast classification tasks (~$0.001/call), Sonnet handles deep reasoning and debate (~$0.003/call). Full analysis per ticker: ~$0.003.

**Stack:** Python backend, Next.js dashboard with WebSocket live data, Alpaca paper trading, Whisper voice input, Docker deployment. 113 tests, CI/CD.

The core insight: structured disagreement produces better decisions than consensus. The Bear agent regularly catches risks (earnings proximity, mean reversion signals, liquidity gaps) that a single-pass system misses.

MIT licensed. Would appreciate feedback on the adversarial agent architecture.
