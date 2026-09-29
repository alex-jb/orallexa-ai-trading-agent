# New 90-pair evaluation protocol (declared 2026-09-29)

The README's former eight-row table claimed 90 tests, but the repository
retained only a nine-pair NVDA report and an older 21-pair JSON. The source
OHLCV and the other 81 pair results were not retained. **Those numbers are
unverified; this protocol defines a new cohort, not a reconstruction.**

- Family: nine strategies in this fixed order: double_ma, macd_crossover,
  bollinger_breakout, rsi_reversal, trend_momentum, alpha_combo, dual_thrust,
  ensemble_vote, regime_ensemble. Ten tickers in this fixed order: NVDA,
  AAPL, TSLA, GOOG, META, INTC, QQQ, MSFT, AMZN, SPY. The later registered
  `vwap_reversion` is outside this 90-pair family. No post-result substitutions.
- Data: yfinance adjusted daily OHLCV, from 2021-01-01 through 2026-09-28
  inclusive. Commit the ten CSV files and `manifest.json` from
  `python -m eval.freeze_data` when the feed is available. Review CSV hashes
  before publishing results.
- Run: `python -m eval.run_harness --tickers NVDA,AAPL,TSLA,GOOG,META,INTC,QQQ,MSFT,AMZN,SPY --strategies double_ma,macd_crossover,bollinger_breakout,rsi_reversal,trend_momentum,alpha_combo,dual_thrust,ensemble_vote,regime_ensemble --data-dir eval/snapshots/2026-09-29 --seed 42 --no-adaptive`.
  Commit the resulting full `docs/evaluation_report.md` and JSON together
  with the inputs. An incomplete run exits 2 and cannot support a claim.
- Walk-forward: 252 trading bars initial training, successive 63-bar OOS
  windows with 50 prior bars for indicator warmup; fixed strategy defaults.
  The rule-based strategies are *not* the multi-agent decision system.
- Returns: prior-bar signal × daily close-to-close return; charge 10 bps
  transaction cost plus 10 bps slippage per unit of position change on entry
  and exit. This is a percentage-of-notional model, with no per-share fee.
  Results are net of those modeled costs, but do not model spread, borrow,
  taxes, partial fills, or market impact.
- Tests: one-sided t-test of all OOS daily net returns (including flat days).
  Bonferroni family-wise adjustment and BH FDR across **all 90 planned pairs**;
  unavailable pairs count as p=1. The t-test assumes independent daily
  observations and is exploratory when returns are serially dependent.
  Monte Carlo shuffling is descriptive, not an independent evidence gate.
- Do not label a strategy as having a validated trading edge from this run
  alone. Paper fills, forward behavior, and a matched buy-and-hold comparison
  are separate tests.
