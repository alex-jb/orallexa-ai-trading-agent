import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SignalToast } from "../components/signal-toast";
import type { BreakingSignal } from "../types";

// Mock crypto.randomUUID
vi.stubGlobal("crypto", { randomUUID: () => "test-uuid-1" });

const mockSignal: BreakingSignal = {
  ticker: "NVDA",
  type: "breakout",
  direction: "bullish",
  severity: "high",
  message: "Breakout above resistance at $145",
  timestamp: "2026-04-03T10:00:00Z",
};

describe("SignalToast", () => {
  it("renders nothing when no signals", () => {
    const { container } = render(<SignalToast signals={[]} onSelect={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders toast for a signal", () => {
    render(<SignalToast signals={[mockSignal]} onSelect={vi.fn()} />);
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("Breakout above resistance at $145")).toBeInTheDocument();
  });

  it("shows BRK badge for breakout type", () => {
    render(<SignalToast signals={[mockSignal]} onSelect={vi.fn()} />);
    expect(screen.getByText("BRK")).toBeInTheDocument();
  });

  it("shows VOL badge for volume_spike type", () => {
    const volSignal: BreakingSignal = { ...mockSignal, type: "volume_spike", timestamp: "vol-ts" };
    render(<SignalToast signals={[volSignal]} onSelect={vi.fn()} />);
    expect(screen.getByText("VOL")).toBeInTheDocument();
  });

  it("shows SENT badge for sentiment_shift type", () => {
    const sentSignal: BreakingSignal = { ...mockSignal, type: "sentiment_shift", timestamp: "sent-ts" };
    render(<SignalToast signals={[sentSignal]} onSelect={vi.fn()} />);
    expect(screen.getByText("SENT")).toBeInTheDocument();
  });

  it("calls onSelect with ticker when clicked", () => {
    const onSelect = vi.fn();
    render(<SignalToast signals={[mockSignal]} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("alert"));
    expect(onSelect).toHaveBeenCalledWith("NVDA");
  });

  it("calls onSelect on Enter keypress", () => {
    const onSelect = vi.fn();
    render(<SignalToast signals={[mockSignal]} onSelect={onSelect} />);
    fireEvent.keyDown(screen.getByRole("alert"), { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("NVDA");
  });

  it("has dismiss button with accessible label", () => {
    render(<SignalToast signals={[mockSignal]} onSelect={vi.fn()} />);
    expect(screen.getByLabelText("Dismiss signal alert")).toBeInTheDocument();
  });

  it("has accessible region wrapper", () => {
    render(<SignalToast signals={[mockSignal]} onSelect={vi.fn()} />);
    expect(screen.getByRole("region", { name: /signal notifications/i })).toBeInTheDocument();
  });
});
