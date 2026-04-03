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

type Indicator = "MA20" | "MA50" | "BB" | "RSI";

// ── Technical indicator calculations ──────────────────────────────────

function calcSMA(closes: number[], period: number): (number | null)[] {
  return closes.map((_, i) => {
    if (i < period - 1) return null;
    const slice = closes.slice(i - period + 1, i + 1);
    return slice.reduce((a, b) => a + b, 0) / period;
  });
}

function calcBB(closes: number[], period: number = 20, mult: number = 2): { upper: (number | null)[]; middle: (number | null)[]; lower: (number | null)[] } {
  const middle = calcSMA(closes, period);
  const upper: (number | null)[] = [];
  const lower: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1 || middle[i] === null) {
      upper.push(null);
      lower.push(null);
      continue;
    }
    const slice = closes.slice(i - period + 1, i + 1);
    const std = Math.sqrt(slice.reduce((s, v) => s + (v - middle[i]!) ** 2, 0) / period);
    upper.push(middle[i]! + mult * std);
    lower.push(middle[i]! - mult * std);
  }
  return { upper, middle, lower };
}

function calcRSI(closes: number[], period: number = 14): (number | null)[] {
  const rsi: (number | null)[] = [null];
  let avgGain = 0, avgLoss = 0;
  for (let i = 1; i < closes.length; i++) {
    const change = closes[i] - closes[i - 1];
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? -change : 0;
    if (i <= period) {
      avgGain += gain / period;
      avgLoss += loss / period;
      rsi.push(i < period ? null : 100 - 100 / (1 + avgGain / Math.max(avgLoss, 0.0001)));
    } else {
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
      rsi.push(100 - 100 / (1 + avgGain / Math.max(avgLoss, 0.0001)));
    }
  }
  return rsi;
}

// ── Component ─────────────────────────────────────────────────────────

export function PriceChart({ ticker, t }: { ticker: string; t: Record<string, string> }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof import("lightweight-charts").createChart> | null>(null);
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>(PERIODS[2]);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<CandleData[]>([]);
  const [indicators, setIndicators] = useState<Set<Indicator>>(new Set(["MA20"]));

  const toggleIndicator = (ind: Indicator) => {
    setIndicators(prev => {
      const next = new Set(prev);
      next.has(ind) ? next.delete(ind) : next.add(ind);
      return next;
    });
  };

  // Generate mock OHLCV data
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

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    const days = period.label === "1D" ? 1 : period.label === "5D" ? 5 : period.label === "1M" ? 30 : period.label === "3M" ? 90 : 365;
    const timeout = setTimeout(() => {
      setData(generateMock(days));
      setLoading(false);
    }, 200);
    return () => clearTimeout(timeout);
  }, [ticker, period]);

  // Render chart with indicators
  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    const init = async () => {
      const { createChart, CandlestickSeries, HistogramSeries, LineSeries } = await import("lightweight-charts");

      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }

      const chart = createChart(containerRef.current!, {
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
        rightPriceScale: { borderColor: "rgba(212,175,55,0.1)" },
        timeScale: {
          borderColor: "rgba(212,175,55,0.1)",
          timeVisible: period.label === "1D" || period.label === "5D",
        },
      });

      chartRef.current = chart;
      const closes = data.map(d => d.close);

      // Candlesticks
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: "#006B3F", downColor: "#8B0000",
        borderUpColor: "#006B3F", borderDownColor: "#8B0000",
        wickUpColor: "#006B3F", wickDownColor: "#8B0000",
      });
      candleSeries.setData(data.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close })));

      // MA20
      if (indicators.has("MA20")) {
        const ma20 = calcSMA(closes, 20);
        const ma20Series = chart.addSeries(LineSeries, {
          color: "#D4AF37", lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
        });
        ma20Series.setData(data.map((d, i) => ({ time: d.time, value: ma20[i] ?? undefined })).filter(d => d.value !== undefined) as { time: string; value: number }[]);
      }

      // MA50
      if (indicators.has("MA50")) {
        const ma50 = calcSMA(closes, 50);
        const ma50Series = chart.addSeries(LineSeries, {
          color: "#C5A255", lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false,
        });
        ma50Series.setData(data.map((d, i) => ({ time: d.time, value: ma50[i] ?? undefined })).filter(d => d.value !== undefined) as { time: string; value: number }[]);
      }

      // Bollinger Bands
      if (indicators.has("BB")) {
        const bb = calcBB(closes, 20, 2);
        const bbUpper = chart.addSeries(LineSeries, {
          color: "rgba(212,175,55,0.35)", lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false,
        });
        const bbLower = chart.addSeries(LineSeries, {
          color: "rgba(212,175,55,0.35)", lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false,
        });
        bbUpper.setData(data.map((d, i) => ({ time: d.time, value: bb.upper[i] ?? undefined })).filter(d => d.value !== undefined) as { time: string; value: number }[]);
        bbLower.setData(data.map((d, i) => ({ time: d.time, value: bb.lower[i] ?? undefined })).filter(d => d.value !== undefined) as { time: string; value: number }[]);
      }

      // Volume
      if (data[0]?.volume) {
        const volumeSeries = chart.addSeries(HistogramSeries, {
          priceFormat: { type: "volume" }, priceScaleId: "volume",
        });
        chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
        volumeSeries.setData(data.map(d => ({
          time: d.time, value: d.volume ?? 0,
          color: d.close >= d.open ? "rgba(0,107,63,0.25)" : "rgba(139,0,0,0.25)",
        })));
      }

      // RSI in separate pane (below main chart)
      if (indicators.has("RSI")) {
        const rsi = calcRSI(closes, 14);
        const rsiSeries = chart.addSeries(LineSeries, {
          color: "#D4AF37", lineWidth: 1, priceScaleId: "rsi", priceLineVisible: false, lastValueVisible: false,
        });
        chart.priceScale("rsi").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
        rsiSeries.setData(data.map((d, i) => ({ time: d.time, value: rsi[i] ?? undefined })).filter(d => d.value !== undefined) as { time: string; value: number }[]);
      }

      chart.timeScale().fitContent();

      const ro = new ResizeObserver(() => {
        if (containerRef.current && chartRef.current) {
          chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
        }
      });
      ro.observe(containerRef.current!);
    };

    init();

    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [data, period.label, indicators]);

  const INDICATOR_OPTS: { key: Indicator; label: string; color: string }[] = [
    { key: "MA20", label: "MA20", color: "#D4AF37" },
    { key: "MA50", label: "MA50", color: "#C5A255" },
    { key: "BB", label: "BB", color: "rgba(212,175,55,0.5)" },
    { key: "RSI", label: "RSI", color: "#D4AF37" },
  ];

  return (
    <Mod title={<div className="flex items-center justify-between w-full">
      <span>{t.priceChart} — {ticker}</span>
      <div className="flex gap-1 overflow-x-auto">
        {PERIODS.map(p => (
          <button key={p.label} onClick={() => setPeriod(p)}
            className="px-2 py-0.5 text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.1em] transition-colors shrink-0"
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
      {/* Indicator toggles */}
      <div className="flex gap-1 mb-2 flex-wrap">
        {INDICATOR_OPTS.map(ind => (
          <button key={ind.key} onClick={() => toggleIndicator(ind.key)}
            className="px-2 py-0.5 text-[7px] font-[DM_Mono] font-medium uppercase transition-colors"
            style={{
              color: indicators.has(ind.key) ? ind.color : "#4A4D55",
              background: indicators.has(ind.key) ? `${ind.color}15` : "transparent",
              border: `1px solid ${indicators.has(ind.key) ? `${ind.color}40` : "rgba(42,42,62,0.5)"}`,
            }}>
            {ind.label}
          </button>
        ))}
      </div>
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
