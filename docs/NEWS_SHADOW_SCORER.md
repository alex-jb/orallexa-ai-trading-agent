# Offline company-news shadow scorer

This is an **evaluation tool**, not a news classifier, model runner, trading signal, or proof of excess return. It makes no API requests and has no broker access. It scores a declared four-class primary event (`earnings`, `guidance`, `regulatory`, `other`) and the binary question **“Does this article explicitly concern this ticker?”**. Use it for a shadow comparison only. It does not update signal weights or order routes.

The older `eval/benchmark_provider_ab.py` uses five synthetic quant prompts, schema/length checks and **estimated** costs. It has no independently adjudicated news labels or human accuracy estimate. This scorer uses a separate, explicitly supplied frozen cohort. Its tests contain invented synthetic labels to check accounting only; the tests provide no empirical model result. The [annotation workflow](NEWS_ANNOTATION.md) prepares blank reviewer copies and requires explicit adjudication; the [real-headline development seed](../eval/data/news_source_pilot_2026-10-05/README.md) remains unlabelled.

## Inputs and command

Use UTF-8 JSON for the manifest and JSONL with exactly one object per line for human gold and predictions. The following abbreviated schema describes the required fields (the file paths below are your own local files):

```json
{
  "cohort_id": "frozen-news-test-v1",
  "sample_kind": "stratified",
  "require_source_bundle": true,
  "relevance_confidence_thresholds": [0.0, 0.5, 0.8, 0.95, 1.0],
  "frozen_at_utc": "2026-09-30T00:00:00Z",
  "primary_class_rule": "If both guidance and earnings occur, label guidance; otherwise label the main event.",
  "cases": [
    {
      "case_id": "news-001:ACME", "source_id": "filing-001", "source_sha256": "<64 lowercase hex digits>",
      "source_url": "https://example.org/filing-001", "source_rights": "licensed-for-internal-evaluation",
      "event_group_id": "earnings-q3-acme", "split": "test", "ticker": "ACME", "language": "en",
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

Gold JSONL object: `{"case_id":"news-001:ACME","source_id":"filing-001","source_sha256":"<same hash>","status":"adjudicated","reviewer_ids":["reviewer-a","reviewer-b"],"event_type":"earnings","concerns_company":true,"evidence_span_ids":["paragraph-12"]}`. Reviewers should independently label blind to model outputs, then adjudicate. The scorer checks two distinct reviewer **ID claims** and `status`, but cannot verify reviewer independence, whether the event was correctly labeled, or data-use rights. Local source bytes and evidence ranges are checked only when a [source bundle](NEWS_SOURCE_PREFLIGHT.md) is supplied. Unresolved ambiguous or missing-source records cause the entire report to fail: resolve their status under a predeclared policy and preserve their original case IDs; do not remove hard examples after examining model outputs.

Prediction JSONL object: `{"model_id":"candidate","case_id":"news-001:ACME","source_id":"filing-001","source_sha256":"<same hash>","event_type":"earnings","concerns_company":true,"abstain":false,"concerns_company_probability":0.83,"latency_ms":290,"usage":{"input_tokens":800,"output_tokens":50,"billed_usd":0.002}}`. For `evidence_capable=true`, add `"evidence_span_ids":["paragraph-12"]` to **every** row; for classification-only arms, omit it. A deliberate threshold abstention uses `abstain:true`, null event/relevance labels and no evidence; it **may retain** a valid numeric probability for calibration, and still requires latency and usage. If a provider fails, record its case as abstained with `failure_kind` set to `timeout`, `provider_error`, `schema_error` or `missing_source`, and include all attempts' latency, tokens and billed cost; retain a separate runner error trace. Failed calls must not supply a scored probability. Deliberate abstention has no `failure_kind`; counts are separate in the report. Never silently omit a failed or timed-out case. `billed_usd` can be omitted or null if unknown, but a partially observed bill is reported as incomplete, not extrapolated.

```bash
python -m eval.news_source_preflight --manifest /path/to/manifest.json --source-bundle /path/to/bundle.json --output /path/to/preflight.json
python -m eval.news_shadow_score --manifest /path/to/manifest.json --gold /path/to/gold.jsonl --predictions /path/to/predictions.jsonl --source-bundle /path/to/bundle.json --output /path/to/report.json
python -m pytest -q tests/test_news_shadow_score.py
```

No report file is created or replaced on validation failure; an older output may still exist, so consume a report only after exit status 0 and input-hash checks. The output includes SHA-256 hashes of the exact input bytes that were parsed, model revision/pricing in the manifest, and declared cohort/sample type. For an empirical study, archive immutable input files, source snapshots and licensed retrieval receipts, runner version/commit, prompts, frozen splits and adjudication records with the report. A hash or URL alone does **not** prove the article's authenticity, timestamp, rights statement or human labels.

Report schema v3 adds `source_verification`. Supplying `--source-bundle` checks every train/test source's UTF-8 snapshot against its manifest SHA-256, verifies all preindexed evidence byte ranges and span hashes, and binds the bundle bytes to the report. Set `require_source_bundle:true` in a real-study manifest before freezing it to prevent accidental scoring without those archives. Legacy manifests default to false and can still run without a bundle, but are explicitly marked `metadata_only`. Byte verification does not prove what a provider actually consumed, when a fact first became public, or that a model's training excluded future outcomes. Preflight produces only unreviewed case rows; it does not assign human labels or model predictions.

## Confidence gates and language slices (introduced in report schema v2)

The report now includes `selective_company_relevance` for each model. This describes the coverage/error tradeoff at each **frozen** confidence threshold. Supply a strictly increasing, nonempty array in `[0, 1]` as `relevance_confidence_thresholds`; omitted arrays use the code defaults shown above. Freeze the manifest **and the scorer commit** before inspecting model outputs. The manifest hash binds custom thresholds to that input, and `thresholds_source` discloses whether the defaults were used. The scorer cannot prove that a freeze happened before results existed. It never ranks thresholds or selects one for deployment. Choose any operational threshold on a separate development cohort, then lock it before a held-out test.

For P(article explicitly concerns ticker) = `p`, the confidence of an emitted `true` label is `p`, and the confidence of an emitted `false` label is `1-p`. A row is accepted in a curve only if it answered, supplied this numeric probability, and its emitted-label confidence is at least the threshold. The code does **not** switch labels to their most probable value. Contradictory labels/probabilities are counted as `label_probability_disagreements`; a confident wrong answer still contributes an error. Probabilities of the event category are not available in this schema, so this is a **binary-relevance gate**, not a confidence test of the whole news analysis.

Every declared test case remains in the coverage denominator. Model abstentions, provider failures and answered rows without numeric probabilities are visibly withheld. Their usage and latency remain in the original complete-cohort totals. A threshold accepting zero cases returns `null` for its error rate and joint accuracy; it is not a perfect classifier. The accepted-set relevance error and event-plus-relevance accuracy are separate, because getting the company right does not mean getting the event right. Accepted-set diagnostics never replace the existing full-cohort F1, accuracy or Brier score. No threshold executes a model, changes a signal or authorizes an order.

Each manifest case may declare a lowercase language tag such as `en`, `zh` or `zh-hans`. Omitted tags become `und` (unknown), without guessing from text. The supported syntax is a two- or three-letter base followed by optional hyphen-separated 2–8 character alphanumeric segments; this is a shape check, not language identification or a complete language-tag registry. Unknown and mixed-language labeling policies must be fixed in advance. Reports include per-language case/event-group counts, abstentions, full-cohort classification metrics, probability coverage and the same relevance curves. A missing probability withholds Brier for that slice and for the total cohort; another fully covered slice can still report its own Brier. Train cases never enter these slices.

These slices are descriptive. Differences can reflect content, source, event mix, label ambiguity and sample size as well as language. Translations and repeated ticker cases may share an event group; do not treat slice rows as independent samples. Keep paired translations in the same event group and split. The script does not estimate uncertainty or establish a causal language effect.

Research motivation: [MIT's RLCR paper](https://arxiv.org/abs/2507.16806) studies training for calibrated answers, while [Stanford's cross-language measurement paper](https://arxiv.org/abs/2605.17173) separates factors hidden by one aggregate score. These diagnostics borrow their evaluation motivation. They do not implement RLCR training, reproduce Stanford's measurement model, or demonstrate calibrated financial predictions.

## Denominators and limits

- Every declared `test` case must appear exactly once in human gold and **for every declared model**; missing, duplicate, extra, malformed or future-after-freeze records fail. Train cases appear in the manifest for source-hash and event-group split leakage checks, and are counted but never scored. Multiple ticker cases can share an event group inside test, and test case/group counts are reported; a group cannot cross train/test. The reporter labels synthetic, development-pilot, stratified and representative samples separately. `sample_kind:development_pilot` discloses public development material; a `test` split does not make it held out. Stratified cohort metrics are not population prevalence estimates.
- Macro F1 averages all four frozen classes, including classes with zero support (their F1 is zero). Full-cohort classification F1 and relevance accuracy count abstentions as misses. Per-class support/precision/recall/F1 and model coverage are printed. A future paper should prespecify how to interpret absent classes; prefer a frozen test with examples of all four.
- Binary Brier is reported **only if every test item has an explicit numeric P(“explicitly concerns ticker”)**, including any abstentions that still produced a probability before policy rejection. A missing probability withholds Brier rather than offering a favorable selective-case score; the number supplied remains visible. Abstentions count as classification misses even when their valid probability contributes to full-cohort Brier. Do not substitute a free-form LLM `confidence`. TypeSafe Jev's Noul `.noul` can represent P(yes) for the same predeclared question; Choice `.probabilities` are a different multiclass output. No Jev API or private pricing is used here.
- Evidence exact match is **N/A** for classification-only arms. For declared evidence-capable arms it is scored only on gold records with at least one preindexed citation span; empty gold/predicted sets cannot score as a correct citation. Both the eligible denominator and full-cohort rate are printed. Jev could use a separately frozen Choice over candidate IDs, but its primitive does not generate arbitrary evidence text/IDs; do not compare it to a citation-generating model without an equivalent candidate set.
- p50/p95 latency uses nearest-rank on every test item. `observed_billed_usd` and its per-1,000 scaling appear only if **every** case has an actual per-case bill. Token-rate estimates use **explicit rates in the manifest** and exclude unreported tools, retries, caches, taxes and provider fees. They are labeled separately from actual billed amounts and cannot be treated as invoices. Aggregate retry usage into the corresponding case before scoring. A paid runner would need its own hard $5 cap, rights checks and failure trace; this scorer cannot enforce an external provider's spend.
- This script has no confidence intervals, paired event-cluster bootstrap or multiple-comparison testing. An empirical model ranking must predeclare the primary comparison, use independent event clusters, evaluate an additional representative stream, and correct multiple claims (e.g. Holm/Bonferroni or Benjamini–Hochberg, chosen in advance). News-label accuracy alone does not validate forecast skill, paper fills, net P&L or market edge.
