# HN Show — Orallexa

**Title** (≤80 chars):
Show HN: Orallexa — 9-model trading research stack that caught its own false-positive backtest

**URL**:
https://github.com/alex-jb/orallexa-ai-trading-agent

**Body**:

I've been working on a multi-model trading research stack for the last 14 months. Single-developer project, 745+ tests, MIT license. The interesting story isn't the architecture — it's the false-positive backtest.

Architecture is conventional: 9 ML models running concurrently — Random Forest / XGBoost / EMAformer Transformer / DDPM diffusion / PPO RL / GAT / MOIRAI-2 / Chronos-2 / Logistic Regression — with a rolling Sharpe-weighted ensemble for the final decision. On top of that, a 5-voice LangGraph debate (Bull / Bear / Judge / Critic / Auditor) acts as the decision layer; every agent has a structurally different prior so anchor-bias and confirmation drift get adversarially probed before any verdict ships.

The interesting story:

In late May my backtest reported **+$5,950 / 60.9% win rate over 128 trades** on the last 30 days. Looked great. I almost moved real money in. Then I built a walk-forward validation framework (`scripts/walkforward.py`) that slices the decision log into N sliding (train, test) windows and reports mean Sharpe over out-of-sample tests.

Verdict: **FAIL**. Mean OOS Sharpe -3.08. Worst-window Sharpe -4.23. Mean win rate 31.6%.

Root cause: the `+60.9% win` was in-sample evaluation with an invisible `--use-atr-stops` flag that wasn't being passed to the production cron. The entry rule itself is regime-blind momentum — it buys at RSI > 60 + BB% > 0.7 simultaneously (= classic momentum exhaustion), which works in trending markets and fails catastrophically in ranging markets like June 2026.

Shipped fixes:
1. **Anti-extension gate** in the entry score function — reject BUY when 2+ extension signals fire simultaneously
2. **ADX-based regime gate** — clamp BUY signals during ranging markets (ADX < 18) and require pullback-to-MA20 during trending
3. **Walk-forward gate** — production paper P&L must hit mean OOS Sharpe > 0.5 across 4 windows before any real money trades

The walk-forward verdict on the current code is still FAIL. So no real money. The willingness to publish honest negative results is the point.

The diagnostic writeup is here: research/2026-06-08-markets-stack-deep-diagnosis.md inside the repo. Four root causes named and dated.

What I'd love feedback on:
- Has anyone seen literature on detecting regime non-stationarity in entry-rule eval beyond ADX?
- Is the walk-forward gate threshold (mean OOS Sharpe > 0.5) too strict / not strict enough for indie quant work?

745+ tests, MIT, single developer. No newsletter, no Substack, no SaaS — just a public research repo and the honest postmortem.
