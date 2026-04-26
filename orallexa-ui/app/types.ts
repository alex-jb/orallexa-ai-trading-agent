/* ── Types ─────────────────────────────────────────────────────────────── */
export interface Decision { decision: string; confidence: number; risk_level: string; signal_strength: number; recommendation: string; reasoning: string[]; source?: string; probabilities?: { up: number; neutral: number; down: number }; }
export interface NewsItem { title: string; sentiment: "bullish" | "bearish" | "neutral"; score: number; url?: string; summary?: string; provider?: string; }
export interface DeepReport { market: string; fundamentals: string; news: string; }
export interface RiskMgmt { entry: number; stop: number; target: number; size: number; }
export interface InvestmentPlan { position_pct: number; entry: number; stop_loss: number; take_profit: number; risk_reward: string; key_risks: string[]; plan_summary: string; analysis_narrative?: string; }
export interface MLModel { model: string; sharpe: number; return: number; win_rate: number; trades: number; status?: "ok" | "failed" | "skipped"; error?: string; purpose?: string; }
export interface ChartInsight { trend: string; setup: string; levels: string; summary: string; }
export interface Profile { style: string; win_rate: string; today: string; win_streak: number; loss_streak: number; patterns: string[]; }
export interface JournalEntry { ticker: string; mode: string; decision: string; timestamp: string; }
export interface MarketSummary { close?: number; change_pct?: number; rsi?: number; volume_ratio?: number; }
export interface BreakingSignal { type: string; severity: string; ticker: string; timestamp: string; message: string; direction?: string; shift_pct?: number; prev_decision?: string; new_decision?: string; }
export interface WatchlistFusion { conviction: number; direction: "BULLISH" | "BEARISH" | "NEUTRAL"; confidence: number; n_sources: number; top_sources: { name: string; score: number }[]; detail: string; }
export interface WatchlistItem { ticker: string; price: number | null; change_pct: number | null; decision: string; confidence: number; signal_strength: number; risk_level: string; probabilities: { up: number; neutral: number; down: number }; recommendation: string; error: string | null; fusion?: WatchlistFusion; fusion_error?: string; pm_preview?: { approved: boolean | null; scaled_position_pct?: number; reason?: string; warnings?: string[] }; pm_error?: string; }
export interface SocialPosts { movers: string; sectors: string; picks: string; brief: string; volume: string; }
export interface MacroIndicator { label: string; value: string; change: number; direction: "up" | "down" | "flat"; }
export interface EconEvent { date: string; time: string; event: string; impact: "high" | "medium" | "low"; forecast?: string; previous?: string; }
export interface FearGreedData { score: number; label: string; components: { name: string; value: number; signal: "extreme_fear" | "fear" | "neutral" | "greed" | "extreme_greed" }[]; }
export interface MarketBreadth { advancers: number; decliners: number; unchanged: number; new_highs: number; new_lows: number; adv_vol: number; dec_vol: number; }
export interface OptionsFlow { ticker: string; type: "call" | "put"; premium: string; strike: string; expiry: string; sentiment: "bullish" | "bearish"; unusual: boolean; }
export interface EarningsEvent { ticker: string; date: string; days_until: number; eps_estimate: number | null; pead_drift: number | null; positive_rate: number | null; narrative: string; }
export interface ScenarioImpact { ticker: string; impact_pct: number; direction: "bullish" | "bearish" | "neutral"; severity: "low" | "medium" | "high"; reasoning: string; time_horizon: string; key_level: number; }
export interface ScenarioResult { scenario: string; date: string; impacts: ScenarioImpact[]; portfolio_delta_pct: number; historical_analog: { event: string; date: string; market_reaction: string; relevance: string }; hedging_suggestions: string[]; summary: string; confidence: number; regime_shift: string; }
export interface PerspectiveView { role: string; icon: string; bias: "BULLISH" | "BEARISH" | "NEUTRAL"; score: number; conviction: number; reasoning: string; key_factor: string; }
export interface RoleMemoryStats { total: number; correct: number; accuracy: number; by_bias: Record<string, { total: number; correct: number }>; best_ticker: { ticker: string; accuracy: number } | null; worst_ticker: { ticker: string; accuracy: number } | null; }
export interface PerspectivePanel { consensus: string; avg_score: number; agreement: number; perspectives: PerspectiveView[]; panel_summary: string; }
export interface BiasPattern { type: string; severity: "low" | "medium" | "high"; description: string; ticker?: string; magnitude: number; }
export interface BiasCalibration { range: string; label: string; count: number; accuracy: number | null; avg_return?: number | null; }
export interface BiasProfile { status: string; total_evaluated?: number; minimum_required?: number; overall?: { accuracy: number; correct: number; total: number; avg_return: number; forward_days: number; days_analyzed: number }; by_direction?: { buy: { accuracy: number; count: number }; sell: { accuracy: number; count: number } }; by_ticker?: Record<string, { accuracy: number; count: number; avg_return: number }>; calibration?: BiasCalibration[]; patterns?: BiasPattern[]; recommendations?: string[]; updated_at?: string; }
export interface PredictionMarket { question: string; yes_price: number; volume_24hr: number; end_date: string; sign: number; }
export interface RegimeProposal { ticker: string; regime: "trending" | "ranging" | "volatile" | "unknown"; strategy: string | null; params: Record<string, number | string>; reasoning: string; source: "heuristic" | "llm" | "none"; }
export interface PortfolioManagerVerdict { approved: boolean | null; scaled_position_pct?: number; reason?: string; warnings?: string[]; original_confidence?: number; adjusted_confidence?: number; checks?: Record<string, number | string | boolean>; error?: string; }
export interface TokenBudgetSnapshot { label?: string; n_calls: number; used_tokens: number; used_cost_usd: number; cap_tokens: number | null; cap_usd: number | null; remaining_tokens: number | null; remaining_usd: number | null; exhausted: boolean; }
export interface SignalSource { score: number; weight: number; normalized_weight: number; available: boolean; signals?: string[]; agreement?: number; n_models?: number; pc_ratio?: number; unusual_calls?: { strike: number; volume: number; oi: number; ratio: number }[]; unusual_puts?: { strike: number; volume: number; oi: number; ratio: number }[]; max_pain?: number; insider_transactions?: { type: string; shares: number; text: string }[]; short_pct?: number; institutional_pct?: number; n_posts?: number; bullish?: number; bearish?: number; engagement?: number; days_until?: number | null; next_date?: string | null; avg_drift_5d?: number | null; positive_rate?: number | null; narrative?: string; n_markets?: number; n_directional?: number; total_volume_24hr?: number; markets?: PredictionMarket[]; }
export interface SignalFusion { conviction: number; direction: "BULLISH" | "BEARISH" | "NEUTRAL"; confidence: number; n_sources: number; sources: Record<string, SignalSource>; fusion_detail: string; }
export interface SwarmPath { step: number; avg_position: number; bullish_pct: number; bearish_pct: number; neutral_pct: number; }
export interface SwarmResult { ticker: string; convergence: string; conviction: number; convergence_speed: string; avg_steps_to_converge: number; buy_pct: number; sell_pct: number; mixed_pct: number; n_simulations: number; avg_final_position: number; sample_path: SwarmPath[]; }
export interface BacktestResult { strategy: string; total_return: number; sharpe: number; max_drawdown: number; win_rate: number; trades: number; profit_factor?: number; }
export interface BacktestSummary { ticker: string; period: string; results: BacktestResult[]; best_strategy: string; }
export interface Playbook { tone_en: string; tone_zh: string; environment: { risk_level: string; index_bias: string; index_bias_zh: string; sentiment: string; sentiment_zh: string; position_advice: string; position_advice_zh: string }; main_theme_en: string; main_theme_zh: string; secondary_themes_en: string[]; secondary_themes_zh: string[]; biggest_risk_en: string; biggest_risk_zh: string; biggest_opportunity_en: string; biggest_opportunity_zh: string; }
export interface DailyIntelData { date: string; generated_at: string; market_mood: string; summary: string; playbook?: Playbook; gainers: { ticker: string; price: number; change_pct: number; volume: number; volume_ratio?: number }[]; losers: { ticker: string; price: number; change_pct: number; volume: number; volume_ratio?: number }[]; volume_spikes?: { ticker: string; price: number; change_pct: number; volume_ratio: number }[]; sectors: { sector: string; etf: string; change_pct: number }[]; headlines: { title: string; ticker: string; sentiment: string; score: number; url: string; provider: string }[]; ai_picks: { ticker: string; direction: string; reason: string; catalyst: string; target_price?: number; stop_loss?: number; timeframe?: string; conviction?: string; regime?: { regime: string; strategy: string | null; source: string }; pm_preview?: { approved: boolean | null; scaled_position_pct?: number; reason?: string; warnings?: string[] } | null }[]; orallexa_thread?: string[]; social_posts?: SocialPosts; macro?: MacroIndicator[]; econ_calendar?: EconEvent[]; fear_greed?: FearGreedData; breadth?: MarketBreadth; options_flow?: OptionsFlow[]; earnings_watchlist?: EarningsEvent[]; }

/* ── i18n ──────────────────────────────────────────────────────────────── */
export const T: Record<string, Record<string, string>> = {
  EN: {
    brand: "ORALLEXA", subtitle: "Capital Intelligence System", active: "Active",
    asset: "Asset", context: "Context", contextPh: "Catalyst, level, thesis...",
    engineStatus: "Engine Status", engine: "Engine", strategy: "Strategy", horizon: "Horizon",
    runSignal: "Run Signal", scanning: "Scanning...", openIntel: "Deep Intelligence",
    journal: "Journal", recentLog: "recent decisions logged", viewLog: "View Execution Log →",
    snapshot: "Market Snapshot", analyzeSnap: "Analyze Snapshot", voice: "Voice Command",
    holdSpeak: "Hold to Speak", engineDec: "Engine Decision", standby: "STANDBY",
    runToBegin: "Run Signal to engage the capital engine", bullScan: "Bull scanning market...",
    signal: "Signal", confidence: "Confidence", risk: "Risk",
    marketIntel: "Market Intelligence", overall: "Overall",
    marketReport: "Market Report", fundamentals: "ML Analysis",
    chartInsight: "Chart Insight", capitalProfile: "Capital Profile",
    style: "Style", winRate: "Win Rate", today: "Today",
    executionLog: "Execution Log", behaviorSignals: "Behavior Signals",
    why: "Bull / Bear Debate", techDetails: "Technical Details", riskMgmt: "Risk Management",
    entry: "Entry", stop: "Stop", target: "Target", size: "Size",
    listening: "Listening...", voiceError: "Microphone access denied",
    scalp: "SCALP", intraday: "INTRADAY", swing: "SWING",
    m5: "5M", m15: "15M", h1: "1H", d1: "1D",
    watchlist: "Watchlist", watchlistPh: "NVDA, AAPL, TSLA...", scanAll: "Scan All", scanningAll: "Scanning...",
    signalTab: "Signal", intelTab: "Intel", morningBrief: "Morning Brief", topMovers: "Top Movers",
    sectorMap: "Sector Heatmap", aiPicks: "AI Picks", worthWatching: "Worth Watching", refresh: "Refresh",
    lastUpdated: "Last updated", catalyst: "Catalyst",
    macroPulse: "Macro Pulse", econCalendar: "Economic Calendar", fearGreed: "Fear & Greed Index",
    calToday: "Today", calTomorrow: "Tomorrow", forecast: "Forecast", previous: "Previous",
    marketBreadth: "Market Breadth", advancers: "Advancers", decliners: "Decliners",
    newHighs: "52W Highs", newLows: "52W Lows", optionsFlow: "Options Flow",
    earningsWatch: "Earnings Watch", peadDrift: "PEAD Drift", eps: "EPS", daysLabel: "days", positiveRateLabel: "win rate",
    regimeStrategy: "Regime & Strategy",
    portfolioManager: "Portfolio Manager", pmApproved: "Approved", pmRejected: "Rejected", pmPosition: "Position", pmWarnings: "Warnings",
    tokenBudget: "Token Budget", budgetUsed: "used", budgetCap: "cap", budgetSkipped: "skipped", budgetExhausted: "exhausted",
    scanFusion: "8-src fusion", scanFusionHint: "pulls Polymarket + Reddit — slower",
    share: "Share", shareX: "Share on X", shareLinkedIn: "Share on LinkedIn", copyLink: "Copy Link", copied: "Copied",
    fearLabel: "Fear", greedLabel: "Greed", unchanged: "unchanged", volumeLabel: "Volume",
    callType: "CALL", putType: "PUT", unusualActivity: "unusual activity",
    gainersLabel: "Gainers", losersLabel: "Losers", volumeSpikes: "Volume Spikes",
    oralexaThread: "Orallexa Thread", copy: "Copy", copyFullThread: "Copy Full Thread",
    demoMode: "Demo Mode — Simulated data for demonstration",
    networkOffline: "Network offline — data may be stale",
    priceChart: "Price Chart",
    backtestResults: "Backtest Results", strategyName: "Strategy", totalReturn: "Total Return",
    sharpeRatio: "Sharpe Ratio", maxDrawdown: "Max Drawdown", winRateCol: "Win Rate",
    tradesCol: "Trades", profitFactor: "Profit Factor", bestStrategy: "Best Strategy",
    backtestPeriod: "Period", noBacktestData: "No backtest data available",
    bt1y: "1Y", bt2y: "2Y", bt5y: "5Y", btMax: "Max",
    scenario: "What-If Scenario", scenarioPh: "e.g. Fed raises rates by 50bp...",
    scenarioRun: "Simulate", scenarioRunning: "Simulating...",
    scenarioImpact: "Impact Analysis", scenarioHistory: "Historical Parallel",
    scenarioHedge: "Hedging Suggestions", scenarioPortfolio: "Portfolio Impact",
    perspectivePanel: "Perspective Panel", perspectiveConsensus: "Consensus",
    perspectiveAgreement: "Agreement",
    biasTracker: "Prediction Bias Tracker", biasAccuracy: "Accuracy",
    biasBuy: "BUY Accuracy", biasSell: "SELL Accuracy", biasPatterns: "Detected Biases",
    biasCalibration: "Confidence Calibration", biasRecommendations: "Self-Corrections",
    biasInsufficient: "Need more predictions to analyze bias (minimum 5)",
    signalFusion: "Signal Fusion", fusionConviction: "Conviction",
    fusionSources: "Signal Sources", fusionOptions: "Options Flow",
    fusionInstitutional: "Institutional",
    swarmSim: "Agent Swarm", swarmConvergence: "Convergence",
    swarmSpeed: "Speed", swarmAgents: "20 agents",
  },
  ZH: {
    brand: "ORALLEXA", subtitle: "资本智能系统", active: "运行中",
    asset: "资产", context: "背景", contextPh: "催化剂、关键位、策略...",
    engineStatus: "引擎状态", engine: "引擎", strategy: "策略", horizon: "周期",
    runSignal: "执行信号", scanning: "扫描中...", openIntel: "深度分析",
    journal: "交易日志", recentLog: "条近期决策记录", viewLog: "查看执行日志 →",
    snapshot: "图表快照", analyzeSnap: "分析快照", voice: "语音指令",
    holdSpeak: "按住说话", engineDec: "引擎决策", standby: "待命",
    runToBegin: "执行信号以启动资本引擎", bullScan: "Bull 扫描市场中...",
    signal: "信号", confidence: "置信度", risk: "风险",
    marketIntel: "市场情报", overall: "综合",
    marketReport: "市场报告", fundamentals: "ML 分析",
    chartInsight: "图表洞察", capitalProfile: "资本画像",
    style: "风格", winRate: "胜率", today: "今日",
    executionLog: "执行记录", behaviorSignals: "行为信号",
    why: "多空辩论", techDetails: "技术细节", riskMgmt: "风险管理",
    entry: "入场", stop: "止损", target: "目标", size: "仓位",
    listening: "录音中...", voiceError: "麦克风权限被拒绝",
    scalp: "超短", intraday: "日内", swing: "波段",
    m5: "5分", m15: "15分", h1: "1时", d1: "1日",
    watchlist: "自选股", watchlistPh: "NVDA, AAPL, TSLA...", scanAll: "批量扫描", scanningAll: "扫描中...",
    signalTab: "信号", intelTab: "情报", morningBrief: "晨间简报", topMovers: "今日异动",
    sectorMap: "板块热力图", aiPicks: "AI 推荐", worthWatching: "值得关注", refresh: "刷新",
    lastUpdated: "更新于", catalyst: "催化剂",
    macroPulse: "宏观脉搏", econCalendar: "经济日历", fearGreed: "恐惧与贪婪指数",
    calToday: "今天", calTomorrow: "明天", forecast: "预期", previous: "前值",
    marketBreadth: "市场广度", advancers: "上涨", decliners: "下跌",
    newHighs: "52周新高", newLows: "52周新低", optionsFlow: "期权异动",
    earningsWatch: "财报观察", peadDrift: "财报后漂移", eps: "每股收益", daysLabel: "天", positiveRateLabel: "胜率",
    regimeStrategy: "行情与策略",
    portfolioManager: "组合管理", pmApproved: "已批准", pmRejected: "已拒绝", pmPosition: "仓位", pmWarnings: "警告",
    tokenBudget: "Token 预算", budgetUsed: "已用", budgetCap: "上限", budgetSkipped: "跳过", budgetExhausted: "超额",
    scanFusion: "8 源融合", scanFusionHint: "拉 Polymarket + Reddit — 较慢",
    share: "分享", shareX: "分享到 X", shareLinkedIn: "分享到 LinkedIn", copyLink: "复制链接", copied: "已复制",
    fearLabel: "恐惧", greedLabel: "贪婪", unchanged: "不变", volumeLabel: "成交量",
    callType: "看涨", putType: "看跌", unusualActivity: "异动活动",
    gainersLabel: "涨幅榜", losersLabel: "跌幅榜", volumeSpikes: "成交量异动",
    oralexaThread: "Orallexa 推文串", copy: "复制", copyFullThread: "复制完整推文串",
    demoMode: "演示模式 — 展示数据非实时行情",
    networkOffline: "网络已断开 — 数据可能不是最新的",
    priceChart: "价格走势",
    backtestResults: "回测结果", strategyName: "策略", totalReturn: "总收益",
    sharpeRatio: "夏普比率", maxDrawdown: "最大回撤", winRateCol: "胜率",
    tradesCol: "交易次数", profitFactor: "盈利因子", bestStrategy: "最优策略",
    backtestPeriod: "区间", noBacktestData: "暂无回测数据",
    bt1y: "1年", bt2y: "2年", bt5y: "5年", btMax: "最大",
    scenario: "假设场景", scenarioPh: "例如：美联储意外加息50bp...",
    scenarioRun: "模拟", scenarioRunning: "模拟中...",
    scenarioImpact: "影响���析", scenarioHistory: "历史参照",
    scenarioHedge: "对冲建议", scenarioPortfolio: "组合影响",
    perspectivePanel: "多视角面板", perspectiveConsensus: "共识",
    perspectiveAgreement: "一致性",
    biasTracker: "预测偏差追踪", biasAccuracy: "准确率",
    biasBuy: "做多准确率", biasSell: "做空准确率", biasPatterns: "检测到的偏差",
    biasCalibration: "置信度校准", biasRecommendations: "自我修正建议",
    biasInsufficient: "需要更多预测数据来分析偏差（最少5条）",
    signalFusion: "信号融合", fusionConviction: "信念",
    fusionSources: "信号来源", fusionOptions: "期权异动",
    fusionInstitutional: "机构动向",
    swarmSim: "Agent 群体模拟", swarmConvergence: "收敛方向",
    swarmSpeed: "速度", swarmAgents: "20个Agent",
  },
};

/* ── Helpers ────────────────────────────────────────────────────────────── */
export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";
export const TWITTER_HANDLE = "@orallexatrading";

export const displayDec = (d: string) => ({ BUY: "BULLISH", SELL: "BEARISH", WAIT: "NEUTRAL" }[d] ?? d);
export const subtitleDec = (d: string, zh: boolean) => zh
  ? ({ BUY: "看涨信号", SELL: "看跌信号", WAIT: "无明确方向" }[d] ?? "")
  : ({ BUY: "Bullish setup detected", SELL: "Bearish signal detected", WAIT: "No clear setup" }[d] ?? "");
export const sigLabel = (s: number) => s >= 80 ? "Very Strong" : s >= 65 ? "Strong" : s >= 50 ? "Moderate" : s >= 35 ? "Weak" : "Very Weak";
export const confLabel = (c: number) => c >= 70 ? "High" : c >= 50 ? "Moderate" : c >= 30 ? "Low" : "Very Low";
export const riskLabel = (r: string) => ({ LOW: "Low", MEDIUM: "Moderate", HIGH: "Elevated" }[r] ?? r);
export const decColor = (d: string) => d === "BUY" ? "#006B3F" : d === "SELL" ? "#8B0000" : "#D4AF37";
export const riskColor = (r: string) => r === "LOW" ? "#006B3F" : r === "HIGH" ? "#8B0000" : "#D4AF37";
export const sentCls = (s: string) => s === "bullish" ? "text-[#006B3F]" : s === "bearish" ? "text-[#8B0000]" : "text-[#8B8E96]";
export const recBg = (d: string) => d === "BUY" ? "rgba(0,107,63,0.08)" : d === "SELL" ? "rgba(139,0,0,0.08)" : "rgba(212,175,55,0.06)";
export const decColorJournal = (d: string) => d === "BUY" ? "#006B3F" : d === "SELL" ? "#8B0000" : "#D4AF37";
export function nsSummary(items: NewsItem[]) { const avg = items.reduce((s, n) => s + n.score, 0) / (items.length || 1); if (avg > 0.1) return { label: "bullish", color: "#006B3F", avg }; if (avg < -0.1) return { label: "bearish", color: "#8B0000", avg }; return { label: "neutral", color: "#8B8E96", avg }; }
export function copyWithAttribution(text: string) { navigator.clipboard.writeText(`${text}\n\n${TWITTER_HANDLE}`); }
