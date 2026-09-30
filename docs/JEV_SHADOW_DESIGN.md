# Jev news-event shadow experiment (design only)

**Status, 2026-09-29:** `TYPESAFE_API_KEY` is unavailable in this workspace.
This proposal does not install the SDK, call TypeSafe, or change any running
pipeline. No classification, latency, cost, or trading result has been measured.

## Placement and isolation

Read a snapshot of the already fetched, deduplicated news articles from
`engine/news_aggregator.py` in a separate offline runner. An alternative input
is the eight Yahoo headlines currently read by
`engine/multi_agent_analysis.py::_run_news_analyst`; freeze which source is used
before evaluating. Each item includes its original ticker, publication time,
provider, title, and URL. Resolve a ticker to a company name before the call;
the news text alone should not define the target company.

The runner writes to its own append-only JSONL file. It never writes into
`news_items`, `news_report`, `engine/signal_fusion.py` weights, the Bull/Bear
debate context, trade decisions, or broker execution. Existing news sentiment
and debate scheduling stay as they are. On a timeout, missing key, malformed
response, or budget exhaustion, record an error and leave the trading pipeline
untouched. Do not claim Jev saved a debate call while it runs in shadow mode.

## Engineering note on the "100x" illustration

A circulated September 2026 *Jev Engineering* screenshot sketches application
state -> typed decisions -> code validation and execution. That separation is
useful for this experiment: the news classifier may label a frozen article,
while deterministic code checks its schema, budget and audit record. Its first
page does not provide the benchmark data needed to establish a 100x gain, and
the original complete document has not been verified here.

[TypeSafe's published workflow evaluation](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
reports up to 193.6x lower latency and 444.6x lower cost on four workflows
constructed by its own team. The publisher calls these the high end of
expected real-world gains and notes possible selection bias. Those results
measure neither news classification in this repository nor an end-to-end
trading loop. Compare Jev with the frozen keyword and no-classifier baselines
below using the same inputs, errors, latency boundaries and price assumptions
before reporting any Orallexa speed or cost improvement. No return or alpha
claim follows from a classification result.

## External Jev trading demo

The [jev-trade repository](https://github.com/aowang-ai/jev-trade) is a
Hyperliquid crypto perpetual-futures bot, not an Alpaca stock strategy. Its
[README](https://github.com/aowang-ai/jev-trade/blob/main/README.md) defaults
to `MODEL=mock` and describes simulated fills when there is no private key;
its [example configuration](https://github.com/aowang-ai/jev-trade/blob/main/.env.example)
allows a private key and `HL_TESTNET=false` for mainnet orders. It does not
supply a comparable, reproducible stock backtest or a paper-only execution
contract. Do not copy its wallet or order-routing code into Orallexa. This
shadow design takes no trading-performance claim from that demonstration.

## Classification contract

Use `typesafe-sdk` with `TypeSafeClient(model="jev-1.13.0")`. The brief calls
the model `jev-1.13`; TypeSafe's current model registry uses the pinned ID
`jev-1.13.0`. Verify the account accepts that ID when access is granted.

One call per article sends a short `state` with `ticker`, `company_name`,
`title`, and any legitimately available short excerpt. Ask two independent
questions:

| Output | Type | Explicit interpretation |
| --- | --- | --- |
| `event_type` | Choice | `earnings` = reported financial results; `guidance` = forecast or outlook; `regulatory` = government rule, approval, enforcement, or filing action; `other` = none of those or unclear. |
| `concerns_company` | Noul | Probability that the article explicitly concerns the named company as a subject, including its products or results. An industry mention or a different company does not qualify. |

Do not convert Choice confidence or Noul probability into a buy/sell signal.
Store the original response values and question version; choose any relevance
threshold only on a labeled validation set. Process each article once per
target ticker and deduplicate on a stable source/ticker/URL key. News text is
untrusted input; it does not issue instructions to the runner.

## Telemetry and spend

For **every attempted decision**, log UTC attempt time, source, target ticker,
company name, publication time, URL or stable hash, input text hash, fixed
question version, model ID returned, event label and probabilities,
`concerns_company` probability, request ID, outcome/error, wall latency in ms,
input/output token counts, price assumption, and estimated USD cost. Do not
log keys or authorization headers. Retain an immutable, legally usable input
snapshot alongside a labeled evaluation fixture so the run is reproducible.

At the 2026-09-29 direct TypeSafe list price of **$0.042 per million input
tokens, output tokens free**, the estimate per response is
`input_tokens * 0.042 / 1_000_000`; failed calls and retries require their own
usage accounting, and the billing record should be reconciled before claiming
an actual dollar figure. Report weekly sum, number of attempted/successful
calls, token totals, and the price/version used. No API cost number is claimed
for this unrun design.

Before implementation, add a separate `TokenBudget` with proposed initial
weekly caps of 100,000 tokens and $0.01, at most 100 articles per week, one
request at a time, and no automatic retries. The TypeSafe SDK retries with
backoff by default, so explicitly set `RetryPolicy(max_retries=0)` for this
runner. Estimate an upper bound on input
size before each call; skip the article if the remaining cap cannot cover it.
Charge the reported token usage afterward. Review those caps with actual
usage before increasing them. The runner must not consume the live
multi-agent budget or bypass its caps.

## Evaluation gate

Freeze a dated set of article snapshots across the intended tickers before
looking at Jev outputs. Have humans label both fields, adjudicate ambiguous
cases, and keep a time-separated holdout. Report all Choice class counts and
confusion matrices, macro F1, relevance precision/recall at the selected
threshold, abstention/error rate, latency p50/p95, and observed $/week. Compare
against a fixed keyword baseline and a no-classifier baseline on the same
items. Include ticker-name collisions, competitor news, lookalike Unicode,
hidden instructions, and false earnings/guidance cues in the adjudicated
fixture; preserve raw headlines while treating them as untrusted data. Save
the fixture, annotation guide, exact questions, code, model ID,
token usage, and price assumptions. Only a separate, reviewed experiment may
propose changes to debate routing; this PR does not change it.

## Implementation prerequisite

When a TypeSafe early-access key is supplied outside git, put it in the
gitignored `.env` as `TYPESAFE_API_KEY` and update the optional dependency and
tests on a new PR. Start with fixture-based mock SDK tests that prove the
runner has no path to signal weights, debate routing, or order submission.
Only then run a bounded shadow sample and record measured results.

Sources (checked 2026-09-29): [TypeSafe Python SDK](https://docs.typesafe.ai/sdk/python),
[model IDs and price](https://docs.typesafe.ai/models),
[Jev 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13).
