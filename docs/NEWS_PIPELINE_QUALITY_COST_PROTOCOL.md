# News research quality and total-cost study — design only

This is a prospective experiment specification. It configures no provider and
creates no prediction, human judgement or trading result. The [CLM classifier
protocol](CLM_NEWS_SHADOW_PROTOCOL.md) remains a separate study with binary
company-relevance macro F1 as its primary endpoint. The unlabelled development
seed in draft [#34](https://github.com/alex-jb/orallexa-ai-trading-agent/pull/34)
does not constitute a held-out test or a reference financial brief.

## Question and fixed task

For the same source-grounded company-news cohort, can a screening stage reduce
the total resources needed to produce acceptable brief items without increasing
missed relevant items or unsupported claims?

Freeze the source bundle, company aliases, actual availability cutoff, prior
information needed to identify a change, permitted tools, output schema and
maximum brief scope. Specify whether inputs are excerpts or full articles.
Current four-headline development material alone cannot support a richer
financial-analysis task or general alert-rate claims.

Collect independent, blind relevance/event labels as specified in #34. A brief
study additionally needs reference material defining the required change and
atomic facts, plus a separate blinded assessment of produced brief items.
Existing classifier gold cannot substitute for this assessment. Freeze the
rubric, reference facts and adjudication procedure before inspecting outputs.
Evaluation reviewers must not see model names or cost results.

Use a prospective cohort with event-group separation from development examples.
Predeclare sample size, stopping rule, exclusions, repeated-run plan and a
paired event-cluster uncertainty procedure after a development feasibility
study. No test-set tuning, optional stopping on promising results or reuse of
held-out corrections in agent memory is permitted by this study design.

## Initial arms and later routing question

| Arm | Fixed behavior | What must be counted |
| --- | --- | --- |
| Existing workflow | Current generation-based news research, with pinned prompts/models and a declared retry policy. | Every model/tool attempt, including failed and discarded work. |
| Rule screen + research | Frozen alias/keyword screen followed by the same downstream research task for selected items. | Screening, downstream work and missed-item outcomes. |
| CLM screen + research | Frozen binary relevance question and development-selected routing threshold, then the same downstream task. | Encoder/head resources, cache state, downstream work and missed-item outcomes. |

Lock thresholds and resource configurations before the held-out run. Preserve
all cases in every arm; a screened-out relevant item is a miss, not a free
successful completion. Explicitly name abstentions and provider/parser errors.
Keep presented-text length separate from CLM cache-miss token usage.

Study state-dependent role selection as a later comparison with the model,
sources, roles, permissions and output rubric held fixed. Compare the existing
order against choosing a permitted next role from the current evidence gaps.
Charge routing to the same lifecycle budget. Vary contracts and verification
separately if their individual effects are the question. RAC's advisory
`supported` verdict does not replace task correctness, source validation or
existing permission/risk enforcement.

## Outcomes and denominators

The pipeline primary endpoint is the **full-cohort acceptable-output rate**.
For a relevant case, acceptance requires correct entity/event, coverage of the
predeclared key change and support for each required atomic claim from the
frozen source bundle. For an irrelevant case, acceptance requires correct
withholding under the rubric. Budget exits, missed relevant cases, failed calls
and unsupported outputs remain in the full denominator as non-acceptable.

Report relevant/irrelevant slices with their counts. Secondary outcomes include
missed relevant items, false alerts, unsupported-claim incidence, correction
time and classifier metrics. Keep publication/capture time mistakes visible.
No result here measures price direction or trading value.

Report both cohort total cost and cost per acceptable positive brief: divide
**all** cohort-attributable run costs by the number of acceptable positive
briefs, rather than charging only successful runs. If none succeed, return
undefined with the full cost and counts. Also show per-input cost so correct
withholding is visible. Interpret these ratios only for the declared cohort;
its event mix and relevant-item prevalence affect the ratios.

## Receipt and accounting requirements

Each attempt needs case/event-group ID, arm/run ID, exact model/runtime and
source/prompt/candidate revisions, rendered input/output hashes, UTC start/end,
termination reason, retry parent, tool calls, queueing and observed usage.
Preserve raw responses and exceptions when authorized. The cost receipt must
distinguish observed usage, published-tariff estimates, observed provider charges
and actual invoice reconciliation; one status cannot silently stand in for the
next. An author summary with empty raw responses is a reaggregation input,
not a replayable or billing-verified trace.

Separate fresh input, cache reads, cache writes, output and reasoning according
to the provider's semantics. State explicitly whether reasoning is already in
output totals. Retain the effective price date, negotiated/batch/off-peak terms,
request identifiers and available charging evidence. Do not double-count
thinking tokens, or call a failed request free when usage is missing.

For locally served CLM, report observed encoder-plus-head wall time, actual
resource allocation and cold/warm cache conditions. GPU rental or amortized
cost assumptions need their own labelled calculation and utilization basis.
Zero generated tokens is not zero resource cost. A published checkpoint size
does not establish the memory footprint of the whole encoder and server.

Run-level accounting includes screening, generation, routing, in-loop checking,
retrieval/tool services and retries. Separately report external evaluation and
human review/correction time; include them when describing total study cost or
the product's full operating cost. Never present an excluded judge bill as a
complete experiment bill. Unknown cost stays unknown, with attempt/usage
coverage disclosed; avoid a point claim of savings if unknowns could change it.

Report p50/p95 latency and cost with the sample counts, empirical quantile rule
and failure treatment. Distinguish variation across different cases from
variation across repeated runs of the same case. Budget ceilings are configured
limits: an in-flight call can exceed a ceiling before its cost is known. Retain
the overage and stop subsequent work under the declared policy; do not clip
recorded spend to manufacture compliance.

## Decision before integration

Predeclare an acceptable-output noninferiority margin and operational limits
from the development study, not from held-out results. Estimate paired
differences with event-group uncertainty before ranking arms; define the
comparison family and multiplicity handling in advance. Investigate missing
usage and disagreement cases before claiming savings. Do not claim a calibrated
threshold, proven market demand or trading advantage from this experiment.

The immediate deliverable is an auditable offline cohort and receipt contract.
Actual independent gold, representative inputs, a pipeline runner, provider
configuration and performance measurement remain outstanding.

## Research basis

- [Price Reversal, v2](https://arxiv.org/html/2603.23971v2): task-level cost and
  historical pricing can rank models differently. See our [public-summary
  reaggregation and provenance limits](examples/AGENT_COST_SUBSET_RECOMPUTE_2026-10-06.json).
- [RAC, v1](https://arxiv.org/html/2610.00980v1): coordination/verification overhead
  and role selection are experimental variables; estimated inference cost
  excludes its external judge.
- [Earlier financial research note](AI_RESEARCH_UPDATE_2026-10-05.md): distinguish
  correctness from complete factual support. None of these external findings
  has established Orallexa quality or savings.
