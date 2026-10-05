# Local source preflight before news evaluation

The preflight verifies frozen local **model-input snapshots**, without calling a provider or reading gold/predictions. A successful check means the archived bytes, citation anchors and metadata agree. It does not establish source authenticity, legal permission, historical information availability, independent human annotation, financial skill or what an external runner read.

Use it before annotation and again during scoring. The scorer retains its four event labels and binary company-relevance question; this is not a valuation, sentiment or price-direction test.

## Bundle format

Keep `bundle.json` with a `snapshots/` directory. One bundle record is required for every distinct source ID in the manifest, **including training sources**. Multiple ticker cases can share one source. All their hash/URL/rights/publication/availability metadata must agree with that source record. Evidence spans must exactly cover the union of their allowed IDs, with no missing, extra or duplicate IDs.

```json
{
  "bundle_schema_version": 1,
  "cohort_id": "frozen-news-test-v1",
  "sources": [
    {
      "source_id": "filing-001",
      "source_sha256": "<SHA-256 of exact snapshot bytes>",
      "source_url": "https://example.org/filing-001",
      "source_rights": "<documented permission or applicable terms>",
      "published_at_utc": "2026-09-01T11:00:00Z",
      "available_at_utc": "2026-09-01T11:05:00Z",
      "captured_at_utc": "2026-09-01T11:06:00Z",
      "snapshot_path": "snapshots/filing-001.txt",
      "evidence_spans": [
        {
          "span_id": "paragraph-12",
          "start_byte": 0,
          "end_byte": 42,
          "span_sha256": "<SHA-256 of snapshot bytes [0:42]>"
        }
      ]
    }
  ]
}
```

The hashes, times and byte offsets above are **schema placeholders**, not captured data. Generate them from the actual acquired inputs; do not substitute a publication date for an acquisition receipt or backdate a freeze. Enforce publication ≤ availability ≤ capture ≤ freeze. The timestamp check validates the declared ordering, not the truth of those declarations. An archive captured today cannot establish that its contents were available to an earlier forecast.

Snapshots must be regular UTF-8 files of 1 byte–16 MiB within the bundle directory. Paths must be normalized relative paths; parent traversal, absolute paths and symlinks escaping that directory are rejected. Offsets are **zero-based UTF-8 byte offsets**, end-exclusive, not character indexes. A range must contain non-whitespace text, stay within the file, preserve UTF-8 character boundaries and match its span hash. Overlapping spans are allowed. Byte checking uses the same bytes for the file hash and all span checks.

Store the exact text supplied to the model. If extracting it from HTML/PDF or translating it, retain the original acquisition receipt, extraction/translation version and transformation record separately; those are not authenticated by this tool. Prefer a read-only frozen directory during evaluation. Bundle paths are a cooperative file-boundary check, not an operating-system sandbox for hostile concurrent modifications.

## Workflow

```bash
python -m eval.news_source_preflight --manifest /path/to/manifest.json --source-bundle /path/to/bundle.json --output /path/to/preflight.json
python -m eval.news_shadow_score --manifest /path/to/manifest.json --gold /path/to/gold.jsonl --predictions /path/to/predictions.jsonl --source-bundle /path/to/bundle.json --output /path/to/report.json
```

Set manifest `require_source_bundle:true` before the study freeze. The scorer rejects a missing bundle when this is true. Older manifests default to false and remain usable, with `source_verification.mode=metadata_only`; supplying a bundle always enables verification regardless of that flag.

Preflight returns source counts/hashes and test-only `unreviewed_cases`. Reviewer ID, event type and company relevance are null; evidence selection is empty. Keep two independent reviewer copies blind to model outputs, then preserve adjudication records and prepare the separate gold JSONL. A preflight report cannot be used as adjudicated gold. The tool deliberately provides no event, sentiment or relevance guesses and does not attest reviewer identity.

Use [the annotation workflow](NEWS_ANNOTATION.md) to prepare separate blank files, compare submissions without dropping cases, and require explicit adjudication before gold. The [October 5 real-headline development seed](../eval/data/news_source_pilot_2026-10-05/README.md) demonstrates this input preparation while preserving null labels.

Only consume an output after exit status 0 and matching input hashes. Validation failures return status 2 and do not create or replace an output; an older report can remain on disk. Preflight's `gold_status` and `predictions_status` are `not_checked`; success does not mean the cohort is ready for model ranking. Source rights, representative sampling, annotation and event-cluster uncertainty still need their own evidence.
