import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PriceChart } from "../components/price-chart";
import { API } from "../types";

const charts = vi.hoisted(() => {
  const instances: Array<{
    series: Array<{ type: unknown; setData: ReturnType<typeof vi.fn> }>;
    addSeries: ReturnType<typeof vi.fn>;
    remove: ReturnType<typeof vi.fn>;
    applyOptions: ReturnType<typeof vi.fn>;
    fitContent: ReturnType<typeof vi.fn>;
  }> = [];
  return {
    instances,
    createChart: vi.fn(() => {
      const series: typeof instances[number]["series"] = [];
      const fitContent = vi.fn();
      const instance = {
        series,
        addSeries: vi.fn((type: unknown) => {
          const added = { type, setData: vi.fn() };
          series.push(added);
          return added;
        }),
        remove: vi.fn(),
        applyOptions: vi.fn(),
        fitContent,
        priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
        timeScale: vi.fn(() => ({ fitContent })),
      };
      instances.push(instance);
      return instance;
    }),
  };
});

vi.mock("lightweight-charts", () => ({
  createChart: charts.createChart,
  CandlestickSeries: "candles",
  HistogramSeries: "volume",
  LineSeries: "line",
}));

const fetchMock = vi.fn<typeof fetch>();
const observers: Array<{ observe: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> }> = [];
const t = {
  priceChart: "Price Chart",
  chartSource: "来源", chartUnadjusted: "未复权", chartLastBar: "最后一根K线起始时间",
  chartDelayNotice: "历史行情可能延迟；最后一根K线可能尚未收盘。",
};

// Fixed provider-contract fixture, not a claim that these are live prices.
const candles = [
  { time: 1791984600, open: 182.125, high: 183.875, low: 181.5, close: 183.25, volume: 1042300 },
  { time: 1791988200, open: 183.25, high: 184.125, low: 182.75, close: 183.875, volume: 803100 },
];

function history(ticker = "NVDA", period = "1mo", interval = "1h") {
  return {
    ticker, period, interval, source: "Yahoo Finance via yfinance",
    fetched_at: "2026-10-15T16:00:00Z", as_of: "2026-10-14T14:30:00Z", adjusted: false,
    candles: interval === "1d"
      ? candles.map((c, i) => ({ ...c, time: `2026-10-${13 + i}` }))
      : candles.map(c => ({ ...c })),
  };
}
function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
async function expectChartCount(count = 1) {
  await waitFor(() => expect(charts.createChart).toHaveBeenCalledTimes(count));
}
function candleSeries(index = charts.instances.length - 1) {
  return charts.instances[index].series.find(s => s.type === "candles")!;
}
function request(index = 0) {
  const [url, options] = fetchMock.mock.calls[index];
  return { url: new URL(String(url)), signal: options!.signal as AbortSignal, options };
}

beforeEach(() => {
  charts.instances.length = 0;
  charts.createChart.mockClear();
  observers.length = 0;
  fetchMock.mockReset();
  fetchMock.mockImplementation(() => new Promise(() => {}));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("ResizeObserver", class {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();
    constructor() { observers.push(this); }
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("PriceChart real history contract", () => {
  it("shows loading and requests the normalized ticker without a cache", () => {
    render(<PriceChart ticker=" nvda " t={t} />);
    expect(screen.getByRole("status", { name: "Loading chart" })).toBeInTheDocument();
    expect(request().url.href).toBe(`${API}/api/market-history/NVDA?period=1mo&interval=1h`);
    expect(request().options).toMatchObject({ cache: "no-store" });
    expect(request().signal.aborted).toBe(false);
    expect(charts.createChart).not.toHaveBeenCalled();
  });

  it("passes provider OHLC and intraday UTC seconds unchanged to the chart", async () => {
    fetchMock.mockResolvedValue(response(history()));
    render(<PriceChart ticker="NVDA" t={t} />);
    await expectChartCount();
    expect(candleSeries().setData).toHaveBeenCalledWith(candles.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));
    const volume = charts.instances[0].series.find(s => s.type === "volume")!;
    expect(volume.setData).toHaveBeenCalledWith(candles.map(c => expect.objectContaining({ time: c.time, value: c.volume })));
    expect(charts.instances[0].fitContent).toHaveBeenCalledOnce();
    expect(screen.getByRole("img", { name: "NVDA price chart — 1M period" })).toBeInTheDocument();
    expect(screen.getByTestId("chart-provenance")).toHaveTextContent("来源: Yahoo Finance via yfinance · 1h · 未复权");
    expect(screen.getByTestId("chart-provenance")).toHaveTextContent("最后一根K线起始时间: 2026-10-14 14:30:00 UTC");
    expect(screen.getByTestId("chart-provenance")).toHaveTextContent(t.chartDelayNotice);
    expect(screen.queryByRole("status", { name: "Loading chart" })).not.toBeInTheDocument();
  });

  it.each([
    ["1D", "1d", "5m"], ["5D", "5d", "15m"], ["1M", "1mo", "1h"],
    ["3M", "3mo", "1d"], ["1Y", "1y", "1d"],
  ])("maps %s to its API period and interval", (label, period, interval) => {
    render(<PriceChart ticker="NVDA" t={t} />);
    fireEvent.click(screen.getByRole("button", { name: label }));
    const last = request(fetchMock.mock.calls.length - 1);
    expect(last.url.searchParams.get("period")).toBe(period);
    expect(last.url.searchParams.get("interval")).toBe(interval);
    expect(screen.getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "true");
  });

  it("preserves daily exchange session dates instead of converting them into UTC days", async () => {
    fetchMock.mockResolvedValueOnce(response(history()));
    fetchMock.mockResolvedValueOnce(response(history("NVDA", "3mo", "1d")));
    render(<PriceChart ticker="NVDA" t={t} />);
    await expectChartCount();
    fireEvent.click(screen.getByRole("button", { name: "3M" }));
    await expectChartCount(2);
    expect(candleSeries().setData).toHaveBeenCalledWith([
      { time: "2026-10-13", open: 182.125, high: 183.875, low: 181.5, close: 183.25 },
      { time: "2026-10-14", open: 183.25, high: 184.125, low: 182.75, close: 183.875 },
    ]);
    expect(charts.createChart.mock.calls.at(-1)).toEqual(expect.arrayContaining([
      expect.anything(), expect.objectContaining({ timeScale: expect.objectContaining({ timeVisible: false }) }),
    ]));
  });

  it("keeps indicator controls and recalculates overlays without refetching history", async () => {
    fetchMock.mockResolvedValue(response(history()));
    render(<PriceChart ticker="NVDA" t={t} />);
    await expectChartCount();
    expect(screen.getByRole("button", { name: "MA20" })).toHaveAttribute("aria-pressed", "true");
    for (const name of ["MA50", "BB", "RSI"]) {
      const button = screen.getByRole("button", { name });
      expect(button).toHaveAttribute("aria-pressed", "false");
      const before = charts.createChart.mock.calls.length;
      fireEvent.click(button);
      expect(button).toHaveAttribute("aria-pressed", "true");
      await expectChartCount(before + 1);
      fireEvent.click(button);
      expect(button).toHaveAttribute("aria-pressed", "false");
      await expectChartCount(before + 2);
    }
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(candleSeries().setData).toHaveBeenCalledWith(candles.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));
  });
});

describe("PriceChart failures and retry", () => {
  it.each([
    ["empty", () => response({ ...history(), candles: [], as_of: null }), "No price history is available for this selection."],
    ["503", () => response({ detail: "provider unavailable" }, 503), "Price history is unavailable. No simulated candles are shown."],
    ["mismatched ticker", () => response(history("AAPL")), "Price history is unavailable. No simulated candles are shown."],
    ["invalid OHLC", () => response({ ...history(), candles: [{ ...candles[0], high: 1 }] }), "Price history is unavailable. No simulated candles are shown."],
    ["bad JSON", () => new Response("not json", { status: 200 }), "Price history is unavailable. No simulated candles are shown."],
  ])("shows %s without drawing replacement candles", async (_name, makeResponse, message) => {
    fetchMock.mockResolvedValue(makeResponse());
    render(<PriceChart ticker="NVDA" t={t} />);
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(charts.createChart).not.toHaveBeenCalled();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("retries the same selection and recovers using a new successful response", async () => {
    fetchMock.mockResolvedValueOnce(response({}, 503)).mockResolvedValueOnce(response(history()));
    render(<PriceChart ticker="NVDA" t={t} />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await expectChartCount();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(request(0).url.href).toBe(request(1).url.href);
    expect(screen.queryByText(/No simulated candles/)).not.toBeInTheDocument();
    expect(candleSeries().setData).toHaveBeenCalledWith(candles.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));
  });

  it("aborts a pending request at 15 seconds and displays an unavailable state", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation((_input, init) => new Promise((_resolve, reject) => {
      init!.signal!.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
    }));
    render(<PriceChart ticker="NVDA" t={t} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(14999); });
    expect(request().signal.aborted).toBe(false);
    expect(screen.getByRole("status", { name: "Loading chart" })).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(request().signal.aborted).toBe(true);
    expect(screen.getByText(/No simulated candles/)).toBeInTheDocument();
    expect(charts.createChart).not.toHaveBeenCalled();
  });

  it("does not request or fabricate data for a blank ticker", () => {
    render(<PriceChart ticker=" " t={t} />);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(charts.createChart).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});

describe("PriceChart request ownership and cleanup", () => {
  it.each(["ticker", "period"])("ignores a stale %s response even when its provider ignores abort", async change => {
    const old = deferred<Response>();
    const latest = deferred<Response>();
    fetchMock.mockReturnValueOnce(old.promise).mockReturnValueOnce(latest.promise);
    const { rerender } = render(<PriceChart ticker="NVDA" t={t} />);
    if (change === "ticker") rerender(<PriceChart ticker="AAPL" t={t} />);
    else fireEvent.click(screen.getByRole("button", { name: "5D" }));
    expect(request(0).signal.aborted).toBe(true);
    await act(async () => { latest.resolve(response(change === "ticker" ? history("AAPL") : history("NVDA", "5d", "15m"))); });
    await expectChartCount();
    const accepted = candleSeries().setData.mock.calls[0][0];
    await act(async () => { old.resolve(response({ ...history(), candles: candles.map(c => ({ ...c, close: c.open })) })); });
    expect(charts.createChart).toHaveBeenCalledOnce();
    expect(candleSeries().setData.mock.calls[0][0]).toEqual(accepted);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain(change === "ticker" ? "AAPL" : "5D period");
  });

  it("removes the old chart immediately while a new ticker is loading", async () => {
    fetchMock.mockResolvedValueOnce(response(history())).mockImplementationOnce(() => new Promise(() => {}));
    const { rerender } = render(<PriceChart ticker="NVDA" t={t} />);
    await expectChartCount();
    rerender(<PriceChart ticker="AAPL" t={t} />);
    expect(charts.instances[0].remove).toHaveBeenCalledOnce();
    expect(observers[0].disconnect).toHaveBeenCalledOnce();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chart-provenance")).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Loading chart" })).toBeInTheDocument();
  });

  it("aborts on unmount and ignores a late response without constructing a chart", async () => {
    const pending = deferred<Response>();
    fetchMock.mockReturnValueOnce(pending.promise);
    const { unmount } = render(<PriceChart ticker="NVDA" t={t} />);
    const signal = request().signal;
    unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => { pending.resolve(response(history())); });
    expect(charts.createChart).not.toHaveBeenCalled();
  });

  it("cleans up the owned chart and resize observer on unmount", async () => {
    fetchMock.mockResolvedValue(response(history()));
    const { unmount } = render(<PriceChart ticker="NVDA" t={t} />);
    await expectChartCount();
    unmount();
    expect(charts.instances[0].remove).toHaveBeenCalledOnce();
    expect(observers[0].disconnect).toHaveBeenCalledOnce();
  });
});
