# Local GLiNER2.5 experiment — October 29, 2026

**Decision:** keep the base checkpoint as a research candidate. Its entity-level
sentiment is substantially more useful than the existing whole-text baselines on
matched mentions in this diagnostic. The small checkpoint is not a suitable
replacement based on these measurements. Neither checkpoint is enabled in the
application or its numerical trading signals.

## What actually ran

Both public checkpoints ran on CPU in a separate environment: Python 3.12.14,
`gliner2==2.1.0`, `torch==2.9.1+cpu`, `transformers==4.57.3`, `peft==0.18.0`,
and VADER 3.3.2. Four Torch threads and batches of four were fixed. The
[full package lock](../eval/protocols/news-entity-gliner-runtime.txt) is recorded.
No neural package or model weights were added to application requirements.

| Checkpoint | Pinned revision | Actual safetensors bytes |
| --- | --- | ---: |
| [GLiNER2.5 small](https://huggingface.co/fastino/gliner2.5-small-v1) | `df5910e44bc4ffdb0d95399a83b0ca4516349aa5` | 295,567,700 |
| [GLiNER2.5 base](https://huggingface.co/fastino/gliner2.5-base-v1) | `54785d51df8d86a0d8f2eb212fec15871aad2c4d` | 774,366,564 |

Both selected model cards declare Apache-2.0. File hashes, actual package versions,
source hashes and protocol hashes are in each result. Hub downloads happened during
setup; inference used local checkpoint paths, `local_files_only=True`, and offline
Hub/Transformers flags. The loader emitted compatibility warnings about model type
and legacy tokenizer metadata; all measured batches completed without errors.

The [official span-attribute API](https://github.com/fastino-ai/GLiNER2/blob/main/tutorial/13-span_attributes.md)
was used through `AutoExtractor`, with one described `financial_entity` type and
qualified negative/neutral/positive sentiment labels. Entity threshold was fixed at
0.5. Attributes are attached to decoded spans; no gold locations were supplied to
the neural models. Thresholds, schema and class order were not tuned after results.

## Dataset and frozen selections

The input is the same pinned, attributed FinEntity artifact described in the
[baseline diagnostic](NEWS_ENTITY_RESEARCH.md): raw SHA-256
`3208667de69383120b0380aebeaabe360669eda72269c33e1c8b09d63df55463`.
The shared validator excludes 70 wrong-offset and six duplicate/conflicting
annotations, leaving 959 usable paragraphs and 2,055 reference mentions. Refactoring
this validator preserved both previous VADER/keyword diagnostic reports exactly.

The first protocol fixed a seeded random sample of 128 documents plus all 33
opposing-polarity documents (153 unique documents). After the first run demonstrated
adequate CPU throughput, a separate full-corpus protocol retained the same schema
and threshold. The base comparison also used the full corpus with unchanged schema.
All selections and checkpoint revisions were written before their respective runs.
These are exploratory full-corpus diagnostics: baseline labels were previously
inspected, no blinded holdout or preregistration is claimed, and pretraining
contamination is unknown. Cohorts overlap and must not be pooled.

## Results on the full corpus

All rows, including empty extractions, stay in recall denominators. Extra, invalid
and duplicate outputs remain in precision denominators. Exact character boundaries
must match; no fuzzy correction, name searching, or implicit-company linking occurs.

| Checkpoint | Exact entity precision | Exact entity recall | Entity F1 | Exact entity + sentiment F1 |
| --- | ---: | ---: | ---: | ---: |
| Small | 61.37% | 78.78% | 69.00% | 35.41% |
| Base | 69.11% | 85.35% | 76.38% | 60.66% |

Small predicted 2,638 entities: 1,619 matched a reference span, and 831 also had the
correct sentiment. Base predicted 2,538: 1,754 matched, and 1,393 also had the correct
sentiment. There were zero inference errors and zero invalid character spans in
these runs. False positives are reference-relative: unannotated entities, annotation
policy differences and boundary differences are not necessarily invented entities.

The table below controls the target set **within each checkpoint**: broadcast the
existing document classifier's label onto exactly the same matched gold spans.
These conditional scores omit missed entities; use the joint F1 above to account
for detection failures. The two checkpoints have different matched sets.

| Matched target set | Method | Sentiment accuracy | Sentiment macro F1 |
| --- | --- | ---: | ---: |
| Small: 1,619 mentions | Span-conditioned small | 51.33% | 48.66% |
| Same 1,619 | VADER + existing financial lexicon | 42.80% | 43.17% |
| Same 1,619 | Existing keyword fallback | 55.96% | 45.11% |
| Base: 1,754 mentions | Span-conditioned base | 79.42% | 79.18% |
| Same 1,754 | VADER + existing financial lexicon | 43.44% | 43.77% |
| Same 1,754 | Existing keyword fallback | 56.67% | 45.14% |

On the 33 opposing-polarity documents (120 gold mentions), joint F1 was 29.01% for
small and 54.69% for base. Base sentiment accuracy was 75.28% on its 89 matched
mentions; VADER on those same 89 obtained 46.07%. This is a targeted diagnostic,
not an additional independent sample. Eighteen conditional confusion-matrix metric
sets were independently checked against scikit-learn accuracy and macro F1.

Measured full-corpus batch wall time, excluding model load, was about 51.49 seconds
for small and 128.13 seconds for base. Per-row timing fields allocate batch time
equally; they are not serial response latency or a production performance promise.

An initial [synthetic reversal smoke test](../eval/history/news-entity/gliner-small-reversal-smoke-2026-10-29.json)
showed why detection and sentiment must be checked separately: small correctly
located Nvidia in both variants, but kept a positive label when its profit changed
from rising to falling. This two-sentence illustration is not a benchmark score.
Detection confidence and attribute confidence are separate, uncalibrated outputs.

## Artifacts and reproduction

- [Small seeded sample result](../eval/history/news-entity/gliner-small-sample-2026-10-29.json)
- [Small full-corpus result](../eval/history/news-entity/gliner-small-full-2026-10-29.json)
- [Base full-corpus result](../eval/history/news-entity/gliner-base-full-2026-10-29.json)
- Protocols: [small sample](../eval/protocols/news-entity-gliner-small-v1.json),
  [small full corpus](../eval/protocols/news-entity-gliner-small-full-v1.json),
  [base full corpus](../eval/protocols/news-entity-gliner-base-full-v1.json).

Use a separate environment with the recorded package versions. Obtain the pinned
dataset and the checkpoint's five files named in the result's `model_manifest`;
save that manifest as a JSON file. Re-run from the repository root:

```bash
python -m eval.run_news_entity_probe \
  --input /path/to/FinEntity.json \
  --protocol eval/protocols/news-entity-gliner-base-full-v1.json \
  --model-dir /path/to/local-base-checkpoint \
  --model-manifest /path/to/base-manifest.json \
  --predictions /path/to/new-predictions.jsonl \
  --output /path/to/new-result.json
```

The driver checks input/checkpoint hashes, package and revision identities, and
uses exclusive outputs. Every frozen row must have a prediction record; batch
failures become explicit error records with false negatives. Partial logs cannot
be scored as complete. Original news is not included in the committed reports.
Synthetic CI tests cover these contracts without neural package installation or
model download. This experiment changes no deployed model or trading decision.

## Next evidence needed

Base warrants a separate integration experiment for **research assistance**. Before
using it as a ticker-specific trading contribution, measure company/ticker linking,
headline-only input, unmentioned/implicit entities, fresh independently annotated
examples, temporal claims and abstention behavior. An explicit span does not prove
which listed security is affected, when an event happened, or a future price effect.
The newer [FinER-ABSA paper](https://aclanthology.org/2026.lrec-1.149/) identifies
implicit-entity reasoning as a separate benchmark problem; its dataset and license
were not adopted or evaluated here. No calibrated confidence, held-out accuracy,
causal market effect or trading-return improvement follows from this diagnostic.
