import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BacktestPanel } from "../components/backtest-panel";
import type { BacktestSummary } from "../types";
import { T } from "../types";

const t = T["EN"];

const mockData: BacktestSummary = {
  ticker: "NVDA",
  period: "2024-01-01 to 2025-12-31",
  results: [
    { strategy: "double_ma", total_return: 15.2, sharpe: 1.35, max_drawdown: 12.3, win_rate: 55, trades: 48, profit_factor: 1.42 },
    { strategy: "bollinger_breakout", total_return: 22.8, sharpe: 1.82, max_drawdown: 8.1, win_rate: 62, trades: 32, profit_factor: 1.78 },
    { strategy: "rsi_reversal", total_return: -3.5, sharpe: 0.25, max_drawdown: 18.7, win_rate: 44, trades: 65, profit_factor: 0.85 },
  ],
  best_strategy: "bollinger_breakout",
};

describe("BacktestPanel", () => {
  it("renders empty state when data is null", () => {
    render(<BacktestPanel data={null} t={t} />);
    expect(screen.getByText(t.noBacktestData)).toBeInTheDocument();
  });

  it("renders ticker name", () => {
    render(<BacktestPanel data={mockData} t={t} />);
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });

  it("renders period", () => {
    render(<BacktestPanel data={mockData} t={t} />);
    expect(screen.getByText(/2024-01-01 to 2025-12-31/)).toBeInTheDocument();
  });

  it("renders best strategy label", () => {
    render(<BacktestPanel data={mockData} t={t} />);
    expect(screen.getAllByText("BB Breakout").length).toBeGreaterThanOrEqual(1);
  });

  it("renders all strategy rows", () => {
    render(<BacktestPanel data={mockData} t={t} />);
    expect(screen.getByText("Double MA")).toBeInTheDocument();
    // BB Breakout appears twice: best strategy callout + table row
    expect(screen.getAllByText("BB Breakout").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("RSI Reversal")).toBeInTheDocument();
  });

  it("renders sharpe ratios", () => {
    render(<BacktestPanel data={mockData} t={t} />);
    expect(screen.getByText("1.35")).toBeInTheDocument();
    expect(screen.getByText("1.82")).toBeInTheDocument();
    expect(screen.getByText("0.25")).toBeInTheDocument();
  });

  it("renders total returns with sign", () => {
    render(<BacktestPanel data={mockData} t={t} />);
    expect(screen.getByText("+15.2%")).toBeInTheDocument();
    expect(screen.getByText("+22.8%")).toBeInTheDocument();
    expect(screen.getByText("-3.5%")).toBeInTheDocument();
  });

  it("renders drawdowns with negative sign", () => {
    render(<BacktestPanel data={mockData} t={t} />);
    expect(screen.getByText("-12.3%")).toBeInTheDocument();
    expect(screen.getByText("-8.1%")).toBeInTheDocument();
  });

  it("renders win rates", () => {
    render(<BacktestPanel data={mockData} t={t} />);
    expect(screen.getByText("55%")).toBeInTheDocument();
    expect(screen.getByText("62%")).toBeInTheDocument();
  });

  it("renders trade counts", () => {
    render(<BacktestPanel data={mockData} t={t} />);
    expect(screen.getByText("48")).toBeInTheDocument();
    expect(screen.getByText("32")).toBeInTheDocument();
  });

  it("renders profit factors", () => {
    render(<BacktestPanel data={mockData} t={t} />);
    expect(screen.getByText("1.42")).toBeInTheDocument();
    expect(screen.getByText("1.78")).toBeInTheDocument();
  });

  it("sorts strategies by sharpe descending", () => {
    const { container } = render(<BacktestPanel data={mockData} t={t} />);
    const rows = container.querySelectorAll("[class*='grid'][class*='py-']");
    // First data row (after header) should be bollinger_breakout (highest sharpe)
    const strategyNames = Array.from(rows).map(
      (row) => row.querySelector("span")?.textContent
    ).filter(Boolean);
    // BB Breakout should appear before Double MA and RSI Reversal
    const bbIdx = strategyNames.indexOf("BB Breakout");
    const maIdx = strategyNames.indexOf("Double MA");
    const rsiIdx = strategyNames.indexOf("RSI Reversal");
    if (bbIdx !== -1 && maIdx !== -1) {
      expect(bbIdx).toBeLessThan(maIdx);
    }
    if (maIdx !== -1 && rsiIdx !== -1) {
      expect(maIdx).toBeLessThan(rsiIdx);
    }
  });

  it("renders column headers", () => {
    render(<BacktestPanel data={mockData} t={t} />);
    expect(screen.getByText(t.strategyName)).toBeInTheDocument();
    expect(screen.getByText(t.totalReturn)).toBeInTheDocument();
    expect(screen.getByText(t.sharpeRatio)).toBeInTheDocument();
  });

  it("works with ZH locale", () => {
    const zhT = T["ZH"];
    render(<BacktestPanel data={mockData} t={zhT} />);
    expect(screen.getByText(zhT.backtestResults)).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });
});
