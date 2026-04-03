/* ── Types ─────────────────────────────────────────────────────────────── */
export interface Decision { decision: string; confidence: number; risk_level: string; signal_strength: number; recommendation: string; reasoning: string[]; source?: string; probabilities?: { up: number; neutral: number; down: number }; }
export interface NewsItem { title: string; sentiment: "bullish" | "bearish" | "neutral"; score: number; url?: string; summary?: string; provider?: string; }
export interface DeepReport { market: string; fundamentals: string; news: string; }
export interface RiskMgmt { entry: number; stop: number; target: number; size: number; }
export interface InvestmentPlan { position_pct: number; entry: number; stop_loss: number; take_profit: number; risk_reward: string; key_risks: string[]; plan_summary: string; analysis_narrative?: string; }
export interface MLModel { model: string; sharpe: number; return: number; win_rate: number; trades: number; }
export interface ChartInsight { trend: string; setup: string; levels: string; summary: string; }
export interface Profile { style: string; win_rate: string; today: string; win_streak: number; loss_streak: number; patterns: string[]; }
export interface JournalEntry { ticker: string; mode: string; decision: string; timestamp: string; }
export interface MarketSummary { close?: number; change_pct?: number; rsi?: number; volume_ratio?: number; }
export interface BreakingSignal { type: string; severity: string; ticker: string; timestamp: string; message: string; direction?: string; shift_pct?: number; prev_decision?: string; new_decision?: string; }
export interface WatchlistItem { ticker: string; price: number | null; change_pct: number | null; decision: string; confidence: number; signal_strength: number; risk_level: string; probabilities: { up: number; neutral: number; down: number }; recommendation: string; error: string | null; }
export interface SocialPosts { movers: string; sectors: string; picks: string; brief: string; volume: string; }
export interface DailyIntelData { date: string; generated_at: string; market_mood: string; summary: string; gainers: { ticker: string; price: number; change_pct: number; volume: number; volume_ratio?: number }[]; losers: { ticker: string; price: number; change_pct: number; volume: number; volume_ratio?: number }[]; volume_spikes?: { ticker: string; price: number; change_pct: number; volume_ratio: number }[]; sectors: { sector: string; etf: string; change_pct: number }[]; headlines: { title: string; ticker: string; sentiment: string; score: number; url: string; provider: string }[]; ai_picks: { ticker: string; direction: string; reason: string; catalyst: string }[]; orallexa_thread?: string[]; social_posts?: SocialPosts; }

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
