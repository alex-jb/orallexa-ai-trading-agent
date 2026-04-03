# 更新日志

Orallexa AI 交易操作系统的所有重要升级记录。

---

## [2026-04-03] — 质量、测试、CI/CD、性能 & 部署

### 代码质量
- **Lint 零警告** — 修复全部 7 个 ESLint 警告：未使用导入、`<img>` → `next/image`、三元表达式、exhaustive-deps
- **React hooks 修复** — signal-toast 中 `useState` → `useRef`，offline 页面用 `useSyncExternalStore`，补齐 `useCallback` 依赖
- **ErrorBoundary** — 全局错误边界，Art Deco 风格错误页面 + 重新加载按钮

### 测试 — 230 前端 + 14 E2E + ~180 后端 = 424 总计
- **新增单元测试** — price-chart (11)、signal-toast (12)、service-worker-registrar (8)
- **覆盖率扩展** — atoms、signal-toast 超时行为、SW registrar 授权路径
- **覆盖率 73% → 86%** — 安装 `@vitest/coverage-v8`
- **Playwright E2E** — 14 个测试：页面加载、输入、策略/时间按钮、语言切换、响应式、离线页面

### CI/CD 管道
- **ESLint 加入 CI** — build-ui job 中增加 `npm run lint`
- **E2E job** — GitHub Actions 中 Playwright Chromium，失败时上传截图
- **CI badge** — 添加到 README

### 性能优化
- **懒加载重组件** — `PriceChart` 和 `DailyIntelView` 动态导入 `ssr: false`
- **Lighthouse 审计** — 无障碍 96、最佳实践 96、SEO 100

### 后端 API 修复
- **Backtest 端点** — 修复 `MarketDataSkill` 构造函数、70/30 训练/测试分割、结果解析

### 部署
- **Vercel 生产环境** — 部署到 [orallexa-ui.vercel.app](https://orallexa-ui.vercel.app)
- **.env.example** — 前端环境变量模板
- **.gitignore** — Playwright 产物

---

## [2026-04-02] — 设计系统、组件架构 & 全覆盖测试

### 设计系统 & 品牌
- **DESIGN.md** — 完整 Art Deco 设计规范: 4字体系统 (Poiret One / Josefin Sans / Lato / DM Mono)、金色调色板、组件模式、间距、动画、无障碍
- **像素牛吉祥物** — NFT风格像素金牛 (5色变体 + 26帧精灵动画)
- **Art Deco 头像重新设计** — 几何金牛品牌标志 + 金色钻石装饰
- **聊天弹窗重设计** — Welcome问候、像素装饰、新布局
- **中国市场颜色** — 红涨绿跌 (符合中国市场习惯)
- **Logo重新生成** — Art Deco 金色风格 PNG
- **桌面助手字体** — Josefin Sans + Lato + DM Mono TTF 与 Web 统一

### Next.js 组件架构 (page.tsx 1574→751行，减少52%)
- **types.ts** (88行) — 所有接口 + 工具函数
- **atoms.tsx** (148行) — DecoFan, GoldRule, Heading, Mod, Row, Toggle, BullIcon, BrandMark, CopyBtn
- **decision-card.tsx** (210行) — DecisionCard + ProbBar + BullBearPanel + InvestmentPlanCard
- **daily-intel.tsx** (168行) — DailyIntelView 全部板块
- **watchlist.tsx** (64行) — WatchlistGrid
- **breaking.tsx** (65行) — BreakingBanner (中英双语解释)
- **market-strip.tsx** (46行) — MarketStrip (实时价格)
- **ml-scoreboard.tsx** (27行) — MLScoreboard (最佳模型高亮)

### Next.js 体验改进
- **无障碍**: aria-expanded, role=checkbox, prefers-reduced-motion
- **键盘快捷键**: Ctrl+Enter(运行), Ctrl+D(深度), Ctrl+1/2(标签切换), Escape(清除)
- **next/font**: 零CLS字体加载 (替换外部Google Fonts)
- **错误体验**: 重试按钮、连接状态、最后信号时间戳、离线横幅
- **SEO**: OG meta标签、自动关闭错误、colorScheme: dark
- **品牌**: 纯金色渐变 (去除残留的蓝紫色)

### 测试 — 139个前端测试 (vitest + @testing-library/react)
- **9个测试文件**: types, atoms, mock-data, decision-card, breaking, market-strip, ml-scoreboard, watchlist, daily-intel
- **CI管道**: vitest 加入 GitHub Actions Next.js 构建任务
- **总测试数**: 252个 (139前端 + 113后端)

### ML & 评估
- **Optuna 超参数优化器** — 贝叶斯优化策略参数
- **策略集成框架** — 多策略加权投票
- **LLM 解释器** — 自然语言解释优化后的参数
- **评估图表** — matplotlib 回测可视化
- **策略进化器** — 改进的 LLM 策略生成管道
- **每日评估管道** — 自动化评估运行

### 其他
- **CORS修复** — Vercel生产URL加入允许列表
- **ASSETS.md** — 图片资产目录
- **Figma品牌资产** — Logo变体已创建
- **Gitignore** — 排除运行时数据文件

---

## [2026-04-01] — 云部署 & 最终优化

### 云基础设施
- **云部署** — 在线体验: [Vercel](https://orallexa-aa9zjelyu-alex-jbs-projects.vercel.app)(前端) + [Railway](https://orallexa-ai-trading-agent-production.up.railway.app)(后端, Demo模式)
- **Demo模式** — `DEMO_MODE=true` 运行完整UI + 模拟数据，零API费用
- **轻量Docker** — `Dockerfile.railway` 云端专用: 无PyTorch, <1GB镜像
- **README重写** — 重新定位为 "AI交易操作系统"，加入在线演示链接
- **新Logo** — 蓝色翼 + 金蓝渐变文字，部署到README/PWA图标/演示文稿/仪表板

### 体验修复
- **API启动** — 去掉阻塞预加载，秒启动
- **7个静默异常** — 所有 `except: pass` 替换为debug日志
- **Viewport警告** — 修复Next.js metadata弃用警告

---

## [2026-04-01] — 深度学习模型 & 测试

### 新ML模型（共9个）
- **#014 EMAformer** — AAAI 2026 Transformer + Embedding Armor (Sharpe 1.24, +4.3%收益)
- **#015 PPO RL Agent** — 强化学习，Sharpe从-2.76优化到+4.86
- **#016 LLM策略进化** — Claude生成/测试/进化Python策略代码，多代迭代
- **#017 GNN (GAT)** — 图注意力网络，17只股票关系图，跨股票信号传播
- **#018 DDPM扩散模型** — 概率预测，50条价格路径，VaR/置信区间
- **#019 LangGraph** — Bull/Bear辩论迁移到StateGraph，类型化状态+条件路由

### 质量 & DevOps
- **#020 测试套件** — 113个测试（集成+ML回归+API E2E），108通过，0失败
- **#021 社交内容** — 每个板块 "Copy for X" 按钮，大白话风格推文
- **#022 CI/CD** — GitHub Actions: 代码检查+测试+构建，每次push自动运行
- **#023 Docker** — `docker compose up` 一键部署，含健康检查
- **#024 Alpaca模拟交易** — 信号自动执行为括号订单（止损+止盈）
- **#025 WebSocket** — `/ws/live` 实时价格推送+信号变化检测
- **#026 PWA** — 可安装为手机App，自定义图标

---

## [2026-04-01] — 生产就绪: Docker + README + 部署修复

### 新增
- **Dockerfile** — Python 3.11-slim, uvicorn入口, 端口8002
- **docker-compose.yml** — 一键启动 API + 前端
- **README.md** — GitHub级英文README: 徽章、架构图、功能表、快速启动
- **README_CN.md** — 完整中文翻译

---

## [2026-04-01] — 社交级每日情报升级

### 改动
- **LLM升级**: Haiku → Sonnet，写作质量大幅提升
- **成交量异动检测**: 扫描50+股票，检测2倍以上异常成交量
- **社交推文串**: 6-7条推文，每条≤280字符，一键复制到Twitter/X
- 每个板块独立社交帖: 异动/板块/推荐/简报/成交量

---

## [2026-04-01] — 每日市场情报仪表板

### 新增
- **daily_intel.py** — 自动化每日市场情报: 异动扫描、板块热力图、新闻情绪、AI简报、AI推荐
- **Signal / Intel 双视图** — 切换分析和情报模式
- 按日缓存，每日仅需3次LLM调用 (~$0.05)

---

## [2026-04-01] — UX/UI全面审计升级

### 仪表板
- **移动端适配** — 三栏布局在手机上折叠，响应式设计
- **无障碍** — ARIA标签、键盘支持、焦点指示器、对比度修复
- **加载动画** — 按钮内转圈、5步进度指示、骨架屏
- **错误处理** — 红色抖动动画、关闭按钮、alert角色

### 桌面AI助手
- **字体优化** — 最小字号8→10pt
- **风险管理卡** — 入场/止损/目标/风险收益比
- **i18n完善** — 新增20+翻译键
- **启动验证** — API key检查，缺失时降级运行

---

## [2026-04-01] — Claude AI信号覆盖

- **快速Claude覆盖** — 单次Haiku调用审查技术信号，调整置信度±15
- **安全护栏** — 不能翻转BUY↔SELL方向，仅微调

---

## [2026-04-01] — 多股票看板扫描

- **POST /api/watchlist-scan** — 最多10只股票并行分析，按信号强度排序
- **看板卡片** — Polymarket风格概率卡片，点击切换分析

---

## [2026-04-01] — 实时价格刷新

- **GET /api/live/{ticker}** — 实时价格+当日涨跌
- **30秒自动刷新** — 价格变动闪烁动画

---

## [2026-04-01] — 信号突变警报

- **信号检测引擎** — 对比当前信号vs上次记录，检测方向翻转/概率偏移/置信度变化
- **警报横幅** — 按严重度着色（红/金/绿）

---

## [2026-03-31] — LLM深度内容 & 仪表板研究升级

### 新增
- **LLM深度市场报告** — 500-700字结构化分析（市场结构/催化剂/ML共识/风险/操作位）
- **投资论文** — 可展开的200-300字策略上下文

### 改动
- Bull/Bear辩论: 400→800 tokens，结构化4点论证模板
- 风险管理: 扩展计划摘要 + 投资论文

---

## [2026-03-31] — 核心系统构建

- **#001 多代理架构** — 初始多代理交易分析框架
- **#002 双层模型路由** — Haiku快速 + Sonnet深度，成本降60%
- **#003 Bull/Bear辩论** — 轻量对抗辩论: 牛→熊→裁判
- **#004 交易反思记忆** — 交易后AI反思注入未来预测
- **#005 ML证据注入** — RF/XGBoost预测注入多代理分析
- **#006 深度分析Lite** — 3次LLM调用替代10+，15秒替代5分钟
- **#007 LLM调用日志** — 记录模型/延迟/tokens/成本
- **#008 实验框架** — FAST vs DEEP vs DUAL对比
- **#009 决策评估** — 方向准确/置信度校准/解释一致性/回测
- **#010 Gatsby UI** — 华尔街Art Deco主题
- **#011 Claude Sonnet 4.6** — 模型升级
- **#012 FinBERT情绪分析** — 替代VADER作为主分析器
- **#013 MOIRAI-2** — Salesforce零样本时序基础模型

---

## 汇总

| 指标 | 数值 |
|------|------|
| 总升级数 | 35+ |
| ML模型 | 9个 (RF, XGB, LR, EMAformer, MOIRAI-2, Chronos-2, DDPM, PPO RL, GNN) |
| 测试覆盖 | 252个测试 (139前端 + 113后端), 0失败 |
| API端点 | 17个REST + 1个WebSocket |
| 前端组件 | 8个提取模块 (page.tsx 减少52%) |
| 设计系统 | Art Deco, 4字体, 金色调色板, 中英双语 |
| 部署 | Docker + Vercel + Railway + GitHub Pages |
| 每次分析LLM成本 | ~$0.003 |
