# ICAIF 2026 offline SMA baseline

This isolated adapter maps a fixed daily SMA20/50 long-or-cash rule to the
[organizer's 2026 Trading Agent Competition](https://icaif2026.org/competitions/).
It returns **target portfolio weights**, never shares or broker orders. It has
no network, broker, LLM, registration, or competition submission code. There
is no measured return or performance claim for this baseline.

## Verified contract and differences from Orallexa paper trading

The [official Starter Kit](https://github.com/DeepIntoStreams/2026ICAIF_Trading_Agent_Competition/tree/ad237b074d31dca39c5c975b3e5cb61cf85a8feb/starter-kit)
defines an importable `strategy(observation) -> weights` callable. Its client
passes `phase`, `round`, `symbols`, `as_of`, `portfolio`, and `round_state`.
The adapter uses the organizer-confirmed `symbols` and current round, then
returns every one of the 30 symbols, including zero targets. The organizer's
client alone owns credentials, preflight checks, uploads, recovery, and the
simulated accounting. Do not pass this output into Alpaca.

| Rule | Competition 99 |
| --- | --- |
| Decisions | Seven windows per U.S. trading day, ET; live schedule is authoritative |
| Portfolio | Independent Validation and Official accounts, each $1m virtual cash |
| Weights | Long only, each 0–0.30, total <=1, unused capital remains cash |
| Cost | 0.1% of buy-plus-sell notional on every rebalance, including initial allocation |
| Output | One `decision.json` containing team ID/token, phase, round ID and 30 weights; official client builds it |
| Failure | Missing or invalid attempt holds existing holdings; valid zero targets sell holdings |

An invalid first in-window attempt consumes that round; later uploads cannot
fix it. Therefore this adapter raises on missing/stale/unavailable data rather
than treating missing prices as sell signals. The SMA rule intentionally
targets cash when **all 30 valid signals** are bearish. Repeating a daily
target in seven windows may cause repeated rebalance costs. This is a
protocol baseline, not evidence of an intraday edge.

## Local input

Set `ORALLEXA_ICAIF_BARS_FILE` to an absolute path **outside the git repo**.
The private UTF-8 JSON file has this shape, with exactly the 30 symbols in the
official current schedule and at least 50 completed daily closes per symbol:

```json
{
  "source": {
    "url": "https://your-public-source.example/prices",
    "terms_url": "https://your-public-source.example/terms",
    "access": "public_free",
    "permission_basis": "Your recorded reason these terms allow this use",
    "competition_use_confirmed": true,
    "verified_at": "2026-10-07T17:00:00-04:00"
  },
  "bars": {
    "AAPL": [
      {
        "timestamp": "2026-10-07T16:00:00-04:00",
        "available_at": "2026-10-07T16:01:00-04:00",
        "close": 100.0
      }
    ]
  }
}
```

That fragment explains the format; it is **not** a full runnable dataset.
Replace the sample source URLs with a real, public, free source and a real
terms or license page. The adapter rejects absent declarations, paid access,
and terms verified after the decision cutoff or more than 30 days earlier.
This is a local attestation check; software cannot determine whether a
source's terms actually grant permission. Review and record that judgment
before using the data. Do not place signed URLs or secrets in this file.
`timestamp` means the 16:00 ET completed daily session close;
`available_at` is when the source released that
particular value. Provide one record per market session. The code validates
all records, excludes those unavailable at `as_of`, requires 50 eligible
closes and a most recent eligible close within seven calendar days. It does
not fetch data or prove the source timestamps. Retain source URL, terms,
adjustment policy, acquisition time and raw input checksum for reproduction.
An early-close session is rejected because recognizing its 13:00 close needs
a verified exchange calendar; extend the adapter and tests before using such
data. A 13:00 or 15:00 price on a normal day is never treated as a final close.

For every symbol, `SMA20 > SMA50` selects long, otherwise cash. Selected
symbols receive equal weights up to 30% each; unused weight is cash. The
strict comparison, 20/50 lookback, and 30% cap are fixed in this version.

The Starter Kit currently bundles **synthetic prices only**. The conference
site announces historical hourly OHLCV for development, but the publicly
visible kit does not contain that dataset or a live feed; verify its access
and license in the competition portal. External data must be freely and
publicly accessible by the decision deadline; paid or private feeds are
prohibited. The Starter Kit does not state a general hardware quota. Its
original guide says Python 3.11+ with standard library only, whereas its
updated root README says Python 3.10+ and `requirements.txt` pins `httpx`
for the automatic submission client. This adapter uses Python 3.10+ standard
library only; follow the organizer's current kit for any transport setup.

## Preparation and eligibility

Keep the official Starter Kit separate; its public repository currently has
no license declaration, so no source or data are copied here. Its importable
strategy reference would be `competition.icaif2026_sma:strategy`, with this
repository on `PYTHONPATH`. Connecting the official `watch` client would
create a competition submission and is outside this offline adapter.
This callable trusts the official client's prior schedule/universe check;
passing an arbitrary handcrafted 30-symbol `observation` directly is an
offline test, not proof of organizer eligibility.

Official registration requires each named team member to have a Codabench
account with a unique matching email; the schema allows 1–50 members.
Registration before **October 8, 00:00 ET** enters both the October 8–9
Validation and October 12–30 Official phases. Registration before the
exclusive **October 12, 00:00 ET** cutoff enters Official only. Final
reproduction materials are due November 3, 23:59:00 ET. The official final
package requires source, environment, input provenance and terms, and a
complete disclosure. This adapter uses no LLM; Orallexa's default Claude
Opus 4.7 is absent from the competition's explicit permitted-model list.

Run the offline checks with `python -m pytest tests/test_icaif2026_sma.py -q`.
The tests use invented prices and make no trading-performance claim.
