# Continuous news monitoring and point-in-time memory protocol

Status: research design only, October 6, 2026. No runner, service, model route or order execution is implemented. Read with the [daytime research](AI_RESEARCH_DAYTIME_2026-10-06.md), [source-function probes](examples/TEMPORAL_MONITORING_PROBE_2026-10-06.json), and [quality / cost protocol](NEWS_PIPELINE_QUALITY_COST_PROTOCOL.md).

## Goal and controlled comparison

Measure whether watching independently changing information and analyzing relevant changes improves company-news reminders at a fixed quality requirement. Keep data access, reference events, model version, prompt, output contract and permissions fixed. Compare a prespecified fixed analysis schedule with a change-triggered schedule. The observer runs independently of agent output; target labels and future changes are unavailable to the agent.

Freeze the cohort and scoring rules before the comparison. Determine sample size from pilot uncertainty, with event-group rather than article-level partitioning. The earlier four-headline development seed is not a representative monitoring cohort and is not a source of independent event labels.

For each trial, record the window, timezone, initial baseline, target company / event identity, condition, latency tolerance, coverage requirement and terminal status. Candidate conditions include a new official disclosure or correction. Initially deliver a research reminder with a source link and dated evidence. Relative price conditions require an explicit baseline time and consistent instrument / adjustment convention. Financial observations and reminders remain different from trade decisions.

## Observer and event record

The observer stores immutable content versions and sequence numbers. Repeated URLs are not sufficient deduplication keys: a correction can change the same URL. An event record includes:

| Field | Meaning |
| --- | --- |
| `event_at` | Claimed occurrence time, including source granularity |
| `published_at` | Source publication time, if verifiable |
| `available_at` | First evidenced availability to the monitored system |
| `observed_at` | Actual observer acquisition time |
| `version_id`, `content_hash`, `parent_version` | Exact bytes, identity and revision relationship |
| `event_group`, `company_id` | Shared underlying event and entity mapping |
| `feed_status`, `sequence_id` | Freshness, gap detection and ordering |

An observation acquired today is not proof it was available to the system at an earlier market decision. Do not backdate availability from publication metadata. Date-only records are not suitable for intraday decisions without an explicit conservative availability policy. Normalize verified instants to aware UTC values while retaining the original timestamp and source granularity; reject ambiguous or missing required times instead of comparing raw strings.

A deterministic observer can detect byte or structured-field changes without an LLM. The proposed trigger admits relevant new versions for analysis; if semantic relevance needs a model, include that invocation in cost and quality measurements. Page chrome changes, repeated irrelevant changes, stale feeds and hidden content must appear in the workload. Persist deduplication and pending-event state across restart. Coalescing is allowed only under a fixed policy that preserves constituent IDs, corrections and latency bounds.

## Independent scoring and coverage

An independent, frozen reference timeline supplies target truth and first eligible observed time. Blind adjudication supplies semantic event judgments; self-reported agent success never supplies the label. Align the scoring clock with evidenced system availability, not unobserved occurrence time. Include persistent, short-lived and never-triggering conditions; SentinelBench's inspected 100 scenarios all model persistent conditions and do not establish performance on short-lived market events.

Report the full trial cohort, not only completed reminders:

| Measure | Required definition |
| --- | --- |
| Event recall | Fraction of eligible reference events detected within the prespecified tolerance |
| False reminders | Unsupported / premature reminders per monitored hour and fraction of no-event trials with any false reminder |
| Detection latency | Reminder time minus first eligible observed time; report p50 / p95 for detected events plus misses separately |
| Coverage | Proportion of the required window with a fresh observer and functioning detector; also longest unobserved gap |
| Duplicate / correction handling | Repeated event alerts and whether a material revision supersedes prior evidence |
| Terminal status | Completed, observed-to-deadline with no event, early stop, degraded feed, budget stop or error |

Define freshness and maximum gap before evaluation. Heartbeats alone do not prove that relevant content was observed or checked. A no-event trial passes only if the monitored window meets the coverage requirement and there is no false reminder. Silent early exit, feed loss and budget exhaustion are separate incomplete outcomes. Event arrival near the deadline, during a data gap or during restart must have a prespecified scoring treatment; do not remove those failures after seeing results.

Use a separate completion endpoint / status for “condition detected” and “window ended without condition.” Record any notification action directly, not just a preceding page visit. Never infer sustained observation from absence of a notification.

## Point-in-time memory comparison

Keep facts, user instructions and learned outcome-based experience as distinct record types. Every derived record identifies all contributing parent versions, creation time, extraction / distillation configuration and exact source-byte hashes. A hash identifies bytes only after it is compared with preserved source bytes; a nonempty string does not authenticate evidence.

At cutoff `T`, require the permitted evidence version to have evidenced availability at or before `T`. Outcome-based experience additionally requires every contributing outcome to resolve strictly before `T`. Apply the rule recursively through merges. Missing ancestry, unresolved outcomes, invalid times and unmatched source hashes make the experience ineligible. Also validate source chronology and the completeness of parent lineage against the recorded construction trace.

Later distillation of old documents is not automatically eligible at an old cutoff. A historical replay must use a saved artifact available then, or a clearly specified reconstruction using only eligible parents and fixed processing, separately assessed for hindsight and model-training contamination. The latter is not a contemporaneously available artifact. Keep revision and invalidation records rather than rewriting historical evidence. Changes to user preferences need effective-time handling independently of financial outcome resolution.

Compare no memory, representative-date-only filtering and complete-parent filtering under the same source access and model settings. Include an old summary merged with a newly resolved case, later correction, unknown publication time, date-only evidence, timezone offsets and a relevant fact superseded by newer eligible evidence. The saved probes check selected upstream functions; they do not implement this proposed policy.

Measure memory-dependent subsequent task completion with the original history, an appropriate history-removed control and an oracle-evidence control. Precheck whether the task really depends on history. Preserve failures of each control; two successes / failures in benchmark construction do not establish universal solvability. Use a streaming evaluation order in which new observations, corrections and tasks interleave, rather than importing all future history before the test.

## Costs, limits and decision

Use all-attempt accounting from the existing quality / cost protocol. Include observation, triggering, model analysis, memory construction / updates, retries, duplicate processing and failures. Report ingestion separately and amortize only over an explicit trial lifetime. Include p50 / p95 latency, feed freshness and any in-flight budget excess. No inference calls are expected for unchanged inputs in the proposed change-triggered condition, but that is a hypothesis to check, not a measured saving.

Compare paired event groups with uncertainty and the prespecified quality / coverage margin. A cheaper condition that stops early or misses events is not acceptable merely because it produced fewer reminders. Begin with offline replay, then a prospective passive pilot with independently assessed references. Recommendation value, user checking time, willingness to pay and trading utility remain separate downstream questions.
