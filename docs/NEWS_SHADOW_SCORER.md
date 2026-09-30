# Offline company-news shadow scorer

This is an **evaluation tool**, not a news classifier, model runner, trading signal, or proof of excess return. It makes no API requests and has no broker access. It scores a declared four-class primary event (`earnings`, `guidance`, `regulatory`, `other`) and the binary question **“Does this article explicitly concern this ticker?”**. Use it for a shadow comparison only. It does not update signal weights or order routes.

The older `eval/benchmark_provider_ab.py` uses five synthetic quant prompts, schema/length checks and **estimated** costs. It has no independently adjudicated news labels or human accuracy estimate. This scorer uses a separate, explicitly supplied frozen cohort. Its tests contain invented synthetic labels to check accounting only; the tests provide no empirical model result.

## Inputs and command

Use UTF-8 JSON for the manifest and JSONL with exactly one object per line for human gold and predictions. The following abbreviated schema describes the required fields (the file paths below are your own local files):

```json
{
  "cohort_id": "frozen-news-test-v1",
  "sample_kind": "stratified",
  "frozen_at_utc": "2026-09-30T00:00:00Z",
  "primary_class_rule": "If both guidance and earnings occur, label guidance; otherwise label the main event.",
  "cases": [
    {
      "case_id": "news-001:ACME", "source_id": "filing-001", "source_sha256": "<64 lowercase hex digits>",
      "source_url": "https://example.org/filing-001", "source_rights": "licensed-for-internal-evaluation",
      "event_group_id": "earnings-q3-acme", "split": "test", "ticker": "ACME",
      "published_at_utc": "2026-09-01T11:00:00Z", "available_at_utc": "2026-09-01T11:05:00Z",
      "evidence_span_ids": ["paragraph-12"]
    }
  ],
  "models": [
    {
      "model_id": "candidate", "revision": "pinned-revision-and-prompt-v1",
      "evidence_capable": false,
      "pricing_usd_per_million_tokens": {"input": 2.0, "output": 10.0}
    }
  ]
}
```

Gold JSONL object: `{"case_id":"news-001:ACME","source_id":"filing-001","source_sha256":"<same hash>","status":"adjudicated","reviewer_ids":["reviewer-a","reviewer-b"],"event_type":"earnings","concerns_company":true,"evidence_span_ids":["paragraph-12"]}`. Reviewers should independently label blind to model outputs, then adjudicate. The scorer checks two distinct reviewer **ID claims** and `status`, but cannot verify reviewer independence, whether the event was correctly labeled, the source bytes, or data-use rights. Unresolved ambiguous or missing-source records cause the entire report to fail: resolve their status under a predeclared policy and preserve their original case IDs; do not remove hard examples after examining model outputs.

Prediction JSONL object: `{"model_id":"candidate","case_id":"news-001:ACME","source_id":"filing-001","source_sha256":"<same hash>","event_type":"earnings","concerns_company":true,"abstain":false,"concerns_company_probability":0.83,"latency_ms":290,"usage":{"input_tokens":800,"output_tokens":50,"billed_usd":0.002}}`. For `evidence_capable=true`, add `"evidence_span_ids":["paragraph-12"]` to **every** row; for classification-only arms, omit it. A deliberate threshold abstention uses `abstain:true`, null event/relevance labels and no evidence; it **may retain** a valid numeric probability for calibration, and still requires latency and usage. If a provider fails, record its case as abstained with `failure_kind` set to `timeout`, `provider_error`, `schema_error` or `missing_source`, and include all attempts' latency, tokens and billed cost; retain a separate runner error trace. Failed calls must not supply a scored probability. Deliberate abstention has no `failure_kind`; counts are separate in the report. Never silently omit a failed or timed-out case. `billed_usd` can be omitted or null if unknown, but a partially observed bill is reported as incomplete, not extrapolated.

```bash
python -m eval.news_shadow_score --manifest /path/to/manifest.json --gold /path/to/gold.jsonl --predictions /path/to/predictions.jsonl --output /path/to/report.json
python -m pytest -q tests/test_news_shadow_score.py
```

No report file is created on validation failure. The output includes SHA-256 hashes of the exact input bytes that were parsed, model revision/pricing in the manifest, and declared cohort/sample type. For an empirical study, archive immutable input files, source snapshots or licensed retrieval receipts, runner version/commit, prompts, frozen splits and adjudication records with the report. A hash or URL alone does **not** prove that the original article bytes, timestamp, rights statement or human labels are true; the scorer checks the hash string and the source ID's consistency, not the source content.

## Denominators and limits

- Every declared `test` case must appear exactly once in human gold and **for every declared model**; missing, duplicate, extra, malformed or future-after-freeze records fail. Train cases appear in the manifest for source-hash and event-group split leakage checks, and are counted but never scored. Multiple ticker cases can share an event group inside test, and test case/group counts are reported; a group cannot cross train/test. The reporter labels synthetic, stratified and representative samples separately; stratified cohort metrics are not population prevalence estimates.
- Macro F1 averages all four frozen classes, including classes with zero support (their F1 is zero). Full-cohort classification F1 and relevance accuracy count abstentions as misses. Per-class support/precision/recall/F1 and model coverage are printed. A future paper should prespecify how to interpret absent classes; prefer a frozen test with examples of all four.
- Binary Brier is reported **only if every test item has an explicit numeric P(“explicitly concerns ticker”)**, including any abstentions that still produced a probability before policy rejection. A missing probability withholds Brier rather than offering a favorable selective-case score; the number supplied remains visible. Abstentions count as classification misses even when their valid probability contributes to full-cohort Brier. Do not substitute a free-form LLM `confidence`. TypeSafe Jev's Noul `.noul` can represent P(yes) for the same predeclared question; Choice `.probabilities` are a different multiclass output. No Jev API or private pricing is used here.
- Evidence exact match is **N/A** for classification-only arms. For declared evidence-capable arms it is scored only on gold records with at least one preindexed citation span; empty gold/predicted sets cannot score as a correct citation. Both the eligible denominator and full-cohort rate are printed. Jev could use a separately frozen Choice over candidate IDs, but its primitive does not generate arbitrary evidence text/IDs; do not compare it to a citation-generating model without an equivalent candidate set.
- p50/p95 latency uses nearest-rank on every test item. `observed_billed_usd` and its per-1,000 scaling appear only if **every** case has an actual per-case bill. Token-rate estimates use **explicit rates in the manifest** and exclude unreported tools, retries, caches, taxes and provider fees. They are labeled separately from actual billed amounts and cannot be treated as invoices. Aggregate retry usage into the corresponding case before scoring. A paid runner would need its own hard $5 cap, rights checks and failure trace; this scorer cannot enforce an external provider's spend.
- This script has no confidence intervals, paired event-cluster bootstrap or multiple-comparison testing. An empirical model ranking must predeclare the primary comparison, use independent event clusters, evaluate an additional representative stream, and correct multiple claims (e.g. Holm/Bonferroni or Benjamini–Hochberg, chosen in advance). News-label accuracy alone does not validate forecast skill, paper fills, net P&L or market edge.
