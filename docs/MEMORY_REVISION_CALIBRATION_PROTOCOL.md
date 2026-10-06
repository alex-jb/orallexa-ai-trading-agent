# Memory revision and probability evaluation protocol

Design only, 2026-10-06. Continues the [continuous monitoring protocol](CONTINUOUS_NEWS_MONITORING_PROTOCOL.md) and [news quality/cost protocol](NEWS_PIPELINE_QUALITY_COST_PROTOCOL.md). No dataset, model comparison, live calibration, Graphiti deployment, or provider connection is supplied here.

## Distinct questions

Keep three quantities separate: whether a source version was available at the decision cutoff, whether a supplied memory proposition influenced the answer within its assigned scope, and whether an explicit probability matches later outcomes. A retrieval score, UI confidence capped at 82, memory-use level, and probability of positive return are not interchangeable.

For probability outputs, name the event and horizon. Examples: P(article explicitly concerns company X), P(a stated event category is correct), and P(log return from a specified reference price to a fixed target time is positive). Each requires different labels. Trading profitability additionally requires costs and an execution policy; it does not follow from any one score.

## Immutable versions and two clocks

Each source version records `source_id`, `version_id`, content hash, original source bytes or authorized snapshot, `published_at`, `first_observed_at`, and an availability justification. Preserve publisher correction timestamps where supplied. The event time and the time this system learned a statement are separate.

Each derived memory records its source version ids, all parent memory ids, derivation creation time, model/prompt identity, and a new immutable revision id. A correction or supersession is appended as a relation/version event; it never silently replaces the earlier record. A content hash establishes identity, not source authenticity or complete lineage.

For reused historical artifacts at cutoff T, require source availability and each ancestor outcome availability at or before T, and require their actual derivation creation times at or before T. Replay-time reconstruction performed today from a strictly filtered historical prefix is a separately named arm; its present creation timestamp must not be represented as a memory that actually existed at T. Historical reconstruction does not exclude pretraining contamination by itself.

Select the latest revision available under the requested knowledge cutoff before interpreting its event-time interval. A current-truth reconstruction using later corrections is different from what the agent could have known then. Retrospective QA and prediction replay must declare these views separately.

Example: an initial statement is observed at 09:05. At 11:00 a correction says the state changed at 09:30. A 10:00 knowledge-cutoff replay retains the original version then available; a present retrospective question about the 10:00 event state may use the correction. Date-filter predicates over a mutated current record are insufficient evidence that both views are implemented correctly.

Unknown availability, missing source versions, mixed/ambiguous timezones, and unresolved lineage are recorded as exclusions or abstentions. Normalize to aware UTC with the source offset retained. Define equality at the cutoff explicitly. Assess both versions of a correction together, never split them across development and test.

## State selection and memory use

Adjudicated items identify the requested state view (current, historical, transition), source versions available at the knowledge cutoff, and atom-level desired influence: Ignore, Bound, or Control. Give each atom a response rubric that identifies observable answer criteria, including acceptable scope and decisive constraints. These are an adaptation inspired by [MemCalib](https://arxiv.org/html/2609.24259v2) and [A-TMA](https://arxiv.org/html/2607.01935v2), not a reproduction of either benchmark or training method.

Report errors at three stages: incorrect preservation/version roles, incorrect candidate/packet selection, and incorrect answer state or proposition use despite adequate evidence. Trace ids connect the answer to the selected version. Evidence-support and memory-use judges require independent human checks, including rare Bound/Control and stale/current boundaries. Overall agreement can hide these boundaries; report confusion matrices, denominators, and disagreements.

Predeclare paired arms using the same queue, source availability, model, query and generation settings: current baseline; explicit source/version/state labels; removal of relevant history; and provision of independently adjudicated key history. The final arm is a diagnostic oracle, not an equally deployable competitor. Keep irrelevant/obsolete distractors available only where the arm permits them. Removing an atom changes the answer context and supports a behavioral diagnostic, not proof of internal causal attribution.

Use source/event clusters and chronological development/test separation. Tune state labels, prompts, gates, and thresholds on development only. Annotators apply rubrics without seeing arm identities or model claims. No fabricated synthetic fixture becomes a real financial accuracy label. Synthetic source probes validate mechanics only.

## Probability evaluation on future outcomes

Only forecasts with valid event semantics, finite values in [0,1], and independently resolved labels enter probability scoring. Track invalid, abstained, unresolved and excluded cases alongside the full issued queue. Assign a resolution availability time, not merely the event's originally scheduled end time. Never discard difficult resolved misses through outcome-dependent filters.

Use Brier and log loss for probabilistic classification, plus fixed-bin reliability estimates with mean predicted probability, empirical frequency, denominators and uncertainty. Brier mixes calibration and resolution; it is not a stand-alone calibration-error estimate. If output includes a fixed-nominal prediction interval, report empirical hit count/denominator, interval width and interval score. In particular N=3 unweighted hit coverage cannot be 0.81–0.83; alternative weighting/denominators must be documented.

Fit post-hoc calibration on previously available resolved outcomes only. Select mapping, regularization and thresholds without access to the locked future test. Compare raw and calibrated predictions on the exact same subsequent events. Training-set Brier improvement and accuracy increasing across confidence buckets are not deployment criteria.

Cold-start behavior must preserve every valid raw probability unless a separately justified baseline is explicitly selected and labeled. Cover intermediate values as well as endpoints and 0.5. Maintain distinct raw, calibrated and UI display fields; rounding/capping must not silently change the scored probability. Include the maximum display value in a bucket or account for it explicitly. Verify sum of bucket counts equals the valid evaluated count.

Baselines include 0.5 and an availability-filtered rolling base rate; add an appropriate price/market baseline where event semantics permit it. Lock the horizon, return definition, interval level, denominator and missing-label policy. Use paired cluster-aware uncertainty calculations, with regime/stress slices chosen before test results. A small pilot does not establish model superiority, robustness or profit.

## Cost and implementation boundaries

Any future per-prompt model-routing arm counts extraction, deduplication, timestamp inference, memory writes, embeddings, query analysis, retrieval, reranking, synthesis, retries and failures. Include infrastructure/storage and actual billable usage when available. Report excluded or estimated costs explicitly. Local query construction and synthetic Brier arithmetic are not measurements of inference latency or cost.

Before adopting Graphiti, test actual backend query semantics for multiple OR date ranges and immutable historical revisions; the [local source probe](examples/probe_memory_calibration.py) only establishes generated parameter bindings and selected mutation behavior. For a managed memory service, verify historical-cutoff access, version export, scoped isolation and service eligibility on an authorized test tenant before claiming equivalence. No such test was run in this research turn.

## Reproduce the bounded source probes

Use an Orallexa repository retaining commit `9bdb4d955d006a04159feb2d8b8b207402ddc33d`. The script reads fixed Git blobs, independently of later worktree edits. Obtain the seven Graphiti source files listed in the script from commit `689de295c209631405c00e19e0af4f9735142f13`; the expected Git blob identities are embedded and verified before AST evaluation. A snapshot directory is sufficient; Graphiti package installation is unnecessary.

```bash
python docs/examples/probe_memory_calibration.py \
  --graphiti-root /path/to/pinned-graphiti-source \
  --orallexa-root /path/to/orallexa-repository \
  --output /path/to/new-memory-calibration-receipt.json
```

An existing output is rejected. The [saved receipt](examples/MEMORY_CALIBRATION_PROBE_2026-10-06.json) records source hashes, 26 case inputs/outcomes, script identity and explicit non-performed work. It proves neither full retrieval correctness nor calibration on financial outcomes.
