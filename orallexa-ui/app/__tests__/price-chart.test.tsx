import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { PriceChart } from "../components/price-chart";

// Mock lightweight-charts (dynamic import)
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
const mockCreateChart = vi.fn(() => mockChart);

vi.mock("lightweight-charts", () => ({
  createChart: mockCreateChart,
  CandlestickSeries: "CandlestickSeries",
  HistogramSeries: "HistogramSeries",
  LineSeries: "LineSeries",
}));

// Mock ResizeObserver which is not available in jsdom
globalThis.ResizeObserver = class ResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
};

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

describe("PriceChart — data loading timeout and chart render path", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Reset mock call counts before each test
    mockSeries.setData.mockClear();
    mockChart.addSeries.mockClear();
    mockChart.remove.mockClear();
    mockCreateChart.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows loading spinner before 200ms elapses", () => {
    render(<PriceChart ticker="NVDA" t={t} />);
    expect(screen.getByRole("status", { name: /loading chart/i })).toBeInTheDocument();
  });

  it("hides loading spinner and shows chart container after 200ms", async () => {
    render(<PriceChart ticker="NVDA" t={t} />);
    expect(screen.getByRole("status", { name: /loading chart/i })).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(200);
    });

    expect(screen.queryByRole("status", { name: /loading chart/i })).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: /NVDA price chart/i })).toBeInTheDocument();
  });

  it("calls createChart with correct layout config after data loads", async () => {
    render(<PriceChart ticker="NVDA" t={t} />);

    await act(async () => {
      vi.advanceTimersByTime(200);
    });

    // Allow the async import().then() inside the chart init to resolve
    await act(async () => {
      await Promise.resolve();
    });

    expect(mockCreateChart).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        height: 280,
        layout: expect.objectContaining({
          background: { color: "#1A1A2E" },
          textColor: "#8B8E96",
        }),
      })
    );
  });

  it("adds CandlestickSeries to chart after data loads", async () => {
    render(<PriceChart ticker="NVDA" t={t} />);

    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(mockChart.addSeries).toHaveBeenCalledWith(
      "CandlestickSeries",
      expect.objectContaining({ upColor: "#006B3F", downColor: "#8B0000" })
    );
  });

  it("calls setData on the candlestick series after data loads", async () => {
    render(<PriceChart ticker="NVDA" t={t} />);

    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    await act(async () => {
      await Promise.resolve();
    });

    // setData is called for candlesticks (and indicator series)
    expect(mockSeries.setData).toHaveBeenCalled();
    const firstCall = mockSeries.setData.mock.calls[0][0] as { time: string; open: number; high: number; low: number; close: number }[];
    expect(Array.isArray(firstCall)).toBe(true);
    expect(firstCall.length).toBeGreaterThan(0);
    expect(firstCall[0]).toHaveProperty("time");
    expect(firstCall[0]).toHaveProperty("open");
    expect(firstCall[0]).toHaveProperty("close");
  });

  it("calls fitContent on the time scale after chart is created", async () => {
    render(<PriceChart ticker="NVDA" t={t} />);

    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(mockTimeScale.fitContent).toHaveBeenCalled();
  });

  it("adds MA20 LineSeries when MA20 indicator is active by default", async () => {
    render(<PriceChart ticker="NVDA" t={t} />);

    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    await act(async () => {
      await Promise.resolve();
    });

    // addSeries should be called at least twice: candlestick + MA20
    expect(mockChart.addSeries).toHaveBeenCalledWith(
      "LineSeries",
      expect.objectContaining({ color: "#D4AF37", lineWidth: 1 })
    );
  });

  it("re-triggers data load when period changes", async () => {
    render(<PriceChart ticker="NVDA" t={t} />);

    await act(async () => {
      vi.advanceTimersByTime(200);
    });

    // Switch to 5D period
    act(() => {
      fireEvent.click(screen.getByText("5D"));
    });

    // Should go back to loading
    expect(screen.getByRole("status", { name: /loading chart/i })).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(200);
    });

    expect(screen.queryByRole("status", { name: /loading chart/i })).not.toBeInTheDocument();
  });

  it("uses known ticker price as starting price for AAPL", async () => {
    render(<PriceChart ticker="AAPL" t={t} />);

    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    await act(async () => {
      await Promise.resolve();
    });

    // AAPL starting price is 218.3; the generated candle data should be in that ballpark
    const candleCall = mockSeries.setData.mock.calls[0][0] as { close: number }[];
    // First candle close should be within reasonable range of 218.3
    expect(candleCall[0].close).toBeGreaterThan(100);
    expect(candleCall[0].close).toBeLessThan(500);
  });

  it("uses fallback price 100 for unknown ticker", async () => {
    render(<PriceChart ticker="UNKNOWN" t={t} />);

    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    await act(async () => {
      await Promise.resolve();
    });

    const candleCall = mockSeries.setData.mock.calls[0][0] as { close: number }[];
    expect(candleCall[0].close).toBeGreaterThan(0);
  });

  it("cleans up chart on unmount", async () => {
    const { unmount } = render(<PriceChart ticker="NVDA" t={t} />);

    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    await act(async () => {
      await Promise.resolve();
    });

    unmount();
    expect(mockChart.remove).toHaveBeenCalled();
  });
});
