"use client";

import { useEffect, useRef, useState } from "react";
import { Mod } from "./atoms";

interface CandleData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

const PERIODS = [
  { label: "1D", period: "1d", interval: "5m" },
  { label: "5D", period: "5d", interval: "15m" },
  { label: "1M", period: "1mo", interval: "1h" },
  { label: "3M", period: "3mo", interval: "1d" },
  { label: "1Y", period: "1y", interval: "1d" },
] as const;

export function PriceChart({ ticker, t }: { ticker: string; t: Record<string, string> }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof import("lightweight-charts").createChart> | null>(null);
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>(PERIODS[2]);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<CandleData[]>([]);

  // Generate mock OHLCV data (used when backend unavailable)
  const generateMock = (days: number): CandleData[] => {
    const TICKER_PRICES: Record<string, number> = {
      NVDA: 142.5, AAPL: 218.3, TSLA: 275.8, MSFT: 432.15, GOOG: 178.9,
      AMZN: 205.4, META: 615.2, AMD: 128.6, PLTR: 98.3, COIN: 265.7,
    };
    let price = TICKER_PRICES[ticker.toUpperCase()] ?? 100;
    const result: CandleData[] = [];
    const now = new Date();
    for (let i = days; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const open = price;
      const change = (Math.random() - 0.48) * price * 0.03;
      const close = Math.round((open + change) * 100) / 100;
      const high = Math.round(Math.max(open, close) * (1 + Math.random() * 0.015) * 100) / 100;
      const low = Math.round(Math.min(open, close) * (1 - Math.random() * 0.015) * 100) / 100;
      price = close;
      result.push({
        time: d.toISOString().slice(0, 10),
        open, high, low, close,
        volume: Math.round(5000000 + Math.random() * 50000000),
      });
    }
    return result;
  };

  // Fetch data or use mock
  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    const days = period.label === "1D" ? 1 : period.label === "5D" ? 5 : period.label === "1M" ? 30 : period.label === "3M" ? 90 : 365;
    // Use mock data (backend chart endpoint doesn't exist yet)
    const timeout = setTimeout(() => {
      setData(generateMock(days));
      setLoading(false);
    }, 200);
    return () => clearTimeout(timeout);
  }, [ticker, period]);

  // Render chart
  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    let chart: ReturnType<typeof import("lightweight-charts").createChart>;

    const init = async () => {
      const { createChart, CandlestickSeries, HistogramSeries } = await import("lightweight-charts");

      // Clean up previous chart
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }

      chart = createChart(containerRef.current!, {
        width: containerRef.current!.clientWidth,
        height: 280,
        layout: {
          background: { color: "#1A1A2E" },
          textColor: "#8B8E96",
          fontFamily: "DM Mono, monospace",
          fontSize: 10,
        },
        grid: {
          vertLines: { color: "rgba(212,175,55,0.04)" },
          horzLines: { color: "rgba(212,175,55,0.04)" },
        },
        crosshair: {
          vertLine: { color: "rgba(212,175,55,0.3)", width: 1, style: 2, labelBackgroundColor: "#D4AF37" },
          horzLine: { color: "rgba(212,175,55,0.3)", width: 1, style: 2, labelBackgroundColor: "#D4AF37" },
        },
        rightPriceScale: {
          borderColor: "rgba(212,175,55,0.1)",
        },
        timeScale: {
          borderColor: "rgba(212,175,55,0.1)",
          timeVisible: period.label === "1D" || period.label === "5D",
        },
      });

      chartRef.current = chart;

      // Candlestick series
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: "#006B3F",
        downColor: "#8B0000",
        borderUpColor: "#006B3F",
        borderDownColor: "#8B0000",
        wickUpColor: "#006B3F",
        wickDownColor: "#8B0000",
      });

      candleSeries.setData(data.map(d => ({
        time: d.time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      })));

      // Volume histogram
      if (data[0]?.volume) {
        const volumeSeries = chart.addSeries(HistogramSeries, {
          priceFormat: { type: "volume" },
          priceScaleId: "volume",
        });

        chart.priceScale("volume").applyOptions({
          scaleMargins: { top: 0.85, bottom: 0 },
        });

        volumeSeries.setData(data.map(d => ({
          time: d.time,
          value: d.volume ?? 0,
          color: d.close >= d.open ? "rgba(0,107,63,0.25)" : "rgba(139,0,0,0.25)",
        })));
      }

      chart.timeScale().fitContent();

      // Resize observer
      const ro = new ResizeObserver(() => {
        if (containerRef.current && chart) {
          chart.applyOptions({ width: containerRef.current.clientWidth });
        }
      });
      ro.observe(containerRef.current!);

      return () => ro.disconnect();
    };

    init();

    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [data, period.label]);

  return (
    <Mod title={<div className="flex items-center justify-between w-full">
      <span>{t.priceChart} — {ticker}</span>
      <div className="flex gap-1">
        {PERIODS.map(p => (
          <button key={p.label} onClick={() => setPeriod(p)}
            className="px-2 py-0.5 text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.1em] transition-colors"
            style={{
              color: period.label === p.label ? "#D4AF37" : "#4A4D55",
              background: period.label === p.label ? "rgba(212,175,55,0.1)" : "transparent",
              border: `1px solid ${period.label === p.label ? "rgba(212,175,55,0.3)" : "transparent"}`,
            }}>
            {p.label}
          </button>
        ))}
      </div>
    </div>}>
      {loading ? (
        <div className="h-[280px] flex items-center justify-center">
          <span className="inline-block w-4 h-4 border-2 border-[#D4AF37] border-t-transparent rounded-full anim-spin" />
        </div>
      ) : (
        <div ref={containerRef} className="w-full" style={{ minHeight: 280 }} />
      )}
    </Mod>
  );
}
