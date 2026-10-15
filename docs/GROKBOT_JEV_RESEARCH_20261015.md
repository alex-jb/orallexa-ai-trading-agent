# GROKBOT + JEV 视频核查与 Orallexa 开发记录

研究日期：2026-10-15。结论：我们可以在 Orallexa 上实现同类分析面板、角色状态和决策流程；当前没有证据支持复制视频中的盈利效果。本轮先修行情与情绪数据链，没有接入新的交易服务。

## 原视频实际展示什么

用户短链 `https://v.douyin.com/5yPvgYxIJ50/` 落地为 [Jackey 的原视频](https://www.douyin.com/video/7696400091225132351)。通过公开浏览器播放核查，未登录。页面当前显示 2026-10-13 23:03、约24秒，和分享文字中的08/08不同；不推定原始上传日期。页面同时显示作者声明内容由AI生成。

画面有 GROKBOT + JEV 标题、FOMO 标志，以及 CHIEF、SCAN、VET、SOCIAL、SIZE、FILLS、RISK、CRAWLER 八个面板；还包括蜘蛛状动态关系图、角色化办公室、K线、余额曲线与日志。面板时钟和余额跳变，属于剪辑或加速展示，不能据此计算可实现收益。没有看见模型版本、可复现回测、交易所流水、完整账户账本或源代码地址。评论中的收益和与幻方的关联均未核实。画面没有域名，不能仅靠FOMO标志确定平台身份。

这是对可见界面的观察，不证明每个动画节点对应真实Agent调用。

## 我们能做哪些部分

| 能力 | Orallexa 当前代码与边界 | 本轮处理 |
| --- | --- | --- |
| 行情K线和技术指标 | 原 PriceChart 无条件随机生成OHLCV，连上后端也一样；已有 lightweight-charts、MA、BB、RSI 绘制 | 删除随机路径，新增只读历史行情接口，显示来源、粒度、未复权口径和最后bar起始时间 |
| 新闻/社交分析 | 已有新闻与社交获取代码；深度分析只导入情绪工具却不调用，误给零分 | 调用共享评分链，保留来源、发布时间和实际backend；失败继续降级，不冒充中性 |
| 多角色分析和风险检查 | `engine/multi_agent_analysis.py` 已有市场、新闻、ML、多空辩论和风险流程 | 保留架构；本轮没有验证模型优劣或交易收益 |
| FOMO式情绪、期权活动和市场广度 | 晨报使用自定义代理、模型生成情景和截断股票样本粗估，非全市场实数 | 修改中英文标签，取消“52周新高/新低”等不符合计算的名称；未重建完整数据源 |
| 蜘蛛连线、办公室和角色动画 | 属于可开发的前端表现；现有真实运行事件可用作状态输入 | 尚未实现；不先画随机动画冒充实际推理过程 |
| 全天持续运行、账户盈亏和成交 | 需要任务运行环境、数据权限、独立账本和经过验证的执行层 | 本轮未启动持续任务、未连接账户、未发订单 |

## 可以借鉴的开源，不混称原视频源码

1. [Bodila51/grok-bot-jev](https://github.com/Bodila51/grok-bot-jev)：MIT，提供 Jev 路由、缓存复用、停止重试、限额研究与日志参考。它不是 Grok Bot 基座。实际查看其 `media/jev-grok-bot-dashboard.png`，内容是机票检索与503重试，和原视频FOMO看板不同，不能说已经找到视频原项目。
2. [TradingAgents](https://github.com/TauricResearch/TradingAgents)：Apache-2.0。核查快照 `1394a3f72aa4393e1a98f51b382434c4b4c2d972` 的 [post_screen.py](https://github.com/TauricResearch/TradingAgents/blob/1394a3f72aa4393e1a98f51b382434c4b4c2d972/tradingagents/agents/post_screen.py)，已支持可选Jev筛相关新闻/社交立场，失败时保留原文并标未筛选。适合借来源、失败与不确定状态的设计；近期帖子不自动构成历史时点完备的数据。
3. [TypeSafe Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python)及[现有模型适配器](https://github.com/typesafe-ai/system-one-adapter-python)：MIT接口代码，可用于同输入比较。SDK公开不等于Jev模型权重公开。

[Grok Bot 官方说明](https://x.ai/news/introducing-grok-bot)介绍持续任务、云电脑与多Bot协作；本轮未找到官方完整Bot自托管源码。[Jev 官方说明](https://docs.typesafe.ai/introduction)定位为针对state回答窄范围结构化问题，不负责凭空获取行情或保证交易效果。它的回答置信度不能解释为盈利概率。

没有将第三方复刻教程或相似蜘蛛动画当作原版源码，也没有安装任何视频推荐的交易工具。本轮没有新增Jev依赖或读取API密钥；当前模型和确定代码足以先完成数据链修复。

## 具体开发契约

`GET /api/market-history/{ticker}?period=1mo&interval=1h`

仅开放五组周期：1d/5m、5d/15m、1mo/1h、3mo/1d、1y/1d。上游采用 yfinance，明确 `auto_adjust=False`，不混入现有复权日线缓存。日线保留交易所本地日期，日内使用UTC秒；`as_of`表示最后bar起始时间，不是最新成交或已经收盘的保证。保留提供方已开始但尚未收盘的bar并显示提示。非法OHLCV、未来bar和重复时间被清理。

空数据返回200空数组；提供方失败、超时或DEMO模式返回明确503，绝不补造K线。前端检查响应身份与结构；切换股票或周期会取消旧请求、清空旧图并忽略迟到响应；有超时、重试和资源清理。

新闻评分实际调用现有 FinBERT → VADER → TextBlob → keywords 路径。修复FinBERT运行失败且VADER缺失时被写成中性的分支；记录真正使用的backend。关键词评分仍是启发式，不是金融预测准确率或校准概率。

## 验证及未完成项

- 后端相关离线回归：`tests/test_market_chart.py`、`tests/test_news_analyst_scoring.py`、`tests/test_sentiment.py` 合计 **79 passed**。提供方和模型均使用离线替身；没有加载FinBERT/Kronos权重。
- UI全套：**271 passed**；其中行情组件22项、响应边界21项。检查原OHLCV进入绘图、五组周期、来源、失败不补数据、迟到响应、取消、超时、重试和卸载清理。
- TypeScript、修改文件ESLint、生产构建及Python编译通过。
- 同进程真实HTTP烟测：健康检查200；DEMO行情503；非法周期422；Next服务返回HTML 200。这不等于浏览器渲染或真实行情全链路通过。
- 对Yahoo只进行一次实际行情尝试，遭遇429限流并得到明确不可用结果；没有更换路径规避限流。真实网络成功取数仍待验证。
- 云浏览器不能连接本地测试端口，浏览器视觉和交互验收未完成。不能把单元测试或构建通过写成已上线可用。

此前[预测修复PR #42](https://github.com/alex-jb/orallexa-ai-trading-agent/pull/42)仍为open、draft、未合并；本轮从同一master建立独立分支，没有合并、部署或替换线上版本。PR42解决交易日、预测上下文和投票口径，本轮解决展示行情与新闻评分，二者都不证明交易表现。

## 后续顺序

先用许可清楚、额度稳定的行情来源完成网络及浏览器验收，再把真实分析阶段映射为扫描、分析、辩论、风险复核等可视状态。只有运行事件发生时才更新节点；缺数据和失败保留为单独状态。随后按同一历史时点、相同信息与预算比较现有模型、简单规则和可选Jev。评价分类错误、缺失率、延迟与成本，再单独做含手续费/滑点的前向模拟；不从视频余额曲线推出策略有效。
