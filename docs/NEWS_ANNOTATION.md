# Independent review and explicit adjudication

`eval.news_annotation` prepares blank files, compares two reviewer submissions and converts an explicit adjudication into the existing scorer's gold JSONL. It does not create labels, invoke models or verify that claimed IDs belong to independent humans. Arrange independent human work outside this tool and keep both reviewers blind to each other's labels and model outputs until their submissions are frozen.

## Inputs and review states

All three commands re-run source preflight. Documents bind the cohort, exact manifest/bundle SHA-256, each case's source ID/hash, ticker and allowed evidence IDs. Keep the source bundle, snapshots, manifest classification rule and any documented ticker aliases accessible to reviewers. Assign the event label to the archived input, not unseen article text; company relevance is separate from sentiment, valuation or predicted price movement.

Each reviewer fills the top-level `reviewer_id` with their own stable ID. Every test case stays in both files. Use these states:

| Status | Fields |
| --- | --- |
| `unreviewed` | Null `event_type`/`concerns_company`, empty `evidence_span_ids`; not complete. |
| `reviewed` | One of `earnings`, `guidance`, `regulatory`, `other`; boolean `concerns_company`; evidence IDs from the frozen map. |
| `ambiguous` | Null labels, empty evidence, and a nonempty `note` explaining the unresolved judgement. Counts as a submitted review, but still needs resolution. |

Reviewer IDs are stripped and compared without case distinctions. Distinct strings are a declaration, not proof of identity or independence. Evidence IDs compare as sets. Pending and ambiguous cases stay in the denominator; they are never silently dropped or guessed.

## Commands

From the repository root, first create a **new** working directory:

```bash
python -m eval.news_annotation prepare --manifest /path/manifest.json --source-bundle /path/bundle.json --output-dir /path/new-review-work
```

It creates `review_a.json`, `review_b.json` and `preflight.json`, with null reviewer IDs and labels. Give each reviewer their own file. After independently completing them, compare into another new directory:

```bash
python -m eval.news_annotation compare --manifest /path/manifest.json --source-bundle /path/bundle.json --review-a /path/new-review-work/review_a.json --review-b /path/new-review-work/review_b.json --output-dir /path/new-comparison
```

`comparison.json` shows pending, ambiguous, agreement and disagreement counts plus differing fields. It always reports `ready_for_scoring:false`. The accompanying `adjudication.json` starts unresolved, even where reviewers agree, and binds both submissions' exact file hashes.

An adjudicator fills their stable `adjudicator_id` and explicitly sets **every** case to `adjudicated`, supplying valid labels, selected evidence IDs and a nonempty `reason`. A reviewer may also adjudicate; the two original reviews still must be distinct and independently completed. Then write a new gold file:

```bash
python -m eval.news_annotation finalize --manifest /path/manifest.json --source-bundle /path/bundle.json --review-a /path/new-review-work/review_a.json --review-b /path/new-review-work/review_b.json --adjudication /path/new-comparison/adjudication.json --output /path/new-gold.jsonl
```

Missing/pending reviews, unresolved decisions, changed submission hashes, changed sources and incomplete case lists fail. Consensus alone cannot become gold. A changed review requires a fresh comparison and adjudication tied to its current hash. Gold retains both reviewer IDs, adjudicator ID, the exact annotation input/review hashes and adjudication hash, and is accepted by `eval.news_shadow_score`.

Validation finishes before writing; exit status 2 means failure. Output directories and gold files must be new, so an existing human submission or gold file is never overwritten. A filesystem error can leave a partial new directory; require exit status 0 and all expected outputs before use. This is a cooperative local workflow, not an authenticated or concurrent multi-user annotation service.

## First real-source development seed

The [October 5 pilot](../eval/data/news_source_pilot_2026-10-05/README.md) has four official short headline excerpts, eight source/ticker cases and two event groups, with no filled labels or provider outputs. Its `sample_kind:development_pilot` explicitly discloses public development material. The `test` split names the scorer's annotation scope; it is not a held-out or representative study. Replace the placeholder model metadata and freeze a separately selected prospective cohort before any empirical comparison.
