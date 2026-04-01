/**
 * Client-side mock data for standalone demo mode.
 * Activates when the backend API is unreachable (e.g. Vercel-only deploy).
 */

const rand = (min: number, max: number) => Math.round((Math.random() * (max - min) + min) * 100) / 100;
const pick = <T,>(arr: T[]): T => arr[Math.floor(Math.random() * arr.length)];
const today = new Date().toISOString().slice(0, 10);
const now = () => new Date().toISOString();

// ── Analyze ──────────────────────────────────────────────────────────
export function mockAnalyze(ticker: string) {
  const decision = pick(["BUY", "SELL", "WAIT"]);
  const confidence = rand(62, 92);
  const up = decision === "BUY" ? rand(0.45, 0.65) : rand(0.20, 0.40);
  const down = decision === "SELL" ? rand(0.35, 0.55) : rand(0.10, 0.30);
  const neutral = Math.round((1 - up - down) * 100) / 100;
  return {
    decision, confidence,
    risk_level: decision === "BUY" ? "MEDIUM" : decision === "SELL" ? "HIGH" : "LOW",
    signal_strength: rand(55, 88),
    probabilities: { up, neutral: Math.max(neutral, 0.05), down },
    reasoning: [
      `RSI at ${Math.round(rand(30, 70))} — ${decision === "BUY" ? "oversold bounce likely" : "approaching resistance"}`,
      `Volume ${rand(1.2, 3.5).toFixed(1)}x average — institutional interest detected`,
      `MACD crossover ${decision === "BUY" ? "bullish" : "bearish"} on chart`,
      `Support/resistance levels well-defined`,
      `Sector momentum ${decision === "BUY" ? "positive" : "fading"}`,
    ],
    recommendation: decision === "BUY" ? `Enter ${ticker} long near current levels` : decision === "SELL" ? `Consider reducing ${ticker} exposure` : `Wait for clearer setup on ${ticker}`,
    source: "demo",
  };
}

// ── Deep Analysis (simulated SSE) ─────────────────────────────────────
const DEEP_STEPS = [
  { label: "Fetching market data...", label_zh: "获取市场数据..." },
  { label: "Running technical analysis...", label_zh: "运行技术分析..." },
  { label: "ML ensemble prediction...", label_zh: "ML 集成预测..." },
  { label: "Multi-agent debate...", label_zh: "多智能体辩论..." },
  { label: "Risk assessment...", label_zh: "风险评估..." },
  { label: "Generating investment plan...", label_zh: "生成投资方案..." },
  { label: "Compiling final report...", label_zh: "编译最终报告..." },
];

export function mockDeepAnalysis(ticker: string) {
  const base = mockAnalyze(ticker);
  const price = TICKER_PRICES[ticker] ?? 100;
  return {
    ...base,
    reports: {
      market: `${ticker} is trading at $${price.toFixed(2)}, showing ${base.decision === "BUY" ? "constructive momentum" : "mixed signals"}. Key support at $${(price * 0.93).toFixed(2)}, resistance at $${(price * 1.08).toFixed(2)}. The broader sector shows ${pick(["strength", "rotation", "consolidation"])}.`,
      fundamentals: `ML ensemble (RF + LR + XGB) signals ${base.decision} with ${base.confidence.toFixed(0)}% confidence. Walk-forward Sharpe: ${rand(0.8, 2.1).toFixed(2)}. Win rate: ${rand(52, 68).toFixed(0)}%.`,
      news: `Recent catalysts: ${pick(["earnings beat expectations", "new product launch", "analyst upgrade", "sector rotation inflow"])}. Sentiment mostly ${pick(["positive", "mixed", "cautiously optimistic"])}.`,
    },
    investment_plan: {
      position_pct: rand(3, 12),
      entry: price,
      stop_loss: Math.round(price * rand(0.94, 0.97) * 100) / 100,
      take_profit: Math.round(price * rand(1.05, 1.15) * 100) / 100,
      risk_reward: `1:${rand(1.5, 3.5).toFixed(1)}`,
      key_risks: ["Sector rotation risk", "Broader market correction", `Earnings miss for ${ticker}`],
      plan_summary: `${base.decision === "BUY" ? "Accumulate" : "Reduce"} ${ticker} with defined risk.`,
      analysis_narrative: `Multi-agent analysis shows ${base.decision.toLowerCase()} bias with ${base.confidence.toFixed(0)}% confidence.`,
    },
    ml_models: [
      { model: "RandomForest", sharpe: rand(0.9, 2.0), return: rand(5, 25), win_rate: rand(52, 68), trades: Math.round(rand(40, 120)) },
      { model: "LogisticReg", sharpe: rand(0.7, 1.8), return: rand(3, 20), win_rate: rand(50, 65), trades: Math.round(rand(30, 100)) },
      { model: "XGBoost", sharpe: rand(1.0, 2.5), return: rand(8, 30), win_rate: rand(55, 72), trades: Math.round(rand(35, 110)) },
    ],
    summary: { close: price, change_pct: rand(-3, 5), rsi: rand(30, 70), volume_ratio: rand(0.8, 2.5) },
  };
}

export { DEEP_STEPS };

// ── News ─────────────────────────────────────────────────────────────
const HEADLINES = [
  ["{t} Beats Q4 Estimates, Raises Full-Year Guidance", "bullish", 0.72],
  ["{t} CEO Announces $2B Buyback Program", "bullish", 0.55],
  ["Analysts Upgrade {t} to Overweight on AI Tailwinds", "bullish", 0.48],
  ["{t} Faces Regulatory Scrutiny Over Market Practices", "bearish", -0.45],
  ["{t} Revenue Misses Estimates Amid Slowing Demand", "bearish", -0.62],
  ["Options Market Signals Unusual Activity in {t}", "neutral", 0.05],
] as const;

export function mockNews(ticker: string) {
  const providers = ["Reuters", "Bloomberg", "CNBC", "MarketWatch", "Benzinga"];
  return {
    ticker,
    items: HEADLINES.map(([tpl, sentiment, score]) => ({
      title: (tpl as string).replace("{t}", ticker),
      sentiment, score: score as number + rand(-0.1, 0.1),
      url: "", summary: "", provider: pick(providers),
    })),
  };
}

// ── Profile ──────────────────────────────────────────────────────────
export function mockProfile() {
  return {
    style: pick(["Aggressive", "Balanced", "Conservative"]),
    win_rate: `${Math.round(rand(55, 72))}%`,
    today: `${Math.round(rand(2, 8))} trades`,
    win_streak: Math.round(rand(0, 5)),
    loss_streak: Math.round(rand(0, 2)),
    patterns: ["Strongest on momentum breakouts", "Better in morning session", "Tends to overtrade in low-vol"],
  };
}

// ── Journal ──────────────────────────────────────────────────────────
export function mockJournal() {
  const tickers = ["NVDA", "TSLA", "AAPL", "AMD", "META"];
  return {
    entries: Array.from({ length: 5 }, () => ({
      ticker: pick(tickers), mode: pick(["scalp", "intraday", "swing"]),
      decision: pick(["BUY", "SELL", "WAIT"]),
      timestamp: new Date(Date.now() - Math.random() * 172800000).toISOString().slice(0, 10),
    })),
  };
}

// ── Breaking Signals ─────────────────────────────────────────────────
export function mockBreakingSignals() {
  const tickers = ["NVDA", "TSLA", "PLTR", "COIN", "AMD"];
  return {
    signals: Array.from({ length: Math.round(rand(2, 4)) }, () => ({
      type: pick(["volume_spike", "sentiment_shift", "price_breakout"]),
      severity: pick(["high", "medium"]),
      ticker: pick(tickers),
      timestamp: new Date(Date.now() - Math.random() * 10800000).toISOString(),
      message: pick([
        "Volume spike detected — 3x average",
        "Sentiment flipped from bearish to bullish",
        "Price broke above key resistance",
      ]),
      direction: pick(["bullish", "bearish"]),
    })),
  };
}

// ── Live Price ───────────────────────────────────────────────────────
const TICKER_PRICES: Record<string, number> = {
  NVDA: 142.5, AAPL: 218.3, TSLA: 275.8, MSFT: 432.15, GOOG: 178.9,
  AMZN: 205.4, META: 615.2, AMD: 128.6, PLTR: 98.3, COIN: 265.7,
  SPY: 572.4, QQQ: 498.1,
};

export function mockLive(ticker: string) {
  const base = TICKER_PRICES[ticker.toUpperCase()] ?? 100;
  const price = Math.round(base * (1 + (Math.random() - 0.5) * 0.04) * 100) / 100;
  const changePct = rand(-3, 4);
  return {
    ticker: ticker.toUpperCase(), price, change_pct: changePct,
    prev_close: Math.round(price / (1 + changePct / 100) * 100) / 100,
    high: Math.round(price * rand(1.005, 1.025) * 100) / 100,
    low: Math.round(price * rand(0.975, 0.995) * 100) / 100,
    volume: Math.round(rand(5000000, 80000000)),
    last_signal: { decision: pick(["BUY", "SELL", "WAIT"]), confidence: rand(60, 90), signal_strength: rand(50, 85), risk_level: pick(["LOW", "MEDIUM", "HIGH"]), timestamp: now() },
    timestamp: now(),
  };
}

// ── Chart Analysis ───────────────────────────────────────────────────
export function mockChartAnalysis(ticker: string) {
  const base = mockAnalyze(ticker);
  return {
    ...base,
    chart_insight: {
      trend: pick(["Uptrend — higher highs and higher lows", "Downtrend — lower highs confirmed", "Range-bound between key levels"]),
      setup: pick(["Bull flag forming", "Double bottom at support", "Breakout above trendline"]),
      levels: `Support: $${(TICKER_PRICES[ticker] ?? 100 * 0.95).toFixed(2)} | Resistance: $${(TICKER_PRICES[ticker] ?? 100 * 1.05).toFixed(2)}`,
      summary: `${ticker} showing ${base.decision === "BUY" ? "constructive" : "distribution"} pattern.`,
    },
  };
}

// ── Watchlist Scan ───────────────────────────────────────────────────
export function mockWatchlistScan(tickers: string[]) {
  return {
    tickers: tickers.slice(0, 10).map(tk => {
      const d = mockAnalyze(tk);
      return {
        ticker: tk.toUpperCase(), price: TICKER_PRICES[tk.toUpperCase()] ?? rand(50, 300),
        change_pct: rand(-4, 6), ...d, error: null,
      };
    }).sort((a, b) => b.signal_strength - a.signal_strength),
  };
}

// ── Daily Intel ──────────────────────────────────────────────────────
export function mockDailyIntel() {
  return {
    date: today, generated_at: now(), market_mood: "Risk-On",
    summary: "RISK-ON\n\nMoney is flooding into semiconductors and AI plays today, with NVIDIA leading the charge at +5.2% on surging datacenter revenue. The AI capex cycle narrative just got another data point — and the market is buying it aggressively.\n\nTwo stories dominate: First, NVDA's datacenter backlog is reportedly filled through 2027, which triggered a sector-wide rally with SOXX up 3.2%. Second, Bitcoin smashing through $90K has lit up the crypto ecosystem — COIN is riding 2.1x normal volume as institutional ETF flows hit records.\n\nThe losers tell the story too: META is down 2.8% on fresh antitrust concerns, and the rotation out of defensive sectors (Utilities -1.5%, Real Estate -1.2%) confirms this is a genuine risk-on move, not just a tech squeeze.\n\nThe #1 risk everyone's ignoring: the Fed. Officials signaled patience on cuts today amid sticky inflation. If next week's CPI prints hot, this entire rally reverses. Watch SPX 5700 as the floor.",
    gainers: [
      { ticker: "NVDA", price: 142.5, change_pct: 5.2, volume: 68000000, volume_ratio: 2.3 },
      { ticker: "PLTR", price: 98.3, change_pct: 4.1, volume: 45000000, volume_ratio: 1.8 },
      { ticker: "COIN", price: 265.7, change_pct: 3.8, volume: 22000000, volume_ratio: 2.1 },
      { ticker: "AMD", price: 128.6, change_pct: 2.9, volume: 38000000, volume_ratio: 1.5 },
      { ticker: "TSLA", price: 275.8, change_pct: 2.4, volume: 55000000, volume_ratio: 1.3 },
    ],
    losers: [
      { ticker: "META", price: 615.2, change_pct: -2.8, volume: 30000000, volume_ratio: 1.6 },
      { ticker: "GOOG", price: 178.9, change_pct: -1.9, volume: 25000000, volume_ratio: 1.2 },
      { ticker: "AMZN", price: 205.4, change_pct: -1.5, volume: 28000000, volume_ratio: 1.1 },
      { ticker: "MSFT", price: 432.15, change_pct: -0.8, volume: 20000000, volume_ratio: 0.9 },
    ],
    volume_spikes: [
      { ticker: "NVDA", price: 142.5, change_pct: 5.2, volume_ratio: 2.3 },
      { ticker: "COIN", price: 265.7, change_pct: 3.8, volume_ratio: 2.1 },
      { ticker: "PLTR", price: 98.3, change_pct: 4.1, volume_ratio: 1.8 },
    ],
    sectors: [
      { sector: "Semiconductors", etf: "SOXX", change_pct: 3.2 },
      { sector: "Technology", etf: "XLK", change_pct: 2.1 },
      { sector: "Comm Services", etf: "XLC", change_pct: 0.8 },
      { sector: "Financials", etf: "XLF", change_pct: 0.5 },
      { sector: "Energy", etf: "XLE", change_pct: 0.2 },
      { sector: "Industrials", etf: "XLI", change_pct: -0.1 },
      { sector: "Healthcare", etf: "XLV", change_pct: -0.4 },
      { sector: "Consumer Disc", etf: "XLY", change_pct: -0.6 },
      { sector: "Consumer Staples", etf: "XLP", change_pct: -0.9 },
      { sector: "Real Estate", etf: "XLRE", change_pct: -1.2 },
      { sector: "Utilities", etf: "XLU", change_pct: -1.5 },
    ],
    headlines: [
      { title: "NVIDIA Datacenter Revenue Surges 40% as AI Demand Accelerates", ticker: "NVDA", sentiment: "bullish", score: 0.78, url: "", provider: "Reuters" },
      { title: "Palantir Wins $500M Government Contract for AI Platform", ticker: "PLTR", sentiment: "bullish", score: 0.65, url: "", provider: "Bloomberg" },
      { title: "Bitcoin Breaks $90K as Institutional Inflows Hit Record", ticker: "COIN", sentiment: "bullish", score: 0.58, url: "", provider: "CNBC" },
      { title: "Meta Faces Antitrust Lawsuit Over Social Media Monopoly", ticker: "META", sentiment: "bearish", score: -0.52, url: "", provider: "WSJ" },
      { title: "Fed Officials Signal Patience on Rate Cuts Amid Sticky Inflation", ticker: "SPY", sentiment: "bearish", score: -0.35, url: "", provider: "MarketWatch" },
      { title: "AMD Launches Next-Gen AI Chips to Challenge NVIDIA", ticker: "AMD", sentiment: "bullish", score: 0.42, url: "", provider: "TechCrunch" },
      { title: "Tesla Deliveries Beat Estimates Despite Price War", ticker: "TSLA", sentiment: "bullish", score: 0.38, url: "", provider: "Bloomberg" },
      { title: "Unusual Bullish Options Positioning in Semiconductors", ticker: "SOXX", sentiment: "bullish", score: 0.30, url: "", provider: "Benzinga" },
    ],
    ai_picks: [
      { ticker: "NVDA", direction: "bullish", reason: "AI capex cycle accelerating — datacenter backlog through 2027", catalyst: "Earnings report next week" },
      { ticker: "PLTR", direction: "bullish", reason: "Government AI spending inflection + commercial momentum", catalyst: "$500M contract confirmation" },
      { ticker: "META", direction: "bearish", reason: "Antitrust overhang caps upside — rotation into pure AI plays", catalyst: "Court hearing date" },
      { ticker: "COIN", direction: "bullish", reason: "BTC $90K breakout drives exchange volume surge", catalyst: "ETF flow data release" },
    ],
    orallexa_thread: [
      `🚨 RISK-ON — ${today}\n\n$NVDA ripping +5.2% on datacenter demand. Semis leading everything. Money pouring into AI. 👇`,
      "🟢 $NVDA +5.2% — AI capex cycle is real\n🟢 $PLTR +4.1% — $500M gov contract\n🟢 $COIN +3.8% — BTC $90K breakout\n🔴 $META -2.8% — antitrust overhang",
      "🐳 UNUSUAL ACTIVITY\n\n$NVDA volume 2.3x average\n$COIN volume 2.1x average\n\nInstitutional money moving into AI + crypto.",
      "📊 SECTOR WATCH\n\n🟢 Semis +3.2% — clear leader\n🟢 Tech +2.1%\n🔴 Utilities -1.5%\n🔴 Real Estate -1.2%\n\nClassic risk-on rotation.",
      "🤖 AI PICKS\n\n$NVDA — datacenter backlog through 2027\n$PLTR — gov AI spend inflection\n$COIN — BTC breakout = volume surge\n\nContrarian: $META short",
      `⚠️ RISK: Fed patience on rate cuts. If CPI comes in hot, this rally reverses fast.\n\nWatch SPX 5700.\n\n#stocks #trading #fintwit`,
    ],
    social_posts: {
      movers: `🔥 MOVERS — ${today}\n\n🟢 $NVDA +5.2%\n🟢 $PLTR +4.1%\n🟢 $COIN +3.8%\n🔴 $META -2.8%\n\n#stocks #trading`,
      sectors: "📊 SECTOR WATCH\n\n🟢 Semis +3.2%, Tech +2.1%\n🔴 Utilities -1.5%, REITs -1.2%\n\nRisk-on rotation. #trading",
      picks: "🤖 AI PICKS\n\n$NVDA — datacenter backlog\n$PLTR — gov AI inflection\n$COIN — BTC breakout\n\n#fintwit",
      brief: `☀️ Risk-on — $NVDA +5.2% leads as AI capex accelerates. Watch the Fed. #stocks #trading`,
      volume: "🐳 UNUSUAL ACTIVITY\n\n$NVDA — 2.3x avg volume\n$COIN — 2.1x avg volume\n\nSmart money moving. 👀",
    },
  };
}
