# AI research continuation — October 5 evening, New York / October 6 UTC

## Decision

Prioritize a small, source-grounded comparison of **CLM-8B for company-news screening**. Study context management and recovery as separate research tracks. The first real-source seed remains unlabelled, so this update specifies experiments and checks output semantics; it does not establish model superiority, accuracy or trading returns.

Sources and source-code revisions were checked October 6 UTC, while it was still October 5 in New York. Publication dates below are the original sources' dates. See the [earlier October 5 note](AI_RESEARCH_UPDATE_2026-10-05.md) for the real-headline pilot and independent annotation workflow.

## Four findings

| Primary source | Verified finding and boundary | Orallexa adaptation |
| --- | --- | --- |
| **Contrastive-LM — [CLM-v0.1-8B author card](https://huggingface.co/Contrastive-LM/CLM-v0.1-8B), [code](https://github.com/Contrastive-LM/CLM)**; card undated, checked today. | The released model uses a frozen Qwen3-8B encoder and trained state/action heads to rank supplied choices. It exposes TypeSafe-style typed answers and can reuse candidate embeddings. The authors report up to 9× lower latency on their zero-shot tasks; coding-verifier results require fine-tuned heads. Candidate probabilities are relative to the supplied set. | Evaluate binary company relevance and a separate four-way event question. Measure actual encoder-plus-head latency and cold/warm caches on our inputs. Do not transfer speedups, calibration or coding benchmark results to financial news. |
| **University of Washington / Meta / MIT / Trillium — [Context Language Models](https://arxiv.org/abs/2609.37725), [author repo](https://github.com/facebookresearch/context-language-models)**; first submitted September 29, current paper text October 1. | The agent treats live context as an editable file and controls what to retain, revise or offload. The study reports task-specific quality/compute improvements in long research/coding workflows. The inspected repo declares CC BY-NC 4.0 and lists ContextBench as coming soon. This is a different meaning of “CLM” from Contrastive Language Models. | Inference: develop versioned working notes for Bull/Bear/Judge while keeping source archives, timestamps and prior records independently inspectable. Measure lost evidence, stale claims, context length and checking cost before changing the live pipeline. No code is imported or context harness run here. |
| **Princeton / NVIDIA / University of Maryland — [PivotOPD](https://research.nvidia.com/labs/lpr/pivotopd/)**; September 30 preprint. | The training method targets early consequential mistakes and subsequent recovery actions. Its preliminary symbolic ALFWorld analysis finds pivotal mistakes in 59% of failed rollouts; the reported gains cover simulated interaction, QA and software tasks. Production pivot detection is teacher-assisted. Code is marked coming soon. | Inference: first collect failed research traces and test recovery from the same saved state—wrong entity, wrong period, incomplete source or mistaken calculation. Correctness needs an external reference; an LLM calling its own earlier answer wrong is not sufficient. No distillation, PPO training or failure-recovery model is run. |
| **MIT and collaborators — [Ataraxos announcement](https://news.mit.edu/2026/game-playing-ai-stratego-new-champ-0930), [Nature paper](https://www.nature.com/articles/s41586-026-11036-y)**; MIT announcement September 30. | Self-play produces a blueprint strategy; decision-time planning refines actions using possible hidden states. The reported 15-win/1-loss/4-draw match concerns Stratego. Games provide specified rules and outcomes; financial-market payoffs and a valid simulator require separate evidence. | Inference: compare candidate decisions under explicit scenarios in a later bounded simulator. Do not treat Bull/Bear debate as self-play training or the game result as stock-selection evidence. This is a longer-term research idea, not an imported trading policy. |

The Context Language Models code revision checked is `18dc11115f50f261233c5bba7937834491e307e8`. Licenses and released materials differ across these projects; read-and-analyze status does not establish that a full method has been reproduced.

## Experiment priorities

These are **my planning scores**, not paper or model benchmark scores. Each dimension is 0–5: project fit, inspectable material/readiness, near-term feasibility and potential product use. Product use is a hypothesis, not measured demand.

| Direction | Fit | Readiness | Feasibility | Product hypothesis | Total /20 |
| --- | ---: | ---: | ---: | ---: | ---: |
| CLM-8B company-news screening | 5 | 4 | 3 | 4 | **16** |
| Versioned agent working memory | 4 | 3 | 3 | 3 | **13** |
| Research failure diagnosis/recovery | 4 | 2 | 2 | 3 | **11** |
| Imperfect-information planning | 3 | 2 | 1 | 3 | **9** |

CLM ranks first because weights/code and a bounded existing task are available. Independent labels and a pinned inference setup are still missing. Context management fits repeated research but needs a separate prototype and review of available code terms. PivotOPD training needs trajectories/teacher signals and released implementation. Financial planning needs a defensible environment before its scores mean anything.

## Concrete work completed

Read the pinned Contrastive-LM source at `d5f9ef0fd9bde185df0ceaad4f4ecc6cfe8c34f6` and execute only its pure schema functions with invented numerical inputs. Seven assertions pass, with no encoder/head weights loaded and no inference call. The [JSON receipt](examples/CLM_SCHEMA_PROBE_2026-10-06.json) includes source revision and file hash.

The probe verifies three different outputs: binary `Noul.noul`, a four-option `Choice` distribution/score gap and an ordered `Score` mean. It also demonstrates candidate-set sensitivity using fixed synthetic logits. These examples are not labelled real news or observed model predictions. Source inspection separately finds default 2,048-token truncation and cache-miss token accounting; neither behavior has been benchmarked here.

The [CLM news study protocol](CLM_NEWS_SHADOW_PROTOCOL.md) now specifies task/field mapping, prospective independent labels, the primary endpoint, fixed candidates/question rendering, checkpoint identity, input limits, complete-cohort failure accounting and cold/warm latency/cost measurement. It does not install a model or create a runner. Existing draft #34 and its eight still-unreviewed real cases are unchanged by this turn.

## Product hypothesis and research boundary

A concrete hypothesis is a financial briefing pipeline with a bounded classifier selecting items for deeper evidence-linked analysis. Compare false alerts, missed company-specific items, correction time and total operating cost against the existing workflow. A locally hosted ranker may be useful when actions repeat, but that needs an actual workload and resource bill. No customer demand, savings or deployment advantage is established here.

Keep the three measurements separate: whether an article concerns a company, whether the resulting research answer is fully supported, and whether a subsequent trading decision adds value. This update extends draft [#31](https://github.com/alex-jb/orallexa-ai-trading-agent/pull/31). It changes documentation and a synthetic probe receipt only; master, providers and broker routes remain unchanged.

## 中文说明

这轮最直接的候选是 CLM-8B：它能在明确给出的候选项之间打分，适合先试新闻分类和公司相关性。代码里有两个接入细节：默认会截断长输入；`Choice.confidence` 是选项分差，需要和二元相关性概率分别处理。

另外三条研究方向是：代理自己整理工作笔记、从早期错误之后恢复，以及在隐藏信息下比较不同决策。它们都有启发，但各自需要实验。已完成的是七项纯格式/数学检查和具体评估设计，真实新闻标签与模型实测仍未产生。
