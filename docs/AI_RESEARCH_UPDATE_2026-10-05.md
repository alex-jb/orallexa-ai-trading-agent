# Orallexa AI research update — 2026-10-05

## Decision

Advance the evidence workflow with a small real-source development seed and independently completed review records. Three current research signals support checking whether an output is grounded, repairable and economically useful. They do not establish model superiority or trading returns. Sources were checked October 5; dates below distinguish recent announcements from an undated dataset card.

The [October 4 note](AI_RESEARCH_UPDATE_2026-10-04.md) covers temporal validity and financial judgement. The [October 3 note](AI_RESEARCH_UPDATE_2026-10-03.md) remains the broader university and enterprise background.

## Three findings

| Primary source and date | Finding and boundary | Project implication |
| --- | --- | --- |
| **MIT CSAIL / Google / Northeastern — [InstructMesh](https://news.mit.edu/2026/instructmesh-tool-lets-users-repair-ai-3d-models-then-fabricate-them-1001)**, MIT announcement October 1. | The interface combines 3D generation with language-guided selective repair before fabrication. Users can identify a region, describe a problem and evaluate the resulting change. The reported demonstrations and novice study concern 3D objects; physical simulation is future work. | Inference: make a generated research result inspectable and correctable at a specific evidence item. Measure error discovery and successful correction before building a richer explanation interface. The annotation CLI is a local evidence workflow, not an implementation of InstructMesh or a completed user study. |
| **inclusionAI / Ant Group — [FinFIRST author dataset card](https://huggingface.co/datasets/inclusionAI/FinFIRST)**, V1 checked October 5; the card has no publication date. | The card describes 123 professionally authored/verified Chinese and English tasks. Its atomic rubrics distinguish fact acquisition, source verification, and computation/answer formation. It separately measures correct answers with incomplete evidence. The card lists Apache-2.0; the released tasks are financial research QA, not our four-label news classification task. | Record the archived input, source/evidence match and eventual human decision separately. Future numerical research needs its own source/date/unit checks and deterministic calculations. No dataset items or leaderboard results are imported as Orallexa gold or reproduced here. |
| **Anthropic — [What work can robots do?](https://www.anthropic.com/research/what-work-can-robots-do)**, September 30. | A Claude-assisted, task-weighted exposure study estimates that robots can perform 34% of U.S. working time in some settings, while only 0.3% of work is cost-competitive under its assumptions. Capability ratings and estimated task-time weights are model-assisted. Exposure is not observed adoption, employment displacement or a revenue forecast. | Inference: test completion, reliability and total workflow cost separately when assessing an AI product. For a research briefing, compare analyst checking time, false alerts and correction time against its operating cost. No customer ROI or market-size estimate has been measured. |

These are different tasks and evidence types: an interactive fabrication system, an author-released financial benchmark and an economic exposure study. Their findings cannot be pooled into a common model ranking. University or company affiliation is not validation of Orallexa.

## Concrete source collection

Existing draft [#34](https://github.com/alex-jb/orallexa-ai-trading-agent/pull/34) now contains `eval/data/news_source_pilot_2026-10-05/`: four actual Federal Reserve short headline excerpts, each queried against WFC and JPM. Eight cases share **two** event groups. Three releases describe stages of the same Wells Fargo enforcement lifecycle; the other is a FOMC headline. Group related updates together to avoid treating a familiar storyline as a separate held-out event.

The Board's [publication policy](https://www.federalreserve.gov/disclaimer.htm) says its information is public domain unless otherwise indicated. This selection uses attributed Board-authored text only. The pilot excludes full bodies, photographs, logos and linked third-party material. Its README and acquisition receipts document selection, original URLs, company aliases, transformation version and the fact that original HTML is not archived.

The manifest/bundle bind exact UTF-8 snapshot hashes and headline byte spans. Publication times come from the official releases; current input availability, extraction and freeze are recorded on October 5. Retrospective capture does not prove earlier market availability. The material is explicitly `sample_kind:development_pilot`, public and purposively selected. The schema's `test` split selects annotation rows; it does not create a held-out test. A model metadata placeholder is marked unselected, with no provider configured or predictions supplied.

This is a real-source **workflow seed**, not a representative corpus, bilingual evaluation or model comparison. All eight labels and reviewer IDs remain null. No gold JSONL or prediction JSONL is committed for the real pilot.

## Independent annotation workflow implemented in #34

`eval.news_annotation` now supports three local operations:

1. **Prepare:** recheck archived sources and create two separate blank reviewer files in a new directory. Both preserve every declared test case and bind the exact manifest/bundle hashes, source IDs/hashes, ticker and allowed evidence map.
2. **Compare:** retain pending/ambiguous cases, show agreement and differing event/relevance/evidence fields, and generate an unresolved adjudication template tied to both submissions' exact hashes. Agreement never becomes gold automatically.
3. **Finalize:** require two completed reviews with distinct claimed IDs and an explicit, valid adjudication with a reason for every case, including agreements. Reject changed submissions or sources, dropped cases and unresolved decisions. Preserve the review/adjudication hashes in scorer-compatible gold.

Reviewers must actually work independently and remain blind to model outputs and one another's labels until submission. The tool validates records; it cannot authenticate humans or prove independence. One reviewer may subsequently adjudicate, but the original two submissions are retained. Output directories/files must be new so existing human work is not overwritten. No model or broker is invoked.

Local validation: **121 tests pass** across news scoring, source preflight and annotation. Of these, 120 exercise synthetic records; one checks the real pilot's four source snapshots and eight still-unreviewed cases. Tests cover changed bytes/hashes, incomplete cohorts, conflicting/ambiguous reviews, claimed ID reuse, explicit adjudication even on agreement, scorer integration and preserving existing outputs. A direct comparison of the real blank submissions reports eight pending cases and readiness false. This is input/workflow validation, not empirical accuracy.

## Next empirical step

Have two independent reviewers annotate a separately planned cohort, adjudicate every case, then freeze a prospective test stream with model configurations and a primary endpoint. Preserve failures, repeated-event grouping, evidence coverage, latency and actual billed costs. The current headline pilot may exercise that procedure, but should remain development material.

A future financial QA experiment can borrow FinFIRST's decomposition without confusing a correct number with a fully supported research answer. A later valuation or trading study still needs separate labels and observed outcomes. The concrete product hypothesis is a briefing whose checking/correction time and false alerts are measured against its cost; demand and ROI remain untested.

This update extends existing draft [#31](https://github.com/alex-jb/orallexa-ai-trading-agent/pull/31). No draft is merged, no provider is called, and no trading outcome is claimed.

## 中文说明

本轮新增三条信号：MIT 的 InstructMesh 把生成后的局部修正做成可交互流程；FinFIRST 把取数、核验来源和计算分别评估；Anthropic 的机器人研究把技术能力与经济成本分别估计。对我们最有用的做法是让每个结果都有可检查的证据，并保留人工修正记录。

现有草稿已加入四份真实官方短标题、八个公司案例，以及“独立标注 → 比较分歧 → 逐条裁定”的工具。真实样本仍未标注，模型比较和交易收益尚未测量。121 项验证通过只说明流程和输入检查有效。
