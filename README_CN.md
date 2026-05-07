<div align="center">

<img src="assets/logo.svg" alt="Orallexa" width="420">

<br>

### AI 交易操作系统

**9 个 ML 模型，对抗辩论，一键执行。**<br>
别猜市场。让 AI 先吵一架。

<br>

[![Stars](https://img.shields.io/github/stars/alex-jb/orallexa-ai-trading-agent?style=for-the-badge&logo=github&color=D4AF37&logoColor=white)](https://github.com/alex-jb/orallexa-ai-trading-agent)
[![Python](https://img.shields.io/badge/Python-3.11+-1A1A2E?style=for-the-badge&logo=python&logoColor=D4AF37)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js_16-1A1A2E?style=for-the-badge&logo=next.js&logoColor=D4AF37)](https://nextjs.org)
[![Claude](https://img.shields.io/badge/Claude_Sonnet_4.6-1A1A2E?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSI+PGNpcmNsZSBjeD0iMTIiIGN5PSIxMiIgcj0iMTAiIGZpbGw9IiNEMkE5NzAiLz48L3N2Zz4=&logoColor=D4AF37)](https://anthropic.com)
[![CI](https://img.shields.io/github/actions/workflow/status/alex-jb/orallexa-ai-trading-agent/ci.yml?style=for-the-badge&logo=githubactions&logoColor=white&label=CI%20—%20Tests%20%26%20Build&color=22c55e)](https://github.com/alex-jb/orallexa-ai-trading-agent/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/990%2B_测试-全部通过-22c55e?style=for-the-badge)](tests/)
[![Issues](https://img.shields.io/badge/未关闭议题-0-22c55e?style=for-the-badge)](https://github.com/alex-jb/orallexa-ai-trading-agent/issues)
[![License](https://img.shields.io/badge/MIT-1A1A2E?style=for-the-badge)](LICENSE)

<br>

[**在线演示**](https://orallexa-ui.vercel.app) · [**演示文稿**](https://alex-jb.github.io/orallexa-ai-trading-agent/presentation.html) · [**评估报告**](docs/evaluation_report.md) · [**English**](README.md)

<br>

<img src="assets/showcase_demo.png" alt="Market Scan → AI Analysis → Decision" width="720">

</div>

<br>

## 这个项目有什么不同

大多数 AI 交易项目：把数据喂给模型，得到信号，结束。

Orallexa 跑一条**多智能体情报管道**。4 个不同风险偏好的 AI 分析师辩论交易。20 个 Agent 群体模拟市场反应。5 个独立信号源投票。偏差追踪器纠正系统自己的错误。然后执行。

```
市场数据 → 9 个 ML 模型 → 4 角色面板 + 多空辩论
    → 5 源信号融合 → 裁判判决 → 假设场景推演
    → 风控计划 → 模拟执行 → 实时仪表盘 → 社交内容
```

每个阶段自动化。每个阶段可观测。系统从自身学习。

---

## 立即体验

**[打开在线演示](https://orallexa-ui.vercel.app)** — 演示模式，无需 API Key。点击 **NVDA**、**TSLA** 或 **QQQ** 查看完整分析。

或本地运行：

```bash
git clone https://github.com/alex-jb/orallexa-ai-trading-agent.git
cd orallexa-ai-trading-agent
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=your_key" > .env

# 终端 1：API 服务
python api_server.py

# 终端 2：仪表盘
cd orallexa-ui && npm install && npm run dev
```

Docker 一键启动：`docker compose up --build`

---

## Walk-Forward 评估（样本外）

<!-- EVAL_TABLE_START -->
| 策略 | 标的 | 样本外 Sharpe | 评级 | p 值 |
|------|------|-------------|------|------|
| rsi_reversal | INTC | **1.41** | PASS | 0.002 |
| dual_thrust | NVDA | **0.96** | PASS | 0.001 |
| alpha_combo | NVDA | **0.92** | PASS | 0.016 |
| macd_crossover | NVDA | **0.91** | PASS | 0.003 |
| ensemble_vote | NVDA | **0.90** | PASS | 0.001 |
| trend_momentum | NVDA | **0.74** | PASS | 0.005 |
| double_ma | GOOG | **0.64** | PASS | 0.049 |
| ensemble_vote | META | **0.31** | MARGINAL | 0.324 |
<!-- EVAL_TABLE_END -->

> 90 个策略-标的组合，10 个标的，9 个策略（含组合投票和 regime 感知集成）。1 个 STRONG PASS，7 个 PASS，33 个 MARGINAL。[完整报告 →](docs/evaluation_report.md)

---

## 架构

<p align="center">
  <img src="assets/architecture.svg" alt="系统架构" width="100%">
</p>

<table>
<tr>
<td width="50%">

### 智能层

| 组件 | 详情 |
|------|------|
| **9 个 ML 模型** | RF, XGB, EMAformer, MOIRAI-2, Chronos-2, DDPM, PPO RL, GNN, LR |
| **4 角色多视角面板** | 保守分析师 / 激进交易员 / 宏观策略师 / 量化研究员，带持久化记忆 |
| **对抗辩论** | 多空裁判制，Claude Sonnet + Haiku 双层路由 |
| **5 源信号融合** | 技术面 + ML 集成 + 新闻情绪 + 期权异动 + 机构数据 |
| **假设场景推演** | Claude 模拟假设事件对组合的影响 |
| **20 Agent 群体模拟** | 规则驱动的蒙特卡洛收敛模拟 |
| **偏差自修正** | 追踪预测准确率，自动调整置信度 |
| **策略进化** | LLM 生成 Python 策略 → 沙盒测试 → 进化赢家 |
| **每日情报** | 50+ 标的扫描，板块轮动，成交量异动，AI 晨间简报 |

</td>
<td width="50%">

### 执行层

| 组件 | 详情 |
|------|------|
| **模拟交易** | Alpaca 括号单，自动止损/止盈 |
| **实时推送** | WebSocket 每 5 秒更新 + 信号变化警报 |
| **仪表盘** | Next.js 16，Art Deco 主题，中英双语 |
| **桌面教练** | 像素牛宠物，语音输入 (Whisper) + TTS |

</td>
</tr>
</table>

---

## 示例输出

NVDA 单次分析的结果：

```
┌─────────────────────────────────────────────────────────────────┐
│  决策: BUY                        置信度: 68%                    │
│  风险: MEDIUM                     信号: 72/100                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  多方论据 (BULL):                                                │
│  • 价格位于 MA20 > MA50 上方 — 完全看多排列                       │
│  • RSI 62 — 强劲动量，尚未超买                                    │
│  • 成交量 1.8 倍均值 — 可能有机构参与                              │
│                                                                 │
│  空方论据 (BEAR):                                                │
│  • ADX 32 但下降 — 趋势可能衰竭                                   │
│  • 布林带 %B 0.85 — 接近上轨，过度延伸                            │
│  • 12 天后财报 — 事件后波动率压缩                                  │
│                                                                 │
│  裁判判决 (JUDGE):                                               │
│  "多方更强。建议买入，止损设在 MA20。"                              │
│                                                                 │
│  概率: 上涨 58% | 震荡 24% | 下跌 18%                            │
│  风控计划:                                                       │
│  入场: $132.50 | 止损: $128.40 | 目标: $141.00 | 风险收益比 2.1:1 │
└─────────────────────────────────────────────────────────────────┘
```

不只是一个数字。结构化论证 + 透明推理 + 可执行风控计划。

---

## 9 个 ML 模型 — 评分排名

每次分析运行所有可用模型。ML 记分板并排展示 Sharpe、收益、胜率。

| 模型 | 类型 | 功能 |
|------|------|------|
| Random Forest | 分类 | 28 个技术特征 → 5 日方向 |
| XGBoost | 梯度提升 | 相同特征，不同优化 |
| Logistic Regression | 线性 | 正则化基准线 |
| **EMAformer** | Transformer | iTransformer + Embedding Armor (AAAI 2026) |
| **MOIRAI-2** | 基础模型 | Salesforce 零样本时序预测 |
| **Chronos-2** | 基础模型 | Amazon T5 概率预测 |
| **DDPM Diffusion** | 生成模型 | 50 条价格路径 → VaR 和置信区间 |
| **PPO RL Agent** | 强化学习 | Gymnasium 环境，Sharpe 奖励 |
| **GNN (GAT)** | 图网络 | 17 只股票关系图，跨股票信号传播 |

所有模型在 CPU 上运行。

---

## 仪表盘

<p align="center">
  <img src="assets/screenshots/dashboard_preview.png" alt="仪表盘" width="90%">
</p>

**信号视图** — 决策卡片、概率条、多空辩论、ML 记分板、风控计划。<br>
**情报视图** — 晨间简报、涨跌榜、板块热力图、成交量异动、AI 推荐、社交推文串。

Art Deco 主题。Polymarket 概率展示。移动端适配。中英双语。

---

## 桌面 AI 教练

一只浮动的像素牛，住在你的桌面上：

- **语音对话** — 按住 K 说话，Whisper 转写，Claude 回复
- **图表分析** — Ctrl+Shift+S 截图任意图表，Claude Vision 分析
- **决策卡片** — 入场价、止损、目标、风险收益比覆盖在屏幕上
- **市场感知头像** — 牛的颜色随市场状态变化

---

## 成本优化 AI

不是每个任务都需要最贵的模型：

| 任务 | 模型 | 成本 |
|------|------|------|
| 多空论证 | Haiku 4.5 | ~$0.001 |
| 4 角色面板 | Haiku 4.5 | ~$0.002 |
| 裁判判决 | Sonnet 4.6 | ~$0.005 |
| 深度报告 | Sonnet 4.6 | ~$0.005 |
| 假设场景 | Sonnet 4.6 | ~$0.005 |
| 信号融合 + 群体模拟 | 本地（无 LLM） | $0 |
| 偏差追踪 | 本地（无 LLM） | $0 |

**单次完整分析：~$0.005。** 每日情报报告：~$0.05。

`ORALLEXA_MULTIMODAL_SAMPLE=0.0..1.0` 控制视觉增强辩论的采样率。默认 `0` 关闭(行为完全等同纯文本)。设为 `0.2` 时,~20% 的深度分析调用会让 Quant Researcher 同时跑文本和 K 线图;每次调用的差异会被存到 `decision_log.extra.multimodal_diff`,夜间 **Multimodal Lift — Vision vs Text Eval** workflow 据此聚合出 ship/reject 结论。被采样的调用 ~5× 成本,推荐生产值 `0.1`–`0.2`。

---

## 为什么选这个架构

| 痛点 | 传统方案 | Orallexa |
|------|---------|----------|
| 孤立信号 | 一个模型，一个预测 | 5 源融合：技术面 + ML + 新闻 + 期权 + 机构 |
| 没有推理 | "买入 73%" — 为什么？ | 4 个分析师辩论，Bull/Bear 对抗，Judge 用证据裁决 |
| 不会自我纠正 | 重复同样的错误 | 偏差追踪器检测过度自信，自动调整未来预测 |
| 静态分析 | 无法测试假设 | "如果美联储加息 50bp？" — 场景推演 + 群体模拟 |
| AI 太贵 | 每次都调 GPT-4 | 80% 用 Haiku，Sonnet 只在推理处用 |
| 手动流程 | Notebook → 看结果 → 决策 → 执行 | 自动化：信号 → 辩论 → 风控 → 模拟下单 |
| 没有上下文 | 每只股票独立分析 | GNN 在 17 只相关股票间传播信号 |
| 不能分享 | 截图你的终端 | 每个板块都有"复制到 X"按钮 |

---

## Orallexa vs ai-hedge-fund

受 [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) 启发。我们共享多 Agent 理念，但走了不同路线：

| 功能 | ai-hedge-fund | Orallexa |
|------|:------------:|:--------:|
| ML 模型 | 0（纯 LLM） | 9 个（RF, XGB, EMAformer, MOIRAI-2, Chronos-2, DDPM, PPO RL, GNN, LR） |
| 模型排名 | 无 | 按 Sharpe 自动排名 |
| LLM 供应商 | OpenAI, Groq, Anthropic, DeepSeek | Claude Sonnet + Haiku（双层路由） |
| 单次分析成本 | ~$0.03+（单层） | ~$0.003（80% Haiku，20% Sonnet） |
| 实时仪表盘 | 基础 Web UI | Next.js 16 + WebSocket，Art Deco 主题 |
| 模拟交易 | 无执行 | Alpaca 括号单（止损 + 止盈） |
| 每日情报 | 无 | 50+ 标的扫描，板块轮动，AI 晨间简报 |
| 桌面助手 | 无 | 像素牛 + 语音（Whisper + TTS） |
| 社交内容 | 无 | 一键"复制到 X" |
| Walk-Forward 评估 | 无 | 70 个策略-标的组合，样本外 Sharpe |
| 测试 | 有限 | 277 个自动化（139 前端 + 138 后端） |
| 双语 | 无 | 中英双语 |

---

## 技术栈

<table>
<tr><td><b>前端</b></td><td>Next.js 16, React 19, Tailwind CSS 4, PWA</td></tr>
<tr><td><b>后端</b></td><td>FastAPI, Python 3.11, WebSocket</td></tr>
<tr><td><b>AI</b></td><td>Claude Sonnet 4.6 + Haiku 4.5（双层路由）</td></tr>
<tr><td><b>ML</b></td><td>scikit-learn, XGBoost, PyTorch (EMAformer, DDPM, GAT, PPO)</td></tr>
<tr><td><b>数据</b></td><td>yfinance（实时 + 历史）</td></tr>
<tr><td><b>NLP</b></td><td>FinBERT, VADER, TextBlob</td></tr>
<tr><td><b>交易</b></td><td>Alpaca 模拟交易（括号单）</td></tr>
<tr><td><b>编排</b></td><td>LangGraph（有状态辩论管道）</td></tr>
<tr><td><b>部署</b></td><td>Docker, GitHub Actions CI/CD, Vercel</td></tr>
</table>

---

## 测试

277 个自动化测试。0 个失败。每次推送 CI。

```bash
python -m pytest tests/ -v           # 后端（138 个测试）
cd orallexa-ui && npm test           # 前端（139 个测试）
```

<details>
<summary><b>完整测试分布</b></summary>

| 套件 | 数量 | 覆盖范围 |
|------|------|---------|
| 引擎集成 | 34 | 技术指标、策略、回测、大脑路由 |
| ML 回归 | 13 | 所有 9 个模型 — 确保升级不降质 |
| API E2E | 19 | 所有端点，FastAPI TestClient |
| 单元测试 | 47 | DecisionOutput, BehaviorMemory, 风控, 剥头皮 |
| 类型与工具 | 28 | 显示函数、颜色映射、i18n |
| 组件测试 | 67 | DecisionCard, Breaking, MarketStrip, ML Scoreboard, Watchlist, DailyIntel |
| Mock 数据 | 31 | 所有 mock 生成器 |

</details>

---

## API

<details>
<summary><b>接口列表</b></summary>

| 方法 | 端点 | 描述 |
|------|------|------|
| `POST` | `/api/analyze` | 快速信号分析（剥头皮/日内/波段） |
| `POST` | `/api/deep-analysis` | 多智能体深度分析 + 辩论 |
| `POST` | `/api/chart-analysis` | 截图图表分析（Claude Vision） |
| `POST` | `/api/watchlist-scan` | 并行多标的扫描 |
| `GET` | `/api/daily-intel` | 每日市场情报（缓存） |
| `GET` | `/api/news/{ticker}` | 新闻 + 情绪评分 |
| `GET` | `/api/profile` | 交易者行为画像 |
| `GET` | `/api/journal` | 决策执行日志 |
| `POST` | `/api/evolve-strategies` | LLM 策略进化 |
| `GET` | `/api/alpaca/account` | 模拟交易账户 |
| `POST` | `/api/alpaca/execute` | 执行信号为模拟订单 |
| `WS` | `/ws/live` | 实时价格 + 信号流 |

</details>

---

## 项目结构

<details>
<summary><b>目录布局</b></summary>

```
orallexa/
├── api_server.py               # FastAPI + WebSocket 服务
├── docker-compose.yml          # 一键部署
│
├── engine/                     # 交易引擎（9 个模型）
│   ├── multi_agent_analysis.py # LangGraph 辩论管道
│   ├── ml_signal.py            # 模型对比框架
│   ├── strategies.py           # 7 个规则策略
│   ├── emaformer.py            # EMAformer Transformer
│   ├── diffusion_signal.py     # DDPM 概率预测
│   ├── gnn_signal.py           # 图注意力网络
│   ├── rl_agent.py             # PPO 强化学习
│   ├── strategy_evolver.py     # LLM 策略进化
│   └── sentiment.py            # FinBERT / VADER
│
├── llm/                        # AI 推理
│   ├── claude_client.py        # 双层模型路由
│   ├── debate.py               # 多空辩论
│   └── debate_graph.py         # LangGraph 管道
│
├── orallexa-ui/                # 仪表盘（Next.js 16）
├── desktop_agent/              # 桌面 AI 教练
├── bot/                        # 执行层（Alpaca）
├── tests/                      # 138 个后端测试
└── .github/workflows/          # CI/CD
```

</details>

---

## 致谢

[Anthropic Claude](https://anthropic.com) · [yfinance](https://github.com/ranaroussi/yfinance) · [Polymarket](https://polymarket.com) · [Alpaca](https://alpaca.markets)

---

<div align="center">

**MIT License** — 详见 [LICENSE](LICENSE)

> **免责声明**: 研究和教育项目，不构成投资建议。

<br>

**用信念构建，不靠炒作。**

</div>
