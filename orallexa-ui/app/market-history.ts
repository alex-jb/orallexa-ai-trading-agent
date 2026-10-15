import type { UTCTimestamp } from "lightweight-charts";

export interface MarketCandle {
  time: string | UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketHistory {
  ticker: string;
  period: string;
  interval: string;
  source: string;
  as_of: string | null;
  fetched_at: string;
  adjusted: false;
  candles: MarketCandle[];
}

// Reject malformed/mismatched responses instead of drawing plausible substitutes.
export function parseMarketHistory(
  payload: unknown, ticker: string, period: string, interval: string,
): MarketHistory {
  const p = payload as Partial<MarketHistory> | null;
  if (!p || p.ticker !== ticker || p.period !== period || p.interval !== interval
    || typeof p.source !== "string" || !p.source.trim() || p.adjusted !== false
    || typeof p.fetched_at !== "string" || !Number.isFinite(Date.parse(p.fetched_at))
    || !(p.as_of === null || (typeof p.as_of === "string" && Number.isFinite(Date.parse(p.as_of))))
    || !Array.isArray(p.candles)) throw new Error("Invalid market history");

  let previous: string | number | null = null;
  for (const c of p.candles) {
    if (!c || ![c.open, c.high, c.low, c.close, c.volume].every(v => typeof v === "number" && Number.isFinite(v))
      || Math.min(c.open, c.high, c.low, c.close) <= 0 || c.volume < 0
      || c.high < Math.max(c.open, c.close, c.low) || c.low > Math.min(c.open, c.close, c.high)) {
      throw new Error("Invalid market candle");
    }
    const validTime = interval === "1d"
      ? typeof c.time === "string" && /^\d{4}-\d{2}-\d{2}$/.test(c.time)
        && new Date(c.time).toISOString().slice(0, 10) === c.time
      : typeof c.time === "number" && Number.isSafeInteger(c.time) && c.time > 0;
    if (!validTime || (previous !== null && c.time <= previous)) throw new Error("Invalid candle time");
    previous = c.time;
  }
  if ((p.candles.length > 0) !== (p.as_of !== null)) throw new Error("Missing last bar time");
  return p as MarketHistory;
}
