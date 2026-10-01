# New 90-pair evaluation protocol (declared 2026-09-29; amended 2026-09-30)

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
  The CLI requires the freeze manifest, verifies all requested CSV hashes,
  and keeps the default numerical report and JSON inside the ignored snapshot
  directory, without generated charts or any tracked repo outputs. Publish
  results together with licensed inputs only after checking redistribution
  rights. An
  incomplete run exits 2 and cannot support a claim.
- Walk-forward: 252 trading bars initial training, successive 63-bar OOS
  windows; causal indicators and stateful rules use all historical bars
  available through each test window, then report only the 63 OOS bars.
  Fixed strategy defaults.
  The rule-based strategies are *not* the multi-agent decision system.
- Returns: a signal made at close on day t is executed at the **next session's
  open**, t+1. Each independent OOS window starts from cash at its first open;
  a signal from the final training close may enter there, paying 10 bps
  transaction cost plus 10 bps slippage. No strategy return is credited for
  the preceding overnight period. Subsequent old positions earn overnight
  returns, and new positions earn open-to-close returns; both costs are
  charged per executed position change. The matched buy-and-hold comparator
  buys the same ticker at that first OOS open with identical entry costs,
  stays invested through that window, and does not pay an unexecuted final
  exit cost. Independent windows restart both portfolios from cash. A signal
  on the last bar cannot execute inside the dataset. This is a percentage-of-
  notional cost model, with no per-share fee, spread, borrow, taxes, partial
  fills, or market impact.
- Tests: the primary exploratory one-sided paired t-test uses OOS daily **net
  strategy return minus matched same-ticker buy-and-hold return**, including
  flat strategy days (H0: mean daily excess <= 0). Absolute net strategy
  return > 0 is retained as an uncorrected diagnostic and never contributes
  to a PASS. Bonferroni family-wise adjustment and BH FDR apply to primary
  excess p-values across **all 90 planned pairs**; unavailable pairs count
  as p=1. The t-test assumes independent daily paired excess returns;
  serial dependence can make p-values optimistic. BH's formal FDR guarantee
  also depends on assumptions about null p-values and their dependence.
  Correlated ticker and strategy results warrant caution. A PASS is an
  exploratory screen, never a validated edge; paper fills, a licensed
  independently reproducible cohort, and prospective testing remain necessary.
  The report exposes mean daily paired excess in basis points as an effect
  size on the same OOS days used by the test.
  (Protocol amendment 2026-09-30, before inspecting any numerical outcome:
  the 2026-09-29 draft incorrectly tested absolute net > 0 and attributed
  training-to-test overnight returns to newly fitted adaptive parameters.)
  Monte Carlo shuffling is descriptive, not an independent evidence gate.
- Do not label a strategy as having a validated trading edge from this run
  alone. Paper fills and forward behavior are separate tests.
- If any pair's walk-forward/statistical calculation fails or has insufficient
  observations, the CLI exits 2 without writing numerical report artifacts.

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
- A private harness run may point `--data-dir` to the private directory; the
  CLI writes numerical reports beside the ignored snapshots and rejects
  explicitly tracked repo outputs for Alpaca cohorts. Do not commit these
  generated numerical reports. Under this project's strict
  reproducibility rule, public numerical performance claims stay **blocked**
  until the full input data can be provided to independent reviewers under a
  suitable redistribution license. Code, hashes, and cost assumptions alone
  do not satisfy that rule.
