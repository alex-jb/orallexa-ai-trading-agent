import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PriceChart } from "../components/price-chart";

// Mock lightweight-charts (dynamic import)
vi.mock("lightweight-charts", () => {
  const mockSeries = { setData: vi.fn() };
  const mockPriceScale = { applyOptions: vi.fn() };
  const mockTimeScale = { fitContent: vi.fn() };
  const mockChart = {
    addSeries: vi.fn(() => mockSeries),
    priceScale: vi.fn(() => mockPriceScale),
    timeScale: vi.fn(() => mockTimeScale),
    applyOptions: vi.fn(),
    remove: vi.fn(),
  };
  return {
    createChart: vi.fn(() => mockChart),
    CandlestickSeries: "CandlestickSeries",
    HistogramSeries: "HistogramSeries",
    LineSeries: "LineSeries",
  };
});

const t = { priceChart: "Price Chart" };

describe("PriceChart", () => {
  it("renders with ticker and period buttons", () => {
    render(<PriceChart ticker="NVDA" t={t} />);
    expect(screen.getByText(/Price Chart — NVDA/)).toBeInTheDocument();
    expect(screen.getByText("1D")).toBeInTheDocument();
    expect(screen.getByText("5D")).toBeInTheDocument();
    expect(screen.getByText("1M")).toBeInTheDocument();
    expect(screen.getByText("3M")).toBeInTheDocument();
    expect(screen.getByText("1Y")).toBeInTheDocument();
  });

  it("renders indicator toggle buttons", () => {
    render(<PriceChart ticker="AAPL" t={t} />);
    expect(screen.getByText("MA20")).toBeInTheDocument();
    expect(screen.getByText("MA50")).toBeInTheDocument();
    expect(screen.getByText("BB")).toBeInTheDocument();
    expect(screen.getByText("RSI")).toBeInTheDocument();
  });

  it("shows loading spinner initially", () => {
    render(<PriceChart ticker="TSLA" t={t} />);
    expect(screen.getByRole("status", { name: /loading chart/i })).toBeInTheDocument();
  });

  it("toggles indicator active state on click", () => {
    render(<PriceChart ticker="NVDA" t={t} />);
    const ma50Btn = screen.getByText("MA50");
    expect(ma50Btn).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(ma50Btn);
    expect(ma50Btn).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(ma50Btn);
    expect(ma50Btn).toHaveAttribute("aria-pressed", "false");
  });

  it("switches period on button click", () => {
    render(<PriceChart ticker="NVDA" t={t} />);
    const btn5d = screen.getByText("5D");
    fireEvent.click(btn5d);
    expect(btn5d).toHaveAttribute("aria-pressed", "true");
    const btn1m = screen.getByText("1M");
    expect(btn1m).toHaveAttribute("aria-pressed", "false");
  });

  it("MA20 is active by default", () => {
    render(<PriceChart ticker="NVDA" t={t} />);
    expect(screen.getByText("MA20")).toHaveAttribute("aria-pressed", "true");
  });
});
