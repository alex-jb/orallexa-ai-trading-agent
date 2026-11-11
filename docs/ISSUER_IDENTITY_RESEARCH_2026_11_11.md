# Financial AI tools and issuer identity — November 11, 2026

The immediate research gap is the connection between an extracted news mention,
the issuer it may identify, and the particular listing named in the source. The
existing FinEntity results measure entity and sentiment extraction; they do not
establish a ticker link. This change adds a separate offline identity check.

## Market and open-source review

| Source | What it offers | Decision for Orallexa |
| --- | --- | --- |
| [AlphaSense source verification](https://help.alpha-sense.com/hc/en-us/articles/54133001189907-AlphaSense-Financial-Data-Sources) and [Generative Search](https://help.alpha-sense.com/hc/en-us/articles/41666587181203-Interacting-with-Generative-Search) | Research synthesis with source links, including links from many figures to filings. | Reuse the verification pattern: make the evidence and its time inspectable. No vendor data imported. |
| [Fiscal.ai changelog](https://fiscal.ai/changelog/) and [Copilot MCP announcement](https://fiscal.ai/blog/fiscal-ai-launches-an-mcp-connector-for-microsoft-copilot/) | Structured financial data in agents; its November 6 release added politician transactions to Terminal and MCP. | A provider integration is a separate option. Treat transaction reports as observations, with their own disclosure dates and access terms. |
| [OpenBB V5 release](https://github.com/openbq-org/OpenBB/releases) and [November 5 OpenBQ announcement](https://openbq.org/) | The V5 code release lists Apache-2.0; OpenBQ announced stewardship of OpenBB open-source projects. [Provider data terms remain separate](https://github.com/OpenBB-finance/openbb-docs/blob/main/content-odp/python/faqs/license.mdx). | Useful adapter reference. Pin a version if evaluating it; no framework dependency needed for today's lookup. |
| [EdgarTools](https://github.com/dgunning/edgartools) and its [MIT license](https://github.com/dgunning/edgartools/blob/main/LICENSE.txt) | An open-source EDGAR client with company and filing abstractions. | Closest candidate for filing retrieval. Keep the observed directory separate from live lookups so replay does not use future data. |
| [OpenFIGI documentation](https://www.openfigi.com/api/documentation) | Separate instrument, composite and share-class identifiers, with exchange constraints. | Candidate for instrument-level validation later. SEC CIKs identify filers, and the current probe does not assert a FIGI or tradability. |
| [FinSearchComp (ICLR 2026)](https://proceedings.iclr.cc/paper_files/paper/2026/hash/4d42358702dff82e1436550a05ade260-Abstract-Conference.html), [code/data](https://github.com/randomtutu/FinSearchComp), and [FinRetrieval](https://arxiv.org/abs/2603.04403) | Separate evaluations for time-sensitive research, historical work and structured fact retrieval. | Borrow the task separation. Correct retrieval and correct identity are measurable before asking whether a research signal has trading value. |

Our product inference is to prioritize an evidence view that shows the exact
mention, the issuer, and a specific symbol when supported. Another agent or
provider would still need to make those distinctions.

## Implemented and measured

- `engine/issuer_identity.py` consumes the exact [SEC exchange directory](https://www.sec.gov/files/company_tickers_exchange.json)
  and its byte count, SHA-256 and caller-declared capture time. It validates source
  news using the existing point-in-time evidence gate and anchors accepted spans to
  the original UTF-8 bytes. A directory captured after the decision cutoff is blocked.
- A unique qualified name or CIK yields an issuer association. An explicit
  cashtag or venue-qualified symbol can yield a listing. Short names are candidates;
  conflicting issuers abstain. A dotted and dashed symbol can match the same
  directory key, but collisions remain visible. An issuer-only match never picks a share class.
- `--scan-explicit` adds complete source notations with their own origin and offsets.
  It does not promote ordinary words, dollar amounts or truncated ticker tokens.
  A provided span that was already counted remains a duplicate, not a second match.

The actual SEC response was captured at **5:45 p.m. New York time** on November 11.
It contained **10,405 directory rows for 8,002 CIKs**. The
[diagnostic record](../eval/history/issuer-identity/sec-directory-2026-11-11.json)
contains the exact UTC time and hashes. **16/16 controlled cases** matched their
specified results against those real bytes, and all 16 were blocked when replayed
before the directory capture. For example, `$GOOG` and a GOOGL focus have the same
issuer, while only an explicit matching symbol earns `same_symbol`.

We also ran the previously pinned **GLiNER2.5 base** checkpoint locally with its
existing schema and thresholds. The same controlled suite had 15 eligible texts
and ten expected positive identity anchors. Model spans alone recovered **7/10**;
adding the explicit scan recovered **9/10**. For the two recovered cases, the
model emitted symbol substrings without their full exchange notation. The
remaining Chinese/English mixed example emitted no model span. These are
controlled interface checks with intentionally present notation, not extraction
or ticker-link accuracy estimates for live news.

A first-party Apple Newsroom feed spot check found no eligible publication time
in the supported fields among 12 entries. The probe did not substitute an update
time as the original publication time or run a live-headline accuracy calculation.
The [SEC FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions)
likewise distinguishes filing acceptance from public availability and notes the
directory associations have coverage and accuracy limitations.

## Replay

The accompanying replay ZIP contains the observed directory, its receipt, controlled
news snapshots and span inputs, expected results, and the blocked-cutoff output.
It also contains the actual model spans for the synthetic examples. It contains
neither model weights nor copied third-party news articles.

```bash
python -m eval.run_issuer_identity_probe \
  --directory /path/to/replay/sec-directory.json \
  --receipt /path/to/replay/sec-directory-receipt.json \
  --input /path/to/replay/identity-probe-input.json \
  --as-of 2026-11-11T22:50:04.881818Z \
  --output issuer-replay.json
```

To replay the checkpoint interface, use `gliner-controlled-input.json` and compare
with and without `--scan-explicit`, using different output filenames. The prior
[checkpoint experiment](NEWS_ENTITY_MODEL_PROBE.md) records model files and setup.
The new CLI requires no model, API key or network access. JSON rows use `id`,
`snapshot` in the existing `snapshot_record` format, and optional `mentions`
with exclusive-end `start`, `end`, `text`; `focus_symbol` is optional.

The directory time is a declared observation, not an authenticated timestamp or
effective listing date. Directory matches do not determine who caused an event,
subsidiary-to-parent attribution, present tradability, sentiment, or market impact.
The component is available for research replay and is not part of decision scoring.
