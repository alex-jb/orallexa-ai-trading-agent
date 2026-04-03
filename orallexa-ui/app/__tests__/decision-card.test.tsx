import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DecisionCard } from "../components/decision-card";
import type { Decision, InvestmentPlan } from "../types";
import { T } from "../types";

const t = T.EN;

const mockDecision: Decision = {
  decision: "BUY", confidence: 78, risk_level: "LOW",
  signal_strength: 72, recommendation: "Strong momentum detected — consider entry near support",
  reasoning: [
    "Bull: RSI bouncing from oversold",
    "Bear: Volume declining on rally",
    "Judge: Lean bullish with tight stop",
    "MACD crossed above signal line",
  ],
  probabilities: { up: 0.65, neutral: 0.20, down: 0.15 },
};

const mockPlan: InvestmentPlan = {
  entry: 145.50, stop_loss: 140.00, take_profit: 160.00,
  position_pct: 5, risk_reward: "1:2.6",
  key_risks: ["Earnings next week", "Sector rotation"],
  plan_summary: "Scale in at support with tight risk",
};

describe("DecisionCard — empty state", () => {
  it("shows STANDBY when no decision", () => {
    render(<DecisionCard d={null} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText("STANDBY")).toBeInTheDocument();
  });

  it("shows engine decision heading", () => {
    render(<DecisionCard d={null} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText("Engine Decision")).toBeInTheDocument();
  });

  it("shows dashes for signal/confidence/risk", () => {
    render(<DecisionCard d={null} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBe(3);
  });
});

describe("DecisionCard — with decision", () => {
  it("shows BULLISH for BUY decision", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText("BULLISH")).toBeInTheDocument();
  });

  it("shows recommendation text", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText(/Strong momentum detected/)).toBeInTheDocument();
  });

  it("shows signal strength label", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText("Strong")).toBeInTheDocument();
    expect(screen.getByText("72/100")).toBeInTheDocument();
  });

  it("shows confidence label", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("78%")).toBeInTheDocument();
  });

  it("shows risk label", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText("Low")).toBeInTheDocument();
  });

  it("shows probability bar with percentages", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText("Up 65%")).toBeInTheDocument();
    expect(screen.getByText("Neutral 20%")).toBeInTheDocument();
    expect(screen.getByText("Down 15%")).toBeInTheDocument();
  });

  it("shows hero probability number", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText("65%")).toBeInTheDocument();
  });

  it("shows bull/bear debate", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText("Bull Case")).toBeInTheDocument();
    expect(screen.getByText("Bear Case")).toBeInTheDocument();
    expect(screen.getByText("RSI bouncing from oversold")).toBeInTheDocument();
    expect(screen.getByText("Volume declining on rally")).toBeInTheDocument();
  });

  it("shows judge verdict", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText("Judge Verdict")).toBeInTheDocument();
    expect(screen.getByText("Lean bullish with tight stop")).toBeInTheDocument();
  });

  it("has toggleable technical details", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.queryByText("MACD crossed above signal line")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/Technical Details/));
    expect(screen.getByText("MACD crossed above signal line")).toBeInTheDocument();
  });

  it("shows asset and strategy info", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText(/NVDA/)).toBeInTheDocument();
    expect(screen.getByText(/scalp/)).toBeInTheDocument();
  });
});

describe("DecisionCard — with investment plan", () => {
  it("shows entry/stop/target/size/R:R", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={mockPlan} t={t} zh={false} />);
    expect(screen.getByText("$145.50")).toBeInTheDocument();
    expect(screen.getByText("$140.00")).toBeInTheDocument();
    expect(screen.getByText("$160.00")).toBeInTheDocument();
    expect(screen.getByText("5%")).toBeInTheDocument();
    expect(screen.getByText("1:2.6")).toBeInTheDocument();
  });

  it("shows key risks", () => {
    render(<DecisionCard d={mockDecision} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={mockPlan} t={t} zh={false} />);
    expect(screen.getByText(/Earnings next week/)).toBeInTheDocument();
    expect(screen.getByText(/Sector rotation/)).toBeInTheDocument();
  });
});

describe("DecisionCard — SELL decision", () => {
  it("shows BEARISH and downside probability", () => {
    const sellDec: Decision = { ...mockDecision, decision: "SELL", probabilities: { up: 0.15, neutral: 0.20, down: 0.65 } };
    render(<DecisionCard d={sellDec} asset="NVDA" strategy="scalp" horizon="5M" news={[]} risk={null} investmentPlan={null} t={t} zh={false} />);
    expect(screen.getByText("BEARISH")).toBeInTheDocument();
    expect(screen.getByText(/Downside/)).toBeInTheDocument();
  });
});
