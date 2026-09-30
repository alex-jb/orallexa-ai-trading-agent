# Paper broker adapters

`bot.broker_adapter.BrokerAdapter` defines account, position, order, signal,
and close operations. `create_broker_adapter("alpaca")` is the only route to
broker execution. Its existing `AlpacaExecutor` sends **paper** requests and
retains market/bracket orders, sizing, and paper journal behavior. The six
`/api/alpaca/*` routes and the legacy daily pilot select Alpaca explicitly.

`create_broker_adapter("robinhood_dry_run")` returns an offline preview. It
does not read credentials, connect to Robinhood, retrieve account data,
calculate a trade quantity, or submit/cancel/close an order. Its responses
always identify `order_submitted: false`, and bracket orders are unsupported.
There is no live Robinhood adapter or `robinhood` factory selection.

```python
from bot.broker_adapter import create_broker_adapter

preview = create_broker_adapter("robinhood_dry_run").execute_signal(
    ticker="NVDA", decision="BUY", stop_loss=90, take_profit=120
)
assert preview["order_submitted"] is False
```

The existing Alpaca API routes remain Alpaca-specific; the Robinhood preview
has no HTTP execution route. The separate fixed-rule paper harness in the
paper-harness PR uses a narrower gateway for order and fill reconciliation.
Unifying that gateway after the PRs merge is follow-up work.
