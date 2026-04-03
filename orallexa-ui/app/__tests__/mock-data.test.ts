import { describe, it, expect } from "vitest";
import {
  mockAnalyze, mockDeepAnalysis, mockNews, mockProfile,
  mockJournal, mockBreakingSignals, mockWatchlistScan,
  mockChartAnalysis, mockDailyIntel,
} from "../mock-data";

describe("mockAnalyze", () => {
  it("returns a valid decision object", () => {
    const result = mockAnalyze("NVDA");
    expect(result.decision).toMatch(/^(BUY|SELL|WAIT)$/);
    expect(result.confidence).toBeGreaterThanOrEqual(62);
    expect(result.confidence).toBeLessThanOrEqual(92);
    expect(result.signal_strength).toBeGreaterThan(0);
    expect(result.reasoning).toBeInstanceOf(Array);
    expect(result.reasoning.length).toBeGreaterThan(0);
    expect(result.recommendation).toBeTruthy();
    expect(result.source).toBe("demo");
  });

  it("returns probabilities that sum to ~1", () => {
    const result = mockAnalyze("AAPL");
    const { up, neutral, down } = result.probabilities;
    expect(up + neutral + down).toBeCloseTo(1, 1);
    expect(up).toBeGreaterThan(0);
    expect(down).toBeGreaterThan(0);
    expect(neutral).toBeGreaterThan(0);
  });

  it("sets risk_level based on decision", () => {
    // Run multiple times to cover different random decisions
    const results = Array.from({ length: 20 }, () => mockAnalyze("TEST"));
    for (const r of results) {
      expect(["LOW", "MEDIUM", "HIGH"]).toContain(r.risk_level);
    }
  });
});

describe("mockDeepAnalysis", () => {
  it("extends mockAnalyze with reports and plan", () => {
    const result = mockDeepAnalysis("TSLA");
    expect(result.decision).toMatch(/^(BUY|SELL|WAIT)$/);
    expect(result.reports).toBeDefined();
    expect(result.reports.market).toBeTruthy();
    expect(result.reports.fundamentals).toBeTruthy();
    expect(result.reports.news).toBeTruthy();
    expect(result.investment_plan).toBeDefined();
    expect(result.investment_plan.entry).toBeGreaterThan(0);
    expect(result.investment_plan.stop_loss).toBeGreaterThan(0);
    expect(result.investment_plan.take_profit).toBeGreaterThan(0);
    expect(result.investment_plan.risk_reward).toBeTruthy();
    expect(result.ml_models).toBeInstanceOf(Array);
    expect(result.ml_models.length).toBe(3);
  });

  it("returns ML models with valid metrics", () => {
    const result = mockDeepAnalysis("NVDA");
    for (const m of result.ml_models) {
      expect(m.model).toBeTruthy();
      expect(typeof m.sharpe).toBe("number");
      expect(typeof m.return).toBe("number");
      expect(m.win_rate).toBeGreaterThan(0);
      expect(m.trades).toBeGreaterThan(0);
    }
  });
});

describe("mockNews", () => {
  it("returns items array", () => {
    const result = mockNews("NVDA");
    expect(result.items).toBeInstanceOf(Array);
    expect(result.items.length).toBeGreaterThan(0);
  });

  it("items have required fields", () => {
    const result = mockNews("AAPL");
    for (const item of result.items) {
      expect(item.title).toBeTruthy();
      expect(["bullish", "bearish", "neutral"]).toContain(item.sentiment);
      expect(typeof item.score).toBe("number");
    }
  });

  it("substitutes ticker into headlines", () => {
    const result = mockNews("GOOG");
    const hasTicker = result.items.some((i: { title: string }) => i.title.includes("GOOG"));
    expect(hasTicker).toBe(true);
  });
});

describe("mockProfile", () => {
  it("returns valid profile", () => {
    const result = mockProfile();
    expect(result.style).toBeTruthy();
    expect(result.win_rate).toBeTruthy();
    expect(result.today).toBeTruthy();
    expect(typeof result.win_streak).toBe("number");
    expect(typeof result.loss_streak).toBe("number");
    expect(result.patterns).toBeInstanceOf(Array);
  });
});

describe("mockJournal", () => {
  it("returns entries array", () => {
    const result = mockJournal();
    expect(result.entries).toBeInstanceOf(Array);
    expect(result.entries.length).toBeGreaterThan(0);
  });

  it("entries have required fields", () => {
    const result = mockJournal();
    for (const e of result.entries) {
      expect(e.ticker).toBeTruthy();
      expect(e.mode).toBeTruthy();
      expect(["BUY", "SELL", "WAIT"]).toContain(e.decision);
      expect(e.timestamp).toBeTruthy();
    }
  });
});

describe("mockBreakingSignals", () => {
  it("returns signals array", () => {
    const result = mockBreakingSignals();
    expect(result.signals).toBeInstanceOf(Array);
    expect(result.signals.length).toBeGreaterThan(0);
  });

  it("signals have required fields", () => {
    const result = mockBreakingSignals();
    for (const s of result.signals) {
      expect(s.type).toBeTruthy();
      expect(s.severity).toBeTruthy();
      expect(s.ticker).toBeTruthy();
      expect(s.message).toBeTruthy();
    }
  });
});

describe("mockWatchlistScan", () => {
  it("returns tickers array matching input", () => {
    const tickers = ["NVDA", "AAPL", "TSLA"];
    const result = mockWatchlistScan(tickers);
    expect(result.tickers).toHaveLength(3);
    expect(result.tickers.map((t: { ticker: string }) => t.ticker).sort()).toEqual([...tickers].sort());
  });

  it("each ticker has decision and probabilities", () => {
    const result = mockWatchlistScan(["QQQ"]);
    const item = result.tickers[0];
    expect(item.decision).toMatch(/^(BUY|SELL|WAIT)$/);
    expect(item.probabilities).toBeDefined();
    expect(item.confidence).toBeGreaterThan(0);
  });
});

describe("mockChartAnalysis", () => {
  it("returns decision + chart insight", () => {
    const result = mockChartAnalysis("NVDA");
    expect(result.decision).toMatch(/^(BUY|SELL|WAIT)$/);
    expect(result.chart_insight).toBeDefined();
    expect(result.chart_insight.trend).toBeTruthy();
    expect(result.chart_insight.setup).toBeTruthy();
    expect(result.chart_insight.levels).toBeTruthy();
    expect(result.chart_insight.summary).toBeTruthy();
  });
});

describe("mockDailyIntel", () => {
  it("returns full daily intel structure", () => {
    const result = mockDailyIntel();
    expect(result.date).toBeTruthy();
    expect(result.market_mood).toBeTruthy();
    expect(result.summary).toBeTruthy();
    expect(result.gainers).toBeInstanceOf(Array);
    expect(result.losers).toBeInstanceOf(Array);
    expect(result.sectors).toBeInstanceOf(Array);
    expect(result.headlines).toBeInstanceOf(Array);
    expect(result.ai_picks).toBeInstanceOf(Array);
  });

  it("gainers have positive change", () => {
    const result = mockDailyIntel();
    for (const g of result.gainers) {
      expect(g.change_pct).toBeGreaterThan(0);
      expect(g.price).toBeGreaterThan(0);
    }
  });

  it("losers have negative change", () => {
    const result = mockDailyIntel();
    for (const l of result.losers) {
      expect(l.change_pct).toBeLessThan(0);
    }
  });

  it("includes macro indicators", () => {
    const result = mockDailyIntel();
    expect(result.macro).toBeInstanceOf(Array);
    expect(result.macro!.length).toBe(6);
    for (const m of result.macro!) {
      expect(m.label).toBeTruthy();
      expect(m.value).toBeTruthy();
      expect(["up", "down", "flat"]).toContain(m.direction);
    }
  });

  it("includes fear & greed data", () => {
    const result = mockDailyIntel();
    expect(result.fear_greed).toBeDefined();
    expect(result.fear_greed!.score).toBeGreaterThanOrEqual(0);
    expect(result.fear_greed!.score).toBeLessThanOrEqual(100);
    expect(result.fear_greed!.label).toBeTruthy();
    expect(result.fear_greed!.components.length).toBeGreaterThan(0);
  });

  it("includes economic calendar", () => {
    const result = mockDailyIntel();
    expect(result.econ_calendar).toBeInstanceOf(Array);
    expect(result.econ_calendar!.length).toBeGreaterThan(0);
    for (const e of result.econ_calendar!) {
      expect(e.event).toBeTruthy();
      expect(["high", "medium", "low"]).toContain(e.impact);
    }
  });

  it("includes market breadth", () => {
    const result = mockDailyIntel();
    expect(result.breadth).toBeDefined();
    expect(result.breadth!.advancers).toBeGreaterThan(0);
    expect(result.breadth!.decliners).toBeGreaterThan(0);
    expect(result.breadth!.new_highs).toBeGreaterThanOrEqual(0);
  });

  it("includes options flow", () => {
    const result = mockDailyIntel();
    expect(result.options_flow).toBeInstanceOf(Array);
    expect(result.options_flow!.length).toBeGreaterThan(0);
    for (const f of result.options_flow!) {
      expect(f.ticker).toBeTruthy();
      expect(["call", "put"]).toContain(f.type);
      expect(f.premium).toBeTruthy();
      expect(["bullish", "bearish"]).toContain(f.sentiment);
    }
  });
});
