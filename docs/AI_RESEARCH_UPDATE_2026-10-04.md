# Orallexa financial AI research update — 2026-10-04

## Decision

Keep three questions separate: whether news explicitly concerns a company, whether it changes the prior public information or valuation picture, and whether a subsequent trading decision adds value. The current news scorer answers the first classification question plus a primary event label. It does not answer the latter two. This update adds archived-input checking before collecting empirical model results; it does not produce a model ranking or returns.

Sources were checked on October 4. Relevant earlier papers are identified by their publication dates, rather than presented as announcements made today. The [October 3 university/enterprise note](AI_RESEARCH_UPDATE_2026-10-03.md) remains the broader background.

## Three research findings

| Primary source and date | Finding and its limits | Orallexa implication |
| --- | --- | --- |
| **Tsinghua / Stepfun and collaborators — [KTD-Fin](https://arxiv.org/html/2605.28359v1)**, May 27, 2026 preprint. | The benchmark masks stock identities/calendar information and separates market, style and stock-selection return components. Its reported LLM performance on CSI300 is largely explained by passive exposures. The observation channel is price/factors, not archived news; most models do not have the full masking-condition grid. | Use a separately specified historical-memory diagnostic and return attribution in a future trading study. Anonymizing a ticker in the current company-relevance task would change the task unless the entity mapping remains available. This update implements neither masking nor a Barra factor model. |
| **Xiamen / USTC / Chinese Academy of Sciences — [Does Training on Future Data Pay?](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7486919)**, written September 17; posted September 23, 2026 preprint. | Comparisons across financial time-series model vintages show that exposure to post-origin training data does not consistently increase measured predictive performance. The U.S.-trained reference often deteriorates; other training environments are more mixed. The information-set violation and its performance effect are different questions. | Record model revision, input availability and forecast origin separately, then measure economic outcomes on an origin-valid comparison. Poor performance does not establish temporal validity, and a clean source archive alone cannot establish a model's training cutoff. No vintage comparison is run here. |
| **Sonto — [Frontier Financial Judgement](https://www.sontoresearch.ai/site-assets/evals/frontier-financial-judgement/v1/frontier-financial-judgement.pdf)**, July 22, 2026 paper, [author-maintained evaluation](https://www.sontoresearch.ai/evals). | The task combines expert-labelled synthetic targets with real context and distinguishes newness, valuation importance and direction. Even its strongest reported agent matches all target labels on only 52.4% of cases. Its context false-positive estimate uses curated distractors, not independently expert-labelled negatives. | Treat joint correctness, false-alert burden, failed outputs and cost as separate diagnostics. A future valuation task needs its own labels and rubric; the present relevance scorer cannot inherit this leaderboard or assume every distractor is a known negative. |

These results motivate test design, not a conclusion that LLMs can or cannot profit in Orallexa's market. They are preprints or author reports, and the tasks, data and configurations differ from our pipeline. No external code was executed and no result was reproduced in this update.

## Dataset investigation

The [Sonto dataset page](https://www.sontoresearch.ai/evals/dataset) explicitly identifies the target events as synthetic and removes company names from key released fields. Its described real-context documents and expert targets are different objects. The page's existence does not establish a license to republish third-party articles or two independent annotators under our gold schema. Browser-extracted text did not expose a complete case download here. No benchmark items were imported as authentic company news or adjudicated Orallexa gold.

The current empirical gap therefore remains specific: a rights-documented source cohort, independent labels and observed provider outputs. A source preflight now makes the **input preparation** executable before those labels exist. This is progress in reproducibility, not a completed corpus or evaluation.

## Implemented in existing draft #34

- Add `eval/news_source_preflight.py`, callable before gold or predictions exist. It checks every declared train/test source and returns test-only review rows with null labels and reviewer ID, status `unreviewed`, and no selected evidence. It creates no human judgement.
- Bind exact local UTF-8 model-input snapshots to manifest SHA-256 values. Check every permitted evidence ID against a nonempty UTF-8 byte range and its own hash. Multiple ticker cases share one source record, whose publication/availability/hash/URL/rights declarations must match every case.
- Check declared publication ≤ availability ≤ capture ≤ freeze. Require bounded regular files within the bundle directory; reject path traversal, escaped symlinks, missing archives, conflicting metadata and incomplete evidence maps.
- Add scorer report schema v3 with explicit `metadata_only` or `snapshot_bytes_verified` mode and the exact bundle hash. Set manifest `require_source_bundle:true` before an empirical study's freeze to make omission fail. Legacy manifests keep their original metrics and can run in disclosed metadata-only mode.

The existing confidence/coverage and language metrics remain unchanged. Source checks do not call a model, broker or network service. Byte equality does not authenticate an article, timestamps, rights, actual provider input, reviewer independence or model pretraining. Acquisition receipts and transformation records still need to be retained; a retrospective capture cannot prove earlier forecast availability. An old output remains untouched after validation failure, so downstream use must require exit status 0 and current input hashes.

Validation: 90 synthetic tests pass across the scorer and source preflight, including tampering, UTF-8 evidence offsets, source completeness, capture ordering, shared-source metadata and failure without output replacement. The tests establish validation/accounting behaviour, not calibration, financial judgement or trading skill.

## Market hypothesis and next experiment

The concrete product hypothesis is a daily evidence-linked briefing: show the archived input, the specific change from prior information, its relevance to the company, the valuation question still unresolved and a reproducible calculation when applicable. Test analyst time saved and false alerts before claiming demand. Sonto's professional-analyst task helps define this workflow; it is not a market-size estimate or proof of customer willingness to pay.

For the first genuine cohort, document use rights and actual acquisition times, retain transformed-input provenance, freeze a selection policy and keep translations/multi-ticker coverage in the same event group. Preflight those files, then use independent blind annotation and adjudication. Select thresholds only on development events and preserve a separate prospective test stream. A later valuation-labelled study and a later return study need distinct endpoints; neither can be inferred from relevance accuracy.

This update extends drafts #31 and #34. It does not change master, merge the paper execution stack, place an order or run a paid model. Paper2Agent/MCP, corrective memory, temporal masking, return attribution and a customer-facing briefing remain separate future work.

## 中文说明

这轮研究的重点是把几件事分别测清楚：新闻是否涉及这家公司、它是否带来新信息、它可能怎样影响估值，以及后续交易有没有价值。清华等团队的研究提醒我们，回测收益需要拆开看大盘和风格的贡献；厦大等团队的研究提醒我们，使用未来训练数据与实际成绩变化是两回事。

已完成的是新闻原文预检：检查实际文件、引用位置与记录时间，并生成尚未标注的清单。真实新闻数据、独立人工标签和模型比较尚未完成。公开金融基准里的合成目标案例不能直接当作我们的真实新闻成绩。
