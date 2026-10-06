# CLM-8B company-news shadow study — design, not results

This protocol specifies a future comparison for Orallexa's existing news task. It creates no model configuration, human label, prediction or deployment. The public four-headline pilot in draft #34 remains development material with eight unreviewed cases and two event groups.

## What was actually checked

- Read the [author model card](https://huggingface.co/Contrastive-LM/CLM-v0.1-8B) and upstream source at commit `d5f9ef0fd9bde185df0ceaad4f4ecc6cfe8c34f6`.
- Execute only the upstream, standard-library `src/clm/schema.py` functions with invented distributions/logits. The [saved probe](examples/CLM_SCHEMA_PROBE_2026-10-06.json) includes the exact source-file hash and seven passing assertions.
- Load no encoder or projection weights, start no server, install no CLM package and make no inference/provider/broker call. The probe checks field meaning, not model quality, latency, calibration or end-to-end API compatibility.

The inspected upstream README/source describe separate state/action computations and reusable embeddings; the model card specifies the frozen Qwen3-8B encoder. Reported speedups concern the authors' tasks, and verifier results use fine-tuned heads. Those claims are not Orallexa measurements. No immutable weight revision or checkpoint hash has been verified here.

## Map each field to one task

| Upstream field | Observed schema meaning | Planned use |
| --- | --- | --- |
| `Noul.noul` | Mass on the affirmative option of the supplied binary question. | Estimated P(input explicitly concerns the named company), only when the frozen instructions ask exactly that question. Validate against adjudicated labels; do not claim calibration beforehand. |
| `Choice.choice` | Highest-scoring candidate key. | Primary event among the same four descriptions: earnings, guidance, regulatory, other. |
| `Choice.probabilities` | A distribution over the supplied candidate set. | Event diagnostics, retained separately from binary relevance. |
| `Choice.confidence` | Top candidate probability minus the mean probability of other candidates. | Preserve as upstream metadata; never substitute it for the scorer's binary relevance probability. |
| `Score.score` | Expected index of the supplied ordered levels. | No mapping into the current event/relevance scorer. |
| `usage.input_tokens` | In the inspected engine/embedder, encoder tokens spent on cache misses. | Report with cache state; do not interpret as complete presented-text length or a monetary bill. |

Source inspection: [`schema.py`](https://github.com/Contrastive-LM/CLM/blob/d5f9ef0fd9bde185df0ceaad4f4ecc6cfe8c34f6/src/clm/schema.py), [`engine.py`](https://github.com/Contrastive-LM/CLM/blob/d5f9ef0fd9bde185df0ceaad4f4ecc6cfe8c34f6/src/clm/engine.py), [`embedder.py`](https://github.com/Contrastive-LM/CLM/blob/d5f9ef0fd9bde185df0ceaad4f4ecc6cfe8c34f6/src/clm/embedder.py). These were read locally at the pinned commit. Web extraction of the pinned file pages failed; the repository itself and model card were retrievable.

The synthetic probe makes two differences visible. A four-way distribution of `[0.55, 0.15, 0.15, 0.15]` produces `confidence=0.40`. With fixed invented logits, adding a third candidate changes the first candidate's softmax mass from about 0.881 to 0.787. These are mathematical examples, not actual CLM news predictions. Candidate wording, membership, order, temperature and question rendering must therefore be fixed before evaluation.

## Comparison to prepare after real labels exist

Use the same adjudicated input cohort for three initial arms: a pinned deterministic alias/keyword baseline, the existing generative-model news baseline, and the reference CLM checkpoint without fine-tuning. A Jev arm can be added only after its exact available model/version, response semantics and price are documented. No provider is configured or invoked by this document.

The primary endpoint is full-cohort **binary company-relevance macro F1**. Primary event macro F1 and event-plus-relevance correctness are secondary diagnostics. Failed calls and abstentions remain in all full-cohort denominators. Probability coverage, Brier where fully observed, latency and measured cost are reported separately. Evidence exact match is N/A for classification-only CLM/rule arms; a future fixed candidate-span question would be a separate, equivalently specified evidence experiment.

Keep development events separate from a prospective held-out stream. Freeze source rights, actual acquisition/capture times, event groups, label precedence, alias policy, question strings, candidate descriptions, model/checkpoint revisions, temperature and code versions. Collect two independent blind reviews and explicit adjudication before generating gold. The current English headline seed cannot establish four-event coverage, language generalization or a representative alert rate.

For uncertainty, use paired event-cluster resampling in a separately implemented analysis and predeclare the comparison family/multiplicity procedure before results. Eight correlated development rows do not support model rankings or confidence intervals. Any recalibration/fine-tuning uses development data only and becomes a separately named arm.

## Actual input and performance receipts

The upstream quickstart and inspected embedder default to a 2,048-token truncation request. Preserve both the archived source and the exact rendered state/question/candidate texts, their hashes, tokenizer/revision and effective limit. Check length before a future call; retain over-limit cases under a predeclared failure policy instead of silently clipping or dropping them. No truncation behavior was reproduced in this schema-only probe.

Pin the Qwen encoder/tokenizer revision, pooling mode, projection-head file hash, serving version, GPU/runtime and both server token limits before model inference. Resolve weight identities separately from the source commit; a moving `clm-latest` name or automatic download is not an immutable configuration.

Measure cold and warm cache conditions on the same cases as distinct performance runs. Record cache capacity/hits/misses, candidate count, batching, queueing, encoder-plus-head wall time, failures and observed resource/provider charges. Ensure embedding caches are invalidated when encoder, pooling, tokenizer, truncation or checkpoint configuration changes. The authors' large-candidate speedups cannot be assumed for two/four options, and zero generated tokens do not imply zero compute cost.

Preserve raw outputs and parser failures. A later adapter must validate complete case/model coverage and write the scorer's JSONL without inventing usage, bills or evidence. It must also bind the actual rendered input receipts; source-file equality alone does not prove what the server consumed. This adapter and model runner have not been implemented.

## 中文说明

CLM 可以先作为新闻筛选候选：一题判断“有没有明确涉及这家公司”，另一题判断新闻类型。它的候选分数、分差字段和股票涨跌概率有各自的含义，不能混用。

本轮只用人工给定的数字检查了输出格式。真正的模型比较还需要独立人工标签、固定版本和实际运行记录。先测筛选质量及总耗时，再考虑接入研究简报；交易价值需要另外评估。
