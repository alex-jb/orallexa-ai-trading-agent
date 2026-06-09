# LinkedIn — Orallexa

I open-sourced a 14-month side project today: **Orallexa** — a 9-model trading research stack with 745+ tests.

The interesting part isn't the architecture. It's the false-positive backtest postmortem.

Three weeks ago my backtest reported +60.9% win rate over 128 trades. Looked great. I almost moved real money in. Then I built a walk-forward validation framework that slices the decision log into 4 sliding (train, test) windows and reports mean Sharpe over out-of-sample.

Verdict: **FAIL**. Mean OOS Sharpe -3.08. Worst-window Sharpe -4.23. Mean win rate 31.6%.

Root cause: the +60.9% was in-sample evaluation with an invisible `--use-atr-stops` flag, and the entry rule itself is regime-blind momentum that fails catastrophically in ranging markets like the one we're in.

I shipped fixes (anti-extension gate + ADX regime detection + walk-forward gate), but the current verdict is still FAIL. So no real money trades. The willingness to publish honest negative results is the point — calibration-honest evaluation is rarer than good models.

Architecture (for completeness):
🟢 9 models: RF / XGBoost / EMAformer / DDPM / PPO / GAT / MOIRAI-2 / Chronos-2 / LogReg
🟢 Rolling Sharpe-weighted ensemble for the final decision
🟢 5-voice LangGraph debate (Bull / Bear / Judge / Critic / Auditor) as the decision layer
🟢 745+ tests across ML regression, integration, parser/sizing/P&L logic
🟢 Brier audit at every prediction layer

Companion to two other OSS projects I shipped this week:
- council-diff — the 5-voice debate library extracted into a generic Brier-audited tool
- memory-wall-tracker — Brier-audited daily research feed on Druckenmiller's Q1 13F AI inference basket

Code: github.com/alex-jb/orallexa-ai-trading-agent (MIT)

For ML researchers and quants: the diagnostic writeup is in `research/2026-06-08-markets-stack-deep-diagnosis.md`. 4 root causes named and dated. The willingness to publish that doc is the entire point of this work.

What's the worst false-positive backtest you've caught (or shipped before catching)? Curious how others handle the eval-honesty discipline.
