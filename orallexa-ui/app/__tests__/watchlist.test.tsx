import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WatchlistGrid } from "../components/watchlist";
import type { WatchlistItem } from "../types";

const mockItems: WatchlistItem[] = [
  {
    ticker: "NVDA", price: 890.50, change_pct: 3.2, decision: "BUY",
    confidence: 82, signal_strength: 75, risk_level: "LOW",
    probabilities: { up: 0.65, neutral: 0.20, down: 0.15 },
    recommendation: "Strong buy", error: null,
  },
  {
    ticker: "TSLA", price: 175.30, change_pct: -2.1, decision: "SELL",
    confidence: 68, signal_strength: 60, risk_level: "HIGH",
    probabilities: { up: 0.20, neutral: 0.25, down: 0.55 },
    recommendation: "Sell signal", error: null,
  },
];

describe("WatchlistGrid", () => {
  it("renders nothing when items is empty", () => {
    const { container } = render(<WatchlistGrid items={[]} onSelect={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders ticker names", () => {
    render(<WatchlistGrid items={mockItems} onSelect={() => {}} />);
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("TSLA")).toBeInTheDocument();
  });

  it("renders prices", () => {
    render(<WatchlistGrid items={mockItems} onSelect={() => {}} />);
    expect(screen.getByText("$890.50")).toBeInTheDocument();
    expect(screen.getByText("$175.30")).toBeInTheDocument();
  });

  it("renders change percentages", () => {
    render(<WatchlistGrid items={mockItems} onSelect={() => {}} />);
    expect(screen.getByText("+3.20%")).toBeInTheDocument();
    expect(screen.getByText("-2.10%")).toBeInTheDocument();
  });

  it("renders decision labels", () => {
    render(<WatchlistGrid items={mockItems} onSelect={() => {}} />);
    expect(screen.getByText("BULLISH")).toBeInTheDocument();
    expect(screen.getByText("BEARISH")).toBeInTheDocument();
  });

  it("renders hero probabilities", () => {
    render(<WatchlistGrid items={mockItems} onSelect={() => {}} />);
    expect(screen.getByText("65%")).toBeInTheDocument(); // NVDA up
    expect(screen.getByText("55%")).toBeInTheDocument(); // TSLA down
  });

  it("calls onSelect with ticker on click", () => {
    const onSelect = vi.fn();
    render(<WatchlistGrid items={mockItems} onSelect={onSelect} />);
    fireEvent.click(screen.getByText("NVDA"));
    expect(onSelect).toHaveBeenCalledWith("NVDA");
  });

  it("shows confidence bar", () => {
    render(<WatchlistGrid items={mockItems} onSelect={() => {}} />);
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("68%")).toBeInTheDocument();
  });

  it("shows error when present", () => {
    const items = [{ ...mockItems[0], error: "API timeout" }];
    render(<WatchlistGrid items={items} onSelect={() => {}} />);
    expect(screen.getByText("API timeout")).toBeInTheDocument();
  });
});
