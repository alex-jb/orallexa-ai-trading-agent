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
- Data source for this original cohort (v1): yfinance adjusted daily OHLCV,
  from 2021-01-01 through 2026-09-28 inclusive. `python -m eval.freeze_data`
  writes ten CSV files and a manifest. Only publish the files if you have
  separately verified redistribution rights for the complete underlying
  market data. Keep them local otherwise. Review CSV hashes; do not publish
  numerical performance claims without data that readers may independently
  obtain and reproduce under an appropriate license.
- Run: `python -m eval.run_harness --tickers NVDA,AAPL,TSLA,GOOG,META,INTC,QQQ,MSFT,AMZN,SPY --strategies double_ma,macd_crossover,bollinger_breakout,rsi_reversal,trend_momentum,alpha_combo,dual_thrust,ensemble_vote,regime_ensemble --data-dir eval/snapshots/2026-09-29 --seed 42 --no-adaptive`.
  Publish the resulting full `docs/evaluation_report.md` and JSON together
  with licensed inputs only after checking redistribution rights. An
  incomplete run exits 2 and cannot support a claim.
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

## Alternative data protocol v2: Alpaca private historical bars

Declared 2026-09-30, before inspecting any Alpaca outcomes. This is a **new
data cohort**, never a reconstruction of v1 or the missing historical results.
The 90 predeclared strategy/ticker pairs, dates, fixed strategy parameters,
252/63-bar windows, costs, seed, and 90-test adjustments remain as specified
above. Changing from yfinance to Alpaca changes prices, volume, split/dividend
handling, and potentially the test results. **IEX and SIP themselves are two
distinct cohorts.** The IEX-only feed covers a fraction of US equity trading
and differs materially from consolidated prices; never label an IEX run as the
original Yahoo cohort or as a SIP run. Their protocol IDs are
`alpaca-iex-alternative-v2-declared-2026-09-30` and
`alpaca-sip-alternative-v2-declared-2026-09-30` respectively.

- The read-only command `python -m eval.freeze_alpaca_data` requests one ticker
  at a time from `GET https://data.alpaca.markets/v2/stocks/bars`, with
  `feed=iex` by default for paper-only accounts, `timeframe=1Day`,
  `adjustment=split,dividend`,
  `asof=2026-09-28` (META includes pre-rename FB), `start=2021-01-01`,
  request `end=2026-09-29T00:00:00Z`, and `sort=asc`. Alpaca's daily bar for
  September 28 is stamped at midnight New York (04:00 UTC during daylight
  saving time); requesting `end=2026-09-28` might exclude it. The manifest
  records the requested UTC boundary separately from the **required last
  trading session, 2026-09-28**. It follows pagination tokens and
  validates OHLCV values and complete, matching daily calendars. The manifest
  includes parameters, per-ticker hashes, capture time, and source. Keys are
  read from the existing ignored `.env`; use paper account credentials. The
  code cannot send any broker order. Alpaca says paper-only accounts are
  entitled to IEX market data:
  https://docs.alpaca.markets/us/v1.4.2/docs/paper-trading . `--feed sip`
  selects a separate cohort and must be used only if the account is actually
  entitled; unauthorized requests fail without creating a snapshot. Basic
  account historical plan descriptions should not be taken as proof of a
  paper-only account's SIP entitlement. No SIP data was fetched here.
- The output defaults to ignored `eval/private_snapshots/alpaca-iex-2026-09-28/`
  (or `alpaca-sip-2026-09-28/` with the explicit option);
  `eval/snapshots/` is also ignored. **Do not force-add or publicly commit the
  CSVs.** Alpaca says API market data cannot be redistributed:
  https://alpaca.markets/support/redistribute-alpaca-api . Keep permitted
  copies private and check the current provider agreement before use.
- A private harness run may point `--data-dir` to the private directory, but
  the current report generator also writes results/charts under `docs/`. Do
  not commit these generated numerical reports. Under this project's strict
  reproducibility rule, public numerical performance claims stay **blocked**
  until the full input data can be provided to independent reviewers under a
  suitable redistribution license. Code, hashes, and cost assumptions alone
  do not satisfy that rule.
