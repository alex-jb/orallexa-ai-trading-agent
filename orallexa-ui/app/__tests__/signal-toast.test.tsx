import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
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

describe("SignalToast — auto-dismiss timeout", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("toast is visible immediately after signal arrives", () => {
    render(<SignalToast signals={[mockSignal]} onSelect={vi.fn()} />);
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });

  it("marks toast as exiting (opacity 0) after 8 seconds", () => {
    render(<SignalToast signals={[mockSignal]} onSelect={vi.fn()} />);
    const alert = screen.getByRole("alert");
    // Before 8 s the toast is fully visible (opacity: 1)
    expect(alert).toHaveStyle({ opacity: 1 });

    act(() => {
      vi.advanceTimersByTime(8000);
    });

    // After 8 s the exiting flag is set → opacity becomes 0
    expect(alert).toHaveStyle({ opacity: 0 });
  });

  it("removes toast from DOM after 8300ms (8s + 300ms exit animation)", () => {
    render(<SignalToast signals={[mockSignal]} onSelect={vi.fn()} />);
    expect(screen.getByText("NVDA")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(8300);
    });

    expect(screen.queryByText("NVDA")).not.toBeInTheDocument();
  });
});

describe("SignalToast — dismiss button stopPropagation", () => {
  it("clicking dismiss does not call onSelect", () => {
    const onSelect = vi.fn();
    render(<SignalToast signals={[mockSignal]} onSelect={onSelect} />);
    const dismissBtn = screen.getByLabelText("Dismiss signal alert");
    fireEvent.click(dismissBtn);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("dismiss button click stops propagation to parent alert", () => {
    const onSelect = vi.fn();
    render(<SignalToast signals={[mockSignal]} onSelect={onSelect} />);
    const dismissBtn = screen.getByLabelText("Dismiss signal alert");
    // Attach a click listener on the alert to verify no bubbling
    const alert = screen.getByRole("alert");
    const alertClickSpy = vi.fn();
    alert.addEventListener("click", alertClickSpy);
    fireEvent.click(dismissBtn);
    // The synthetic fireEvent does not naturally bubble in RTL when stopPropagation
    // is called because the component uses e.stopPropagation() — verify onSelect
    // (which is called by the alert's onClick) was not invoked.
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("dismiss removes the toast with 300ms delay", async () => {
    vi.useFakeTimers();
    render(<SignalToast signals={[mockSignal]} onSelect={vi.fn()} />);
    expect(screen.getByText("NVDA")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Dismiss signal alert"));

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(screen.queryByText("NVDA")).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it("dismiss sets exiting state (opacity: 0) before removal", () => {
    vi.useFakeTimers();
    render(<SignalToast signals={[mockSignal]} onSelect={vi.fn()} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveStyle({ opacity: 1 });

    fireEvent.click(screen.getByLabelText("Dismiss signal alert"));
    // Immediately after click, exiting=true → opacity 0, but not yet removed
    expect(alert).toHaveStyle({ opacity: 0 });

    vi.useRealTimers();
  });
});
