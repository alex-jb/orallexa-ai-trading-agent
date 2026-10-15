# Evidence-aware local news research

`engine.news_research` adds timestamp validation, exact input snapshots and local
BM25 ranking to the existing Orallexa news path. It does not add a hosted agent
framework, new required Python package, model API call or broker operation.
The implementation supports the project's Python 3.11 runtime.

## Integrated behavior

The regular and streaming deep-analysis endpoints, the lightweight engine and
daily intelligence now use the same research gate **before** sentiment scoring
and downstream debate/fusion. Both Yahoo news schemas are supported. Daily
intelligence retains its `DAILY_INTEL_USE_RSS=1` option for Google News/Yahoo RSS;
the legacy `fetch_aggregated_news` convenience API remains available.

Deep results expose `news_research` and retain the same object in
`decision.extra.news_research`, so existing decision logging saves the evidence.
Daily reports cache per-ticker research audits, full selected headline records
and `brief_selected_source_hashes` for the final 20-headline selection. Existing
same-day daily caches are reused; regenerate with `force=True` to get this schema.

The previous deep news helper treated importing the sentiment module as proof
that FinBERT had scored the headlines, leaving them all at zero. The shared path
now actually calls the existing `engine.sentiment.score_text` backend, with its
existing FinBERT/VADER/TextBlob/keyword fallbacks. This can change news votes and
brief contents. FinBERT's existing first-use model load can still be slow. The
change has no demonstrated model-accuracy, calibration or trading-return lift.

News now precedes ML in the debate context so a long ML report cannot consume
the entire old 500-character allowance. Debate context is capped at 2,600
characters; panel/risk/deep-report news is capped at 2,000. These are character
limits, not token guarantees, and can omit later evidence. Paid input token use
can increase; existing token-budget and compression behavior remains in place.
The audit preserves the candidates even when prompts truncate the report.

## Time contract

- **Live:** collect current feeds, stamp actual UTC capture times, then freeze
  the cutoff after collection. `available_at_utc` equals local capture time and
  `availability_basis=local_capture`. It does not claim earliest public release.
- **Historical:** supply a timezone-aware `news_as_of` and previously captured
  records. An explicit cutoff never requests today's feed as a substitute. A
  historical `trade_date` alone returns `cutoff_required`; a precise cutoff
  without an archive returns `archive_required`.
- Each usable record must satisfy publication ≤ availability ≤ capture ≤ cutoff.
  Unknown/naive publication or acquisition times, missing URLs, modified bytes
  and invalid headline byte ranges are excluded with a recorded reason.
- Cutoffs include their exact boundary. New York 09:00 on October 14, 2026 is
  13:00 UTC. A story published at 20:30 UTC that day is excluded. A story fetched
  October 15 is also excluded, even if it claims October 14 publication.
- When multiple versions share a URL, use the latest eligible captured version.
  Retain older versions as `superseded_snapshot`. Conflicting contents claiming
  the same latest capture instant are rejected; an after-cutoff revision cannot
  replace a valid earlier snapshot.

This contract constrains **news inputs only**. The existing technical/ML/price
paths are not converted into a historical replay by passing `news_as_of` or
`trade_date`. Archive timestamps remain declarations; this code cannot
authenticate source receipts or establish that a model had no future knowledge.

## Evidence and ranking

Each candidate retains its title/provider/feed, source URL, source ID, exact
normalized headline/summary `snapshot_text`, SHA-256, publication/availability/
capture times, and a headline span with zero-based, end-exclusive **UTF-8 byte**
offsets and a span hash. These are the retrieval inputs, not full article/HTML
archives. Ranking sees the snapshot; sentiment sees the headline; downstream
prompts see a bounded headline report. No claim is made that a provider consumed
the entire snapshot. `source_rights=unknown` does not grant article-use rights.

Every candidate remains in the audit as selected, omitted or rejected. Ranking
configuration records the exact query, custom aliases, TopK limit and algorithm
version; CLI replay restores the custom aliases and limit. Exact
duplicate snapshots are accounted for separately. Feed states distinguish
`ok`, `empty`, `unavailable` and `invalid`; overall status also distinguishes
partial success from all inputs being filtered. No usable evidence does not
establish that no relevant news exists.

BM25 uses ticker/company aliases and explicit Chinese aliases for a small set
of tickers; callers can supply additional `aliases`. Single-letter tickers such
as `F` survive tokenization. Relevance scores are finite, uncalibrated lexical
scores, **not** company-relevance or price probabilities. Distinct outlets with
lexical matches get a first pass before filling remaining slots. Zero-match
items can fill unused slots, so TopK is not a semantic relevance classifier.
There is no complete-news, independent-source or balanced-opinion guarantee.
There is no age-window filter beyond what the feeds return and the cutoff gate.
Daily intelligence still applies its existing sentiment/recency/provider ranking
to choose the final brief headlines; this is separate from per-ticker retrieval.

## Capture and replay without model calls

From the repository root, choose **new** output filenames:

```bash
python -m engine.news_research --ticker NVDA --rss --output /tmp/nvda-capture.json
python -m engine.news_research --ticker NVDA --as-of '<capture as_of_utc>' --input /tmp/nvda-capture.json --output /tmp/nvda-replay.json
```

The CLI makes feed requests for capture, but never calls sentiment models,
LLMs or brokers. Replay reads the prior audit's `candidates`, verifies snapshot
and span hashes, and binds the exact input-file bytes with `replay_input_sha256`.
It creates the output exclusively and exits 2 on validation/file errors.
`archive_required`, `filtered` or source failure are recorded research outcomes,
not a successful financial assessment; inspect the output status and counts.

Programmatic historical news integration:

```python
import json
from engine.multi_agent_analysis import run_multi_agent_analysis

archive = json.load(open('/path/captured-before-cutoff.json', encoding='utf-8'))
result = run_multi_agent_analysis(
    'NVDA', trade_date='2026-10-14',
    news_as_of='2026-10-14T09:00:00-04:00',
    archived_news=archive['candidates'],
)
```

The full analysis above still uses its existing market data and paid LLM path;
use the CLI to inspect/replay news without those calls. HTTP endpoints currently
run live news research and expose its audit; historical archive selection is a
Python/CLI interface, not an HTTP upload or a new UI control.

The field names intentionally overlap the source preflight work in draft
[PR #34](https://github.com/alex-jb/orallexa-ai-trading-agent/pull/34), but this
change does not depend on that branch. A research audit is not an evaluation
manifest, a source bundle with snapshot files, human gold labels or a scored
model comparison.

## Design references

Research considered TradingAgents'
[date window](https://github.com/TauricResearch/TradingAgents/blob/1394a3f72aa4393e1a98f51b382434c4b4c2d972/tradingagents/dataflows/date_window.py)
and GPT Researcher's
[local lexical filter](https://github.com/assafelovic/gpt-researcher/blob/3582a6841fe7dc801e2a34e34ee408641aea9bce/gpt_researcher/context/lexical.py).
This is an independent implementation of standard BM25 and Orallexa's evidence
contract; it copies no upstream implementation and vendors no framework.
Precise acquisition cutoffs address a gap that date-only filtering cannot cover.

## Validation

```bash
python -m pytest -q tests/test_news_research.py tests/test_news_research_integration.py tests/test_news_aggregator.py tests/test_daily_intel.py
```

Tests use synthetic sources, clocks and stubbed market/LLM calls. Integration
tests run the real research path, filter before fusion and debate context,
exercise both real HTTP handlers, and verify saved decisions contain the same
evidence returned to the caller. Passing tests demonstrate mechanics, not news
coverage, source authenticity, predictive accuracy or a trading edge.
