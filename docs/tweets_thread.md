# Orallexa Twitter/X Thread

## Tweet 1 (Hook)
What if your trading AI had to win a debate before placing a trade?

I built Orallexa -- a system where a Bull analyst and Bear analyst argue over every signal before a Judge makes the call.

Open source. Here's how it works:

## Tweet 2 (Problem)
Most AI trading tools: data in, signal out, trust the black box.

No reasoning. No counterargument. No "what could go wrong."

Single-perspective systems miss risks that are obvious in hindsight. The fix isn't a better model -- it's structured disagreement.

## Tweet 3 (Solution)
Orallexa runs 9 ML models (RF, XGBoost, EMAformer, MOIRAI-2, Chronos-2, Diffusion, PPO RL, GNN) then feeds results into an adversarial LLM debate.

Bull builds the case. Bear tears it apart. Judge synthesizes both into a decision with confidence + risk plan.

## Tweet 4 (Details)
The GNN propagates signals across 17 related stocks -- sector peers, supply chain, macro ETFs.

The LLM also generates, backtests, and evolves new strategies autonomously (inspired by NVIDIA AVO).

Cost per analysis: ~$0.003.

## Tweet 5 (CTA)
Real-time Next.js dashboard, Alpaca paper trading, voice input, 113 tests, Docker deployment.

MIT licensed. Star it, fork it, break it.

https://github.com/alex-jb/orallexa-ai-trading-agent
