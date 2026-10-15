import { describe, expect, it } from "vitest";
import { parseMarketHistory } from "../market-history";

function fixture() {
  return {
    ticker: "NVDA", period: "1mo", interval: "1h", source: "Yahoo Finance via yfinance",
    fetched_at: "2026-10-15T16:00:00Z", as_of: "2026-10-14T14:30:00Z", adjusted: false,
    candles: [
      { time: 1791984600, open: 182.125, high: 183.875, low: 181.5, close: 183.25, volume: 1042300 },
      { time: 1791988200, open: 183.25, high: 184.125, low: 182.75, close: 183.875, volume: 803100 },
    ],
  };
}
function parse(payload: unknown) { return parseMarketHistory(payload, "NVDA", "1mo", "1h"); }

describe("market history validation boundary", () => {
  it("retains raw numeric OHLC, volume, and UTC seconds without transformation", () => {
    const value = fixture();
    expect(parse(value)).toEqual(value);
  });

  it("accepts an explicitly empty result only with no last-bar timestamp", () => {
    expect(parse({ ...fixture(), candles: [], as_of: null }).candles).toEqual([]);
    expect(() => parse({ ...fixture(), candles: [] })).toThrow();
    expect(() => parse({ ...fixture(), as_of: null })).toThrow();
  });

  it.each([
    ["ticker", { ticker: "AAPL" }], ["period", { period: "1y" }], ["interval", { interval: "1d" }],
    ["adjusted values", { adjusted: true }], ["blank source", { source: " " }],
    ["invalid fetch date", { fetched_at: "not a date" }], ["invalid last-bar date", { as_of: "not a date" }],
    ["non-array candles", { candles: {} }],
  ])("rejects %s instead of rendering data from a different contract", (_name, override) => {
    expect(() => parse({ ...fixture(), ...override })).toThrow();
  });

  it.each([
    ["non-finite price", { close: Infinity }], ["string price", { open: "182.125" }],
    ["nonpositive price", { low: 0 }], ["high below open", { high: 182 }],
    ["low above close", { low: 184 }], ["negative volume", { volume: -1 }],
    ["missing volume", { volume: undefined }], ["fractional UTC seconds", { time: 1791984600.5 }],
    ["date string for intraday", { time: "2026-10-14" }],
  ])("rejects a candle with %s", (_name, override) => {
    expect(() => parse({ ...fixture(), candles: [{ ...fixture().candles[0], ...override }] })).toThrow();
  });

  it("rejects duplicate or descending bar keys", () => {
    const value = fixture();
    expect(() => parse({ ...value, candles: [...value.candles].reverse() })).toThrow();
    expect(() => parse({ ...value, candles: [value.candles[0], value.candles[0]] })).toThrow();
  });

  it("preserves valid daily session dates without a UTC conversion", () => {
    const value = { ...fixture(), period: "3mo", interval: "1d", candles: [
      { ...fixture().candles[0], time: "2026-10-13" },
      { ...fixture().candles[1], time: "2026-10-14" },
    ] };
    expect(parseMarketHistory(value, "NVDA", "3mo", "1d").candles.map(c => c.time)).toEqual(["2026-10-13", "2026-10-14"]);
    for (const time of ["2026-02-30", "2026-13-01", "2026-10-13T00:00:00Z", 1791984600]) {
      expect(() => parseMarketHistory({ ...value, candles: [{ ...value.candles[0], time }] }, "NVDA", "3mo", "1d")).toThrow();
    }
  });
});
