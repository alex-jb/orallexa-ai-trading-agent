# Fixed-rule Alpaca paper harness

`bot/paper_harness.py` is a separate long-or-flat SMA20/50 pilot. It uses
**completed daily bars**, enters when SMA20 > SMA50, exits when SMA20 <= SMA50,
and submits at most the configured fixed share quantity per ticker. It does
not call Claude or any other model. Its `TokenBudget` has zero token and USD
caps, and its scoped LLM cost report is **$0/week**.

## Start in dry-run mode

Supply local CSVs with `Date,Close` (at least 50 completed bars per ticker):

```bash
python -m bot.paper_harness --bars-dir path/to/bars --tickers NVDA,AAPL
```

Or set **Alpaca paper** keys in the gitignored `.env` and use the Alpaca IEX
daily bar feed in dry-run mode. Local CSVs are forbidden when sending orders.

Only after checking the dry-run ledger, explicitly enable paper submission:

```bash
python -m bot.paper_harness --submit-paper --tickers NVDA,AAPL --qty 1
```

The gateway constructs `TradingClient(..., paper=True)` with no live URL
override. Submission is blocked when `DEMO_MODE` is on or the paper market is
closed. It never opens a short and refuses to touch a broker position that
does not match its own saved state. One deterministic client order ID per
ticker/side/day prevents retries from submitting a second order. A pending
order is reconciled before any new decision. Do not delete the state file while
orders are pending.

## Audit records

`logs/paper_harness.jsonl` is append-only and `logs/paper_harness_state.json`
stores positions, entry fill prices, pending order IDs, realized P&L, first
benchmark price, and peak equity. Both are gitignored. Every decision logs:

- UTC timestamp, ticker, signal, completed-bar signal price and SMA20/50;
- market order quantity, ID, status, cumulative filled quantity and fill price;
- signed adverse slippage in bps versus the prior completed close;
- assumed paper commission (`fees_usd=0`, labeled as an assumption), realized
  P&L, strategy equity, peak-to-current drawdown, and buy-and-hold P&L;
- scoped LLM API cost per week, always $0 because this loop never calls an LLM.

The benchmark holds the *same fixed share quantity* from each ticker's first
pilot day through its latest recorded mark. The strategy marks those same
tickers over that period, including flat days. `report()` aggregates dollar
P&L; the per-ticker `first_date` records staggered starts. Actual Alpaca
market orders can fill later or partially; pending orders retain their state
until reconciled. Fees other than assumed paper commission, spread, dividends,
interest, taxes, and external broker positions are not included in the P&L.
This is a prospective paper test; no live fill record or measured edge exists
until the pilot actually runs.

The older `scripts/run_daily_pilot.py` calls Claude and is **not** this fixed-rule
loop. Do not schedule both pilots together; its LLM calls are not included in
the $0/week figure above. The new harness does not claim to cap that separate
legacy script.

Alpaca SDK references: [paper TradingClient](https://alpaca.markets/sdks/python/api_reference/trading/trading-client.html),
[stock bars](https://alpaca.markets/sdks/python/api_reference/data/stock/historical.html),
and [StockBarsRequest](https://alpaca.markets/sdks/python/api_reference/data/stock/requests.html).
