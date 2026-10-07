# Kronos daily forecast context and votes

The daily Kronos voter now uses exchange sessions, explicit dates and an explicit
forecasting context. It no longer represents a price-path heuristic as realized
Sharpe or backtest return. These are interface corrections, not evidence of a
profitable forecasting model.

## Resulting behavior

| Boundary | Behavior |
| --- | --- |
| Future daily dates | Use `exchange_calendars` with `XNYS` by default, including exchange holidays. A shortened session remains a trading day. |
| Historical dates | Prefer `timestamps` over the index. Reject numeric dates, missing or malformed dates, duplicate daily labels, unordered labels and non-session dates. Never substitute today's date for an invalid history. |
| Input values | Reject nonfinite or nonpositive OHLC and negative volume or amount before loading checkpoints. |
| Forecast context | Both the normal analysis and SSE analysis pass their full prepared history as `forecast_df`; supervised training and evaluation still use their separate partitions. Omitting that context skips Kronos. |
| Forecast vote | Carry `signal_type=price_forecast` and a bounded `directional_score`. Staying at the current close produces a neutral vote. Legacy synthetic Kronos Sharpe entries are ignored. |
| Evidence | Keep expected price change, horizon, model size, last input session, target sessions and calendar version under `forecast`; keep the legacy `metrics` container empty. The analyst report labels this forecast separately. |

The directional score remains a heuristic: a predicted 5% endpoint change maps
to 100, and -5% maps to -100, with clipping. Fusion gives it the same maximum
per-model scale as the other voters. This score is neither a probability nor a
calibrated confidence value. Path monotonicity is descriptive and does not boost
the vote. Invalid votes are omitted; a valid neutral vote counts as one neutral
model, with zero directional agreement when it is the only voter.

## Daily input contract

Use one completed daily bar per provider-local session label. Timezone-aware
daily labels retain their written local date when normalized; this interface is
not an intraday UTC timestamp converter. Other markets need an explicitly chosen
calendar when constructing `KronosSignal`; the existing analysis entry points
use the US-equity default. Duplicate normalized dates reject intraday bars.

The calendar checks dates, not the truth or availability of market data. The
caller must exclude incomplete bars and any information unavailable at its
forecast cutoff. Passing the latest prepared frame fixes the old train-partition
lag but does not establish historical point-in-time correctness for the entire
pipeline. `trade_date` remains a report parameter, not a newly enforced data
availability cutoff.

The native Kronos return is marked `point_path`. This change does not provide
sample paths, calibrated prediction intervals or volatility forecasts. The
author's predictor averages repeated samples internally; retaining uncertainty
requires a separate adapter and chronological validation.

## Offline verification

With the project requirements installed:

```bash
python -m pytest -q tests/test_kronos_signal.py tests/test_kronos_boundaries.py
python -m pytest -q tests/test_mirofish.py -k score_ml
```

The first pair covers calendar dates independently specified from the NYSE
schedule, explicit timestamp precedence, invalid inputs, neutral and conflicting
path directions, vote boundaries and current context handoff. The existing
consensus tests check that the other model scoring remains intact.

The SSE regression executes the real generator through its third progress
event with offline providers, then closes it before later model stages. It
checks the data-to-ML handoff, not HTTP authentication or the complete stream.
The main-pipeline regression uses offline model, news, debate, panel and risk
providers. No network data, model checkpoint, paid inference or broker is used.

Eleven core regressions were also run against the original master commit
`794a2ec0ce0b1271b468814eee47c2cd4edde147`: all eleven detect the original date,
timestamp, synthetic metric or stale-context behavior. In the exchange-session
fixture ending 2026-10-02, the old pipeline supplies 2026-08-20 as its last
Kronos input; the corrected entry points supply 2026-10-02. This fixture differs
from the earlier weekday-only reproduction.

## 本轮研究对下一步升级的启发

Google Cloud AI Research 与弗吉尼亚大学的 [SEER 论文](https://arxiv.org/html/2610.04109v1)
于 2026 年 10 月 2 日首次提交。它用已经揭晓的预测错误更新检索记忆与文字知识；评测时冻结这两类记忆，并过滤截止日期之后的事件。这个设计适合研究 Orallexa 怎样使用新闻，但不能仅靠截止日期过滤排除基础模型预训练中的未来信息。

股票部分的主表报告 SEER 准确率 38.25%，事件 RAG 为 36.92%，差 1.33 个百分点；这是论文的三分类协议，不是交易胜率。选择性预测另允许每天从 50 只股票中选择至多 6 只，也可以全部弃权。比较时必须同时记录覆盖率、共同选择的样本和固定股票池的基线。

作者[公开仓库](https://github.com/BennyTMT/SEER/tree/609eface72faafd5409ae4f2f075befa5ba28cbe)
在该提交包含 README、图和三份示例文本，没有完整执行或评测代码。2026-03-25 的股票示例选中 MU 和 AMD 并都预测下跌，两者都对；同一选择上的“始终预测下跌”也都对。这个单日示例不能独立证明记忆带来增益。其完整 50 股参考标签为 31 个下跌、11 个中性和 8 个上涨，属于该示例的描述性复算，不是整套测试结果。

下一轮可先做三个按时间冻结的离线条件：现有价格输入、价格加已核查新闻、价格加新闻及固定记忆。保留同一股票池、时间、输出期限与基础模型；测试期间不更新记忆。报告预测误差、选择覆盖率、弃权情况和完整运行成本，再决定是否接入盘前方案。KiT 的权重划分核查和 MIT 的概率自洽检查仍是独立工作，不由本次接口修复替代。

## Primary sources

- [NYSE holidays and trading hours](https://www.nyse.com/trade/hours-calendars)
- [Exchange calendar implementation and documented sessions](https://github.com/gerrymanoim/exchange_calendars)
- [Kronos author implementation](https://github.com/shiyu-coder/Kronos/blob/67b630e67f6a18c9e9be918d9b4337c960db1e9a/model/kronos.py)
- [SEER published stock example](https://github.com/BennyTMT/SEER/blob/609eface72faafd5409ae4f2f075befa5ba28cbe/assets/cases/Stock-Basket50-2026-03-25.txt)

No new-model performance or trading return has been measured in this upgrade.
