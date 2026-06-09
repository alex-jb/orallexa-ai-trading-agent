# r/algotrading (or r/quant)

**Title**:
9-model trading research stack — and the false-positive backtest postmortem

**Body**:

OSS'd a multi-model trading research stack I've been building for 14 months: github.com/alex-jb/orallexa-ai-trading-agent

745+ tests, MIT. The architecture is conventional — 9 ML models concurrent (RF / XGB / EMAformer / DDPM / PPO / GAT / MOIRAI-2 / Chronos-2 / LogReg), rolling Sharpe-weighted ensemble, 5-voice LangGraph debate (Bull / Bear / Judge / Critic / Auditor) as the decision layer.

The interesting thing isn't the architecture. It's the **false-positive backtest postmortem**.

In late May the backtest reported +$5,950 / 60.9% win rate / 128 trades on the last 30 days. Looked legit. Then I built `scripts/walkforward.py` that slices the decision log into N sliding (train, test) windows and reports mean OOS Sharpe.

**Verdict: FAIL.** Mean OOS Sharpe -3.08. Worst-window Sharpe -4.23. Mean win rate 31.6%.

Root cause was three-layered:
1. The `+60.9% win` was in-sample eval with a hidden `--use-atr-stops` flag that wasn't being passed to the production cron
2. The entry rule is regime-blind momentum — buys when RSI > 60 + BB% > 0.7 (= classic momentum exhaustion), works in trending markets, fails in ranging markets like June 2026
3. The 5/29 backtest happened to run on the May rally window so in-sample fit was tautological

What I shipped to address it:
- **Anti-extension gate** in `skills/prediction.py` — caps the BUY score when 2+ extension signals fire simultaneously (RSI>60 + BB%>0.7 + MACD+ADX>25)
- **ADX-based regime gate** — TRENDING/RANGING/UNCERTAIN regimes get different rule sets
- **Walk-forward gate** — production paper P&L must pass mean OOS Sharpe > 0.5 across 4 windows before any real money

Current verdict is still FAIL. So no real money. Will re-run in 2 weeks with fresh data once the new entry rule has had time to generate new decisions.

The full diagnostic writeup is in `research/2026-06-08-markets-stack-deep-diagnosis.md` — 4 root causes named and dated.

What I'd love feedback on:
1. Has anyone seen detection methods for regime non-stationarity in entry-rule eval beyond ADX (Hurst exponent? variance ratio test?)
2. Is the walk-forward gate (mean OOS Sharpe > 0.5 across 4 windows) too strict / not strict enough for indie quant work?
3. The 5-voice debate layer — Bull / Bear / Judge / Critic / Auditor — has been the most useful addition for catching anchor bias. Curious if anyone has tried similar multi-agent debate patterns and what worked / didn't.

No newsletter, no Substack, no SaaS. Just a public repo + the postmortem.
