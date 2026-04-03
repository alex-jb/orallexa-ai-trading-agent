import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BreakingBanner } from "../components/breaking";
import type { BreakingSignal } from "../types";

const baseSignal: BreakingSignal = {
  type: "decision_flip",
  severity: "critical",
  ticker: "NVDA",
  timestamp: "2026-04-02T14:30:00Z",
  message: "NVDA flipped from BUY to SELL",
  prev_decision: "BUY",
  new_decision: "SELL",
};

describe("BreakingBanner", () => {
  it("renders nothing when signals is empty", () => {
    const { container } = render(<BreakingBanner signals={[]} zh={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders signal message", () => {
    render(<BreakingBanner signals={[baseSignal]} zh={false} />);
    expect(screen.getByText("NVDA flipped from BUY to SELL")).toBeInTheDocument();
  });

  it("shows Breaking label", () => {
    render(<BreakingBanner signals={[baseSignal]} zh={false} />);
    expect(screen.getByText("Breaking")).toBeInTheDocument();
  });

  it("shows timestamp time portion", () => {
    render(<BreakingBanner signals={[baseSignal]} zh={false} />);
    expect(screen.getByText("14:30")).toBeInTheDocument();
  });

  it("shows English explanation for decision_flip", () => {
    render(<BreakingBanner signals={[baseSignal]} zh={false} />);
    expect(screen.getByText(/Signal flipped from BUY to SELL/)).toBeInTheDocument();
  });

  it("shows Chinese explanation for decision_flip when zh=true", () => {
    render(<BreakingBanner signals={[baseSignal]} zh={true} />);
    expect(screen.getByText(/从「买入」变成「卖出」/)).toBeInTheDocument();
  });

  it("renders multiple signals", () => {
    const signals: BreakingSignal[] = [
      baseSignal,
      { ...baseSignal, type: "probability_shift", severity: "high", message: "Upside probability surged", direction: "bullish" },
    ];
    render(<BreakingBanner signals={signals} zh={false} />);
    expect(screen.getByText("NVDA flipped from BUY to SELL")).toBeInTheDocument();
    expect(screen.getByText("Upside probability surged")).toBeInTheDocument();
  });

  it("renders probability_shift bullish explanation", () => {
    const sig: BreakingSignal = { ...baseSignal, type: "probability_shift", direction: "bullish", message: "Prob up" };
    render(<BreakingBanner signals={[sig]} zh={false} />);
    expect(screen.getByText(/leaning bullish/)).toBeInTheDocument();
  });

  it("renders probability_shift bearish explanation", () => {
    const sig: BreakingSignal = { ...baseSignal, type: "probability_shift", direction: "bearish", message: "Prob down" };
    render(<BreakingBanner signals={[sig]} zh={false} />);
    expect(screen.getByText(/leaning bearish/)).toBeInTheDocument();
  });

  it("renders confidence_shift positive explanation", () => {
    const sig: BreakingSignal = { ...baseSignal, type: "confidence_shift", shift_pct: 15, message: "Conf up" };
    render(<BreakingBanner signals={[sig]} zh={false} />);
    expect(screen.getByText(/Confidence surged/)).toBeInTheDocument();
  });

  it("renders confidence_shift negative explanation", () => {
    const sig: BreakingSignal = { ...baseSignal, type: "confidence_shift", shift_pct: -10, message: "Conf down" };
    render(<BreakingBanner signals={[sig]} zh={false} />);
    expect(screen.getByText(/Confidence dropped/)).toBeInTheDocument();
  });
});
