import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarketStrip } from "../components/market-strip";
import type { Decision, MarketSummary } from "../types";

const mockSummary: MarketSummary = { close: 145.50, change_pct: 2.34, rsi: 55 };
const mockDecision: Decision = {
  decision: "BUY", confidence: 78, risk_level: "LOW",
  signal_strength: 72, recommendation: "Buy the dip",
  reasoning: ["Bull: Strong momentum"],
};

describe("MarketStrip", () => {
  it("renders nothing when all props are null", () => {
    const { container } = render(
      <MarketStrip summary={null} decision={null} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders price from summary", () => {
    render(<MarketStrip summary={mockSummary} decision={null} />);
    expect(screen.getByText("$145.50")).toBeInTheDocument();
  });

  it("renders change percentage", () => {
    render(<MarketStrip summary={mockSummary} decision={null} />);
    expect(screen.getByText("+2.34%")).toBeInTheDocument();
  });

  it("renders RSI", () => {
    render(<MarketStrip summary={mockSummary} decision={null} />);
    expect(screen.getByText("55.0")).toBeInTheDocument();
  });

  it("renders signal and confidence from decision", () => {
    render(<MarketStrip summary={null} decision={mockDecision} />);
    expect(screen.getByText("72/100")).toBeInTheDocument();
    expect(screen.getByText("78%")).toBeInTheDocument();
  });

  it("renders dashes when no data", () => {
    render(<MarketStrip summary={{}} decision={null} />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it("prefers livePrice over summary", () => {
    const livePrice = { price: 150.00, change_pct: 3.5, high: 152, low: 148, timestamp: "2026-04-02T14:30:00Z" };
    render(<MarketStrip summary={mockSummary} decision={null} livePrice={livePrice} />);
    expect(screen.getByText("$150.00")).toBeInTheDocument();
    expect(screen.getByText("+3.50%")).toBeInTheDocument();
  });

  it("shows H/L when livePrice has high/low", () => {
    const livePrice = { price: 150, change_pct: 1, high: 155, low: 145, timestamp: "2026-04-02T14:30:00Z" };
    render(<MarketStrip summary={null} decision={null} livePrice={livePrice} />);
    expect(screen.getByText("155/145")).toBeInTheDocument();
  });

  it("shows live indicator dot when timestamp present", () => {
    const livePrice = { price: 150, change_pct: 1, high: 155, low: 145, timestamp: "2026-04-02T14:30:00Z" };
    const { container } = render(<MarketStrip summary={null} decision={null} livePrice={livePrice} />);
    const dot = container.querySelector("[title='Polling']") || container.querySelector("[title='WebSocket Live']");
    expect(dot).toBeInTheDocument();
  });
});
