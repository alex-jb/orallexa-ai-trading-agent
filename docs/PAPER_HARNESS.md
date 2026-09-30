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
does not match its own saved state. The deterministic client order ID supports
same-day deduplication for a single loop. Before a new
paper order, the loop persists an `order_intent` event and the exact client ID,
side, quantity, prior-close signal price, rule version, the completed session
date when available, and a SHA-256 of the canonical last 50 *input close
values*. This hash is not proof of the raw Alpaca data or its publication
time. The harness does not currently enforce a maximum age for an otherwise
completed daily bar. Verify the feed and session date before starting an
unattended pilot. The state checkpoint and ledger append fsync their files and
containing directories (including newly created directories); a failed fsync
before submission prevents an order. This depends on the filesystem honoring
fsync and does not provide cross-host or concurrent-process coordination.
A disk failure while writing the intent prevents
submission. If an order is accepted and the process exits before storing its
broker ID, the next invocation looks up the saved ID before considering new
signals, including when that invocation has insufficient bars or happens on a
later day. Broker lookup visibility can lag the submission. A 404 or lookup
error leaves the intent unresolved: no automatic
resubmission with a new ID or new order on that ticker. Review the broker paper
account and ledger; this harness has no automated resolution action. `report()`
refuses to publish a comparison while an intent is unresolved. On a recovery
invocation, the original `intent_signal_price` is kept separately from today's
`signal_price`; the CLI withholds the aggregate report until a later run with
at least 50 completed bars and a verified broker position. This safety rule
may suspend a pilot even if a crash happened just before the request reached
the broker. A pending order is reconciled before any new decision, even when
market data is missing. State plus JSONL are not an atomic multi-worker
coordinator. Concurrent processes sharing the same state path are not
serialized by this harness; run a single instance per pilot.
After recovering an accepted order, the comparison remains withheld until a
later successful broker reconciliation **and position check**. A fill query
alone cannot clear a stale broker-state flag or validate the recorded P&L.
A completed order and a new opposite-side decision get separate ledger rows.
The saved state locks the share quantity: changing `--qty` requires a new pilot
with separate state and ledger paths. State created by older harness versions
without a saved quantity also requires a new pilot. Do not delete state while
orders are pending.

## Audit records

`logs/paper_harness.jsonl` is append-only and `logs/paper_harness_state.json`
stores positions, entry fill prices, pending order IDs, realized P&L, first
benchmark price, the first completed paper BUY order's fill schedule, peak
equity, the fixed quantity, unresolved intents, and one audit outbox row for
process-crash recovery. Both are gitignored. Every decision logs:

- UTC timestamp, ticker, signal, completed-bar signal price and SMA20/50;
- market order quantity, ID, status, newly accounted filled quantity and fill price;
- signed `signal_to_fill_drift_bps` versus the prior completed close. It includes
  overnight price gaps and intraday moves before submission, so it is **not**
  an execution slippage or market-impact estimate;
- assumed paper commission (`fees_usd=0`, labeled as an assumption), realized
  P&L, strategy equity, peak-to-current drawdown, and benchmark P&L;
- scoped LLM API cost per week, always $0 because this loop never calls an LLM.

The pilot-start buy-and-hold benchmark assumes a **hypothetical purchase at the prior
completed close** on each ticker's first pilot day and holds the fixed share
quantity through the latest mark. That entry was not executable when the pilot
first ran after the next open. Its entry time and execution cost are therefore
not matched to the paper strategy, and the report does not establish an
apples-to-apples excess return. On an order day, its prior-close mark can also
precede that day's strategy fill; do not interpret that snapshot as a same-time
performance comparison. `report()` retains this legacy aggregate separately;
the per-ticker `first_date` records staggered starts.

The optional `conditional_comparison` diagnostic begins with the strategy's
**first fully filled paper BUY order**. The hypothetical buy-and-hold portfolio
mirrors that order's fill quantities and weighted average fill price (including
partial fills), then holds the fixed number of shares. No extra order is sent.
Its reported strategy P&L excludes any realized P&L before this entry. The
diagnostic uses the date attached to the latest completed daily bar and only
reports a value when that date is strictly **after** the last observed paper
fill date in New York. It therefore withholds comparisons on fill days and
when the bar date is unknown. `report()` exposes per-ticker results and an
aggregate only if **every started ticker** has an eligible later mark; it lists
exclusion reasons otherwise. Tickers that never complete a paper BUY order
cannot enter this diagnostic. If an early BUY partially fills and terminates
before the fixed share quantity is acquired, this ticker is excluded from the
conditional diagnostic for the rest of that pilot, even if it buys again later.
The earlier fill would otherwise make the later entry schedule ambiguous.

This diagnostic has **selection bias**: it selects only tickers after the
strategy chose to BUY and omits the initial flat period. Its entry price is a
paper fill reused for a hypothetical holding portfolio, not an independently
executed buy-and-hold order. It is not a full-pilot comparison or evidence of
excess return. Dates recorded for fills are conservative observation times,
which can be later than Alpaca's actual execution times. The same omitted
dividends and transaction-cost limitations below apply to both benchmarks.

**Alpaca paper fills are simulated.** Alpaca says its simulator omits market
impact, order information leakage, latency-driven slippage, price improvement,
regulatory fees, and dividends; queue position is also omitted for
nonmarketable limit orders, though this pilot uses market orders. It may fill
a quantity larger than the actual displayed liquidity. Therefore neither this
pilot's fill-to-signal drift nor an apparent win over the conditional benchmark
measures a live executable edge. The feed here is IEX daily bars for signals;
paper fills and a consolidated SIP history are distinct evidence sources.
These limitations apply even after several months of paper observations.
See [Alpaca's paper trading specification](https://docs.alpaca.markets/us/v1.4.2/docs/paper-trading).

Actual Alpaca market orders
can fill later or partially; pending orders retain their state until a final
status is reconciled. If the state checkpoint succeeds but the ledger append
fails, the saved audit row is replayed before the next broker decision;
an existing row is recognized by its event ID. A malformed ledger fails closed
and needs operator review. Fees other than assumed paper commission, spread,
dividends, interest, taxes, and external broker positions are not included.
Stock splits and other corporate actions are not reconciled into the local
cost basis or benchmark; a broker position mismatch blocks orders and requires
a fresh reviewed pilot rather than silently continuing. After a mismatch, the
affected ticker's comparison fields are withheld and `report()` refuses to
publish an aggregate containing it. A failed broker reconciliation or position
lookup also makes the comparison stale: `report()` refuses to publish until a
later successful reconciliation and broker position check restore verified
state. Do not treat a temporary broker error as a zero-fill day.
This is a prospective paper test; no live fill record or measured edge exists
until the pilot actually runs.

The older `scripts/run_daily_pilot.py` calls Claude and is **not** this fixed-rule
loop. Do not schedule both pilots together; its LLM calls are not included in
the $0/week figure above. The new harness does not claim to cap that separate
legacy script.

Alpaca SDK references: [paper TradingClient](https://alpaca.markets/sdks/python/api_reference/trading/trading-client.html),
[stock bars](https://alpaca.markets/sdks/python/api_reference/data/stock/historical.html),
and [StockBarsRequest](https://alpaca.markets/sdks/python/api_reference/data/stock/requests.html).
