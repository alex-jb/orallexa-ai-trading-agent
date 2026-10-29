# Entity sentiment research and local diagnostic — October 29, 2026

The next useful news upgrade is sentiment attached to the correct entity, not
another whole-document score. A headline can report opposite outcomes for two
companies. Existing local classifiers return one label per text; ticker-based
retrieval does not establish which entity a positive or negative phrase concerns.
This is a limitation to measure before choosing a replacement model.

Follow-up: the [local GLiNER2.5 experiment](NEWS_ENTITY_MODEL_PROBE.md) now measures
both small and base checkpoints on this artifact. The results below remain the
original whole-text diagnostic; no neural extractor is enabled in the application.

## Open-source candidates and data

| Resource | Verified interface or purpose | Published license | Decision |
| --- | --- | --- | --- |
| [GLiNER2](https://github.com/fastino-ai/GLiNER2) and [GLiNER2.5 small](https://huggingface.co/fastino/gliner2.5-small-v1) | Entity spans, relations and span-conditioned attributes; small checkpoint is English, 74M parameters | Code Apache-2.0; selected checkpoint card Apache-2.0 | Small and base now measured in the linked follow-up; application extractor remains disabled. |
| [FinEntity](https://huggingface.co/datasets/yixuantt/FinEntity), [authors' repository](https://github.com/yixuantt/FinEntity), [EMNLP 2023 paper](https://aclanthology.org/2023.emnlp-main.956/) | Public entity/sentiment annotations for financial texts | Dataset card and repository state ODC-BY | Used for the diagnostic below, with attribution. Only aggregate results and hashes are committed; no source news or model training data is vendored. |
| [FinReflectKG-EvalBench](https://huggingface.co/datasets/domyn/FinReflectKG-EvalBench) | SEC-filing knowledge-graph evaluation with model-generated judgments | CC-BY-NC-4.0 | Research reference; not adopted as a commercial product dependency or human gold-label source. |

Dataset labels, model weights, code and underlying source content are separate
licensing surfaces. This table records the referenced declarations; it does not
establish redistribution rights over every underlying news article.

GLiNER2.5 attributes are conditioned on decoded entity spans. A document-level
classification schema would reproduce the scope problem. The small checkpoint
requires `AutoExtractor`, rather than the legacy `GLiNER2` loader. Returned offsets
are half-open character positions, not UTF-8 byte offsets. Character anchoring
already exists in `engine.news_context`; matching bytes still does not establish
sentiment correctness, company/ticker linking, or an event's time.

## Input and protocol

Dataset: Yixuan Tang, Yi Yang, Allen Huang, Andy Tam and Justin Tang,
*FinEntity: Entity-level Sentiment Classification for Financial Texts*, EMNLP 2023,
DOI [10.18653/v1/2023.emnlp-main.956](https://doi.org/10.18653/v1/2023.emnlp-main.956).

- [Pinned JSON](https://huggingface.co/datasets/yixuantt/FinEntity/resolve/e86e5451a1fce4731fe07c710649a229d92e5cab/FinEntity.json)
- Hugging Face revision: `e86e5451a1fce4731fe07c710649a229d92e5cab`
- Downloaded October 29, 2026 at `05:02:55.929928Z` (01:02 ET); 710,430 bytes.
- Raw SHA-256: `3208667de69383120b0380aebeaabe360669eda72269c33e1c8b09d63df55463`
- Runtime: Python 3.12.14; VADER package 3.3.2. Each result records the sentiment
  implementation file hash, selected backend, dataset hash and prediction-log hash.

The published JSON has 979 paragraphs and 2,131 annotations. Exact validation of
`text[start:end] == value` finds **70 offset mismatches** in 35 documents. The
annotated name occurs elsewhere in all 70 cases; offsets are not automatically
shifted. Another six entries in three other documents share duplicate/conflicting
spans. All 76 entries are excluded, with row/annotation IDs and reasons retained.
Twenty documents then have no usable annotations. This leaves **959 documents
and 2,055 anchored mentions**. This is a finding about this pinned artifact,
not a claim that all versions have these issues.

For each remaining document, call the existing local `engine.sentiment.score_text`
once on its complete `content` and broadcast its label to each valid gold mention.
VADER uses the existing financial lexicon and existing thresholds; the keyword
run uses the existing fallback and preprocessing. Backends are selected explicitly,
with FinBERT auto-loading bypassed. No models are downloaded, paid APIs called,
prices fetched, or thresholds tuned against these labels.

This is a **full-corpus diagnostic**, with gold entity spans supplied. It is not
the paper's 80/20 protocol, its span-and-label F1 evaluation, a holdout score,
an assessment of the deployed backend, or an entity extraction benchmark.
The input paragraphs also differ from the headline-only input in deep analysis.

## Measured results

Accuracy counts correctly classified gold mentions. Macro F1 averages the fixed
negative/neutral/positive classes with zero for a class whose F1 denominator is zero.

| Diagnostic | Mentions | Accuracy | Macro F1 |
| --- | ---: | ---: | ---: |
| VADER + existing financial lexicon, all anchored mentions | 2,055 | 42.92% | 42.95% |
| Existing keyword fallback, all anchored mentions | 2,055 | 55.28% | 44.65% |
| VADER, documents containing both positive and negative labels | 120 | 42.50% | 32.72% |
| Keyword fallback, same opposing-polarity subset | 120 | 20.00% | 20.54% |

The strictly validated data contains 127 mixed-label documents, of which 33 have
both positive and negative labels. The keyword baseline's higher overall accuracy
does not establish that it is the better company-level model: negative recall is
only 14.08%, and neutral mentions make up 1,079/2,055 of the evaluated set.

A majority label chosen using the complete evaluated gold corpus obtains 52.51%
accuracy. An oracle allowed to choose one optimal label **per document**, using
its gold labels, can obtain at most 1,910/2,055 = **92.94%**. These are gold-label
diagnostics, not deployable models or measured predictions. Even this per-document
oracle must mislabel 145 mentions when its label is broadcast to every entity.

Full confusion matrices, class metrics, subset denominators and excluded annotation
IDs are in [VADER results](../eval/history/news-entity/finentity-vader-2026-10-29.json)
and [keyword results](../eval/history/news-entity/finentity-keywords-2026-10-29.json).
No GLiNER2.5/FinBERT comparison, calibrated financial probability, trading-return
improvement or live-data accuracy is claimed.

## Code and reproduction

`python -m eval.news_entity_sentiment` accepts local JSON and requires its expected
SHA-256. It uses exclusive output creation and fails on invalid scorer labels.
Reports omit news text. Per-document prediction/hash records can be requested with
`--include-predictions`; their canonical hash is present in either form.

After obtaining the pinned dataset above, run from the repository root:

```bash
python -m eval.news_entity_sentiment \
  --input /path/to/FinEntity.json \
  --expected-sha256 3208667de69383120b0380aebeaabe360669eda72269c33e1c8b09d63df55463 \
  --dataset-revision e86e5451a1fce4731fe07c710649a229d92e5cab \
  --backend vader --output /path/to/new-vader-result.json
```

Repeat with `--backend keywords` and a different output path. The CLI has no data
download or transformer-model path. Synthetic tests check known confusion counts,
mixed polarities, Chinese offsets, wrong repeated-name offsets, duplicate and
conflicting annotations, malformed data, local backend selection and overwrite/hash
protection. Dataset downloads are not part of CI.

## Integrated scope records and next evaluation

Scored news, sentiment aggregates, deep-analysis audits and fusion source records
now expose `sentiment_scope="text_sequence"` and `target_sentiment="not_extracted"`.
The human news report and fusion explanation describe headline tone. Bounded model
news segments state that entity-specific sentiment and event time are unverified;
citation ledgers retain the unextracted target state. This metadata reaches normal
and SSE API responses, lite analysis and daily caches through the shared paths.
It does **not** remove or recalibrate the existing numerical news contribution to
signal fusion. Its directional weighting still needs separate evaluation.

Before replacing that contribution, freeze a document-level split with an explicit
annotation policy, then compare a span-conditioned extractor with these baselines.
Measure both gold-span sentiment and end-to-end span/label performance; test
company/ticker linking, repeated names, opposite targets and English/Chinese
separately. Report invalid/missing spans and abstentions in denominators. Resolve
publication time, acquisition time and event time separately; a time mention is not
automatically the event date. A successful local extraction test alone would not
establish trading value.
