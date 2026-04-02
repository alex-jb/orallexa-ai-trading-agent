# Orallexa: 多头与空头 AI 对辩的智能交易系统

GitHub: https://github.com/alex-jb/orallexa-ai-trading-agent

---

## 项目背景

大多数 AI 交易系统的思路是：数据输入 -> 模型预测 -> 输出信号。整个过程是黑盒，你只能得到一个买/卖结论，没有推理过程，没有反方意见。

Orallexa 采用了不同的方法：**让 AI 自己跟自己辩论**。

## 核心机制：对抗性辩论

每次分析会生成三个 LLM Agent：

- **Bull Agent（多头分析师）**：构建最强的做多论据
- **Bear Agent（空头分析师）**：系统性反驳多头观点，寻找风险
- **Judge Agent（裁判）**：综合双方论点，给出结构化决策

输出包含：决策方向、置信度、概率分布（上涨/震荡/下跌）、完整风控方案（入场价、止损、目标价、风险收益比、仓位大小）。

## 9 个 ML 模型

辩论不是空谈，底层有 9 个模型提供数据支撑：

| 模型 | 类型 | 作用 |
|------|------|------|
| Random Forest | 集成学习 | 基线信号 |
| XGBoost | 梯度提升 | 特征重要性 + 信号 |
| EMAformer | Transformer（AAAI 2026） | 时序模式识别 |
| MOIRAI-2 | 基础模型 | 零样本时序预测 |
| Chronos-2 | 基础模型 | 概率预测 |
| DDPM Diffusion | 扩散模型 | 分布感知预测 |
| PPO RL | 强化学习 | 学习交易策略 |
| GNN (GAT) | 图神经网络 | 跨股票信号传播 |
| Logistic Regression | 线性模型 | 概率校准基线 |

## 技术亮点

### GNN 跨股票信号传播

使用图注意力网络（GAT）建模 17 只相关股票之间的关系（同板块、供应链上下游、宏观 ETF）。当一只股票异动时，GNN 会将信号传播到关联节点。在板块轮动日效果尤其明显。

### LLM 策略进化

受 NVIDIA AVO 论文启发，LLM 不仅做分析，还能**生成新的交易策略**（以 Python 函数形式），自动回测并淘汰表现差的，保留优胜者继续迭代。类似遗传算法，但用 LLM 做变异算子。

### 双层 Claude 路由

- **Haiku**：处理快速任务（数据格式化、简单分类），约 $0.001/次
- **Sonnet**：处理深度推理（辩论、策略生成），约 $0.003/次

单只股票完整分析成本约 $0.003，每天跑 50 只股票不到 $0.15。

### 工程实现

- **前端**：Next.js 实时仪表盘，WebSocket 推送行情，支持中英双语
- **执行**：Alpaca 模拟交易，支持 bracket order（自动止损止盈）
- **测试**：113 个自动化测试，CI/CD 流水线
- **部署**：Docker 容器化，一键启动
- **交互**：Whisper 语音输入 + TTS 语音播报，支持免手操作
- **UI 风格**：Art Deco 装饰艺术风格，金色公牛吉祥物

## 技术栈

```
Python 3.11+ | Next.js 16 | Claude Sonnet/Haiku
scikit-learn | XGBoost | PyTorch
yfinance | Alpaca API | Docker
WebSocket | Whisper | TTS
```

## 体会

1. 对抗性辩论比单一模型共识效果更好。Bear Agent 经常能发现单次分析遗漏的风险点。
2. 基础模型（MOIRAI-2、Chronos-2）在金融时序上的零样本能力出人意料地好，但需要与传统模型对齐校准。
3. LLM 生成的策略偶尔有创造性的方法，但大部分是垃圾。进化循环的筛选压力很关键。

---

开源项目，MIT 协议。欢迎交流讨论，特别是对辩论机制的改进建议。

https://github.com/alex-jb/orallexa-ai-trading-agent
