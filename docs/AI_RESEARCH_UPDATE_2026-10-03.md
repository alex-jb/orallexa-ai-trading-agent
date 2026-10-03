# Orallexa research update — 2026-10-03

## Decision

Continue the trading-research objective while making each result easier to inspect: dated source → bounded news task → recorded analysis → risk decision → paper outcome. The immediate engineering investment is **measurement and explanation**, with a separate prospective study still needed for trading value. No paper fill, profitability, customer adoption or new model accuracy is established by this update.

The sources below were checked on October 3, 2026. Dates distinguish current announcements from relevant earlier research. Observations, project adaptations and hypotheses are separate. University names do not constitute validation of Orallexa.

## Check of the shared briefing

**Confirmed: Anthropic Frontier Academy.** The [October 2 official announcement](https://www.anthropic.com/news/claude-frontier-academy) commits $100 million and targets 10,000 Frontier Deployed Engineers by the end of 2027. The first cohorts include consulting firms and financial institutions. The [program page](https://claude.com/programs/frontier-academy) describes four initial days, a 12-week organizational deployment and a practical assessment. Participation begins through organizational nomination; it is not an open individual certification signup. The target and first credentials are future outcomes. The briefing's IPO motive, valuation and assertion that graduates can work only with Claude are **not established** by this announcement.

**Partially corroborated: Karpathy's explanation formats.** The supplied [X post](https://x.com/karpathy/status/2105819303471976479) could not be read directly. A [mirror](https://x.twstalker.com/karpathy/status/2105819303471976479) and a [secondary October 3 report](https://eu.36kr.com/en/p/4009626690539397) describe controlled English, diagrams, interactive HTML and bespoke explainer videos. Treat attribution and completeness as provisional; this is not a peer-reviewed finding or evidence of comprehension gains. The adoption proposal below stands as a testable project design even without that attribution. Do not import an unknown Skill or pay for video generation to implement it.

## University research worth using

| Source and date | What the work supports | Concrete adaptation and boundary |
| --- | --- | --- |
| **MIT CSAIL — [RLCR: Beyond Binary Rewards](https://arxiv.org/abs/2507.16806)**. First submitted July 2025; revised May 15, 2026; [MIT explanation](https://news.mit.edu/2026/teaching-ai-models-to-say-im-not-sure-0422), April 22, 2026. | Training rewards can combine answer correctness with a proper probability score; the reported experiments improve calibration alongside accuracy. | Measure explicit probabilities against independently adjudicated news labels. Report the error/coverage tradeoff at locked thresholds. This is an evaluation adaptation, **not RLCR training**, a new model, or a calibrated probability of a stock rising. |
| **Stanford — [Why Do Safety Guardrails Degrade Across Languages?](https://arxiv.org/abs/2605.17173)**. Revised August 11, 2026; [university overview](https://news.stanford.edu/stories/2026/09/ai-benchmarking-measurement-research), September 25. | A single benchmark score can conflate model robustness, prompt hardness and language-related factors. | Separate event type, company relevance, abstention, evidence and probability coverage; expose language slices. This does not reproduce their latent-variable method or make slice differences causal. Chinese/English labels must be independently checked. |
| **CMU / EPFL / industry — [Human-Agent Audit Collaboration](https://arxiv.org/html/2609.24986v1)**. September 21, 2026 preprint. | In shopping-agent studies, AI assistance broadened exploration but also shaped human judgments. Practitioners needed coverage and reproducible trajectories, and the auditing agents themselves required evaluation. | Preserve input, observed output, proposed failure, human verdict and rerun status. Let a reviewer challenge an evidence card and rerun its deterministic checks. Shopping-agent findings are not a measured financial-agent effect; no human study has been run here. |
| **UC Berkeley BAIR — [Data Systems For, Of, and By Agents](https://bair.berkeley.edu/blog/2026/07/07/intelligence-is-free-now-what/)**. July 7, 2026 perspective. | Agent workloads motivate shared query results, structured corrective memory, failure recovery and verification of generated systems. The article explicitly combines a survey with proposed directions. | Keep source IDs, available times, model/rule versions and event groups in structured records; share factual retrieval across Bull/Bear arms while preserving separate interpretations. A cache must include the source version and as-of cutoff. Claimed duplication rates in the article are not Orallexa speedups. |
| **MIT CISR — [Designing Decision Rights for AI](https://cisr.mit.edu/publication/2026_0601_AIDecisionMatrix_SebastianWeillHaskampVomBrocke)**. June 2026 briefing. | Organizational decisions can be allocated according to ambiguity and consequences, with different responsibilities for framing, acting and learning. | Automate repeatable source/schema checks, reserve ambiguous evidence judgment for a reviewer and retain deterministic paper-execution controls. This is a workflow framework, not a trading strategy or universal human-approval requirement. |
| **Stanford — [Paper2Agent, Nature](https://www.nature.com/articles/s41586-026-11044-y)**. Published September 16, 2026. | The framework exposes paper-associated code, data, methods, resources and prompts through MCP tools, testing them against reference outputs. The reported demonstrations are biomedical analyses. | A later read-only Orallexa research interface could invoke the pinned news scorer or audit replay and explain the returned report. Tool reproduction must retain source/commit references and tolerances. The paper does not establish financial accuracy, and Paper2Agent/MCP generation has not been installed or run here. |

For a more specific memory technique, Berkeley's [Tk-Boost paper](https://arxiv.org/abs/2602.13521), revised February 17, 2026, indexes corrective knowledge by the query conditions where it applies. Its evaluated task is natural-language-to-SQL, not trading. A later Orallexa analogue could retrieve a correction such as “use availability time rather than publication time” only for the relevant source/query operation. Develop those corrections on training examples, version them, and test on new events; do not turn held-out failures or future returns into a memory advantage during evaluation. This has not been implemented here.

## Market evidence and product implication

The [October 1 Anthropic/Barclays announcement](https://www.anthropic.com/news/barclays-scales-claude) describes a deployed retrieval-based knowledge assistant and email classification/enrichment in Global Markets, plus planned developer rollout. These are concrete examples of source retrieval, bounded classification and workflow integration. Its adoption and throughput figures are a vendor/customer report, not an independent efficiency study or a stock-selection result.

The [Aladdin/Forrester 2026 report](https://www.blackrock.com/aladdin/discover/report/ai-in-investment-management) surveyed 303 senior investment professionals during May–July. It reports operational efficiency more often than new strategies, and identifies fragmented systems and legacy technology as barriers. This is a commissioned, self-reported sample; it does not establish market size, causal ROI or open jobs.

**Inference for Orallexa:** start with an evidence-linked research brief that a person can inspect and correct. Keep the trading experiment as a separately scored component. Test three user problems before claiming a market: time spent checking a research brief, time spent diagnosing a data/order exception, and the ability to find what changed between decisions. For Alex's FDE / solutions-engineering direction, this is a plausible way to demonstrate integration and user explanation. It is not an Aladdin integration or a hiring guarantee. The Academy's nomination route should not be presented as a personal enrollment opportunity.

## Implementation in existing draft #34

The offline news scorer now reports:

1. A locked **company-relevance** confidence threshold curve, including accepted cases, the full-cohort coverage denominator, relevance errors and joint event/relevance correctness.
2. Separate withholding counts for model abstention and missing probabilities. Failed calls stay in the cohort and original cost/latency totals. Empty accepted sets produce `null` error rates, not perfect scores.
3. Per-language case/event-group counts, classification diagnostics, probability coverage and the same threshold curves. Missing metadata is `und`, without inferred language. Incomplete probability coverage still withholds the corresponding full-cohort Brier score.
4. Report schema v2, threshold provenance and byte hashes that change when manifest thresholds or language tags change. There is no automated selection of a winning threshold and no deployment route.

Local validation: **46 synthetic tests passed** for the existing and new accounting/input behavior. These tests contain no authentic news labels or model outputs. They do not rank providers. Jev/Claude/other models have not been called in this work, and no broker path changes. Custom thresholds, metadata policies, source snapshots and the scorer commit must be frozen before real results exist; file hashes cannot attest that preregistration happened.

The probability is **P(article explicitly concerns this company)**. It is not P(price increases), model trustworthiness, permission to trade or a calibrated confidence for the event category. Any later routing rule requires development-only selection and a separate locked test, including coverage/cost constraints.

## Next research experiment

Before provider evaluation, produce a rights-cleared, time-stamped cohort with two independent annotators and adjudication. A bilingual cohort is a proposal, not an existing dataset. Fix event precedence, language and mixed-language policy, abstention treatment and source availability; group translations and multi-ticker stories under one underlying event, and keep that group in one split. Reserve a representative prospective stream after development. News-label correctness cannot substitute for later forecast outcomes.

Compare fixed rules and available model arms on the same frozen examples. Keep task labels, citation capability, complete-cohort probability scoring, selective error/coverage, latency and measured bills separate. Predeclare one primary comparison. Estimate uncertainty by event clusters before ranking models; report slices with counts and avoid independent-sample claims for translations. Do not tune a threshold on the test curves.

For the explanation interface, compare a plain report with a read-only evidence card that shows the source/date, input/rule version, recorded result, refusal reason and unresolved questions. Test whether a reader can locate an injected error, reproduce a calculation and explain a refusal; measure time and wrong approvals. A more attractive page or longer generated explanation is not proof of understanding. This interface and user study are **next work**, not shipped functionality.

The Paper2Agent-inspired follow-up would expose only bounded research operations such as scoring an already frozen, approved local cohort and retrieving its metric definitions. First reproduce the CLI output at an exact code/input hash, then test a read-only MCP wrapper against that result with fixed fixtures. Keep file access restricted to the approved cohort and keep broker, provider credentials and arbitrary shell execution out of its tool set. A human-facing explanation must cite the returned numbers and definitions rather than inventing a rationale. This is an implementation proposal, not a deployed server or an adoption of every worker-agent step from the paper.

## Repository snapshot checked today

- `master` is still `794a2ec0ce0b1271b468814eee47c2cd4edde147`. All listed proposals remain open drafts.
- Security review chain: **#13 → #19 → #26**. The implemented changes are still absent from master.
- The paper chain reaches **#38**, which binds a persistent pilot identity, broker IDs and ledger checkpoints and includes sibling decision replay. Its PR reports local synthetic checks; this turn has not rerun that stack or observed an Alpaca paper fill. First-anchor completeness and broker truth remain limitations.
- **#39** contains a later opportunity map; **#40** implements an order-free ICAIF weight baseline. Neither constitutes competition registration, real data access, contest submission or performance evidence. Treat the old September 30 deadline table as historical and consult current organizer portals before acting.
- This update extends **#31** and **#34** rather than creating another draft branch or merging existing ones. There are overlapping older alternatives (#21/#24, #22/#27, #23/#25); their existence is a reason for integration review, not to merge every open PR mechanically.

## 中文说明

我们继续做交易研究，同时让结果更容易检查。MIT 的启发是检查模型的自信是否可靠；Stanford 的启发是把不同能力分别测，并看中英文差异；CMU 的启发是保留人工判断和可重复检查过程；Berkeley 的启发是用有版本、有时间的数据记录帮助代理协作。

本轮已改的是新闻离线评分器：它会显示高置信度回答覆盖了多少样本、错了多少，以及不同语言分别表现怎样。真实新闻数据和模型比较还没有完成。下一步需要独立标注的数据，然后才有资格说哪个模型更适合我们。
