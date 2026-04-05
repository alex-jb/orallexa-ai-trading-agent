import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MLScoreboard } from "../components/ml-scoreboard";
import type { MLModel } from "../types";

const mockModels: MLModel[] = [
  { model: "Random Forest", sharpe: 1.42, return: 15.3, win_rate: 68, trades: 42, status: "ok" },
  { model: "MACD Cross", sharpe: 0.85, return: -3.2, win_rate: 52, trades: 30, status: "ok" },
  { model: "Buy & Hold", sharpe: 0.60, return: 8.1, win_rate: 55, trades: 1, status: "ok" },
];

describe("MLScoreboard", () => {
  it("renders nothing when models is empty", () => {
    const { container } = render(<MLScoreboard models={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders model names", () => {
    render(<MLScoreboard models={mockModels} />);
    // Best model appears in row + "Best:" footer, so use getAllByText
    expect(screen.getAllByText(/Random Forest/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/MACD Cross/)).toBeInTheDocument();
  });

  it("renders sharpe ratios", () => {
    render(<MLScoreboard models={mockModels} />);
    expect(screen.getByText("1.42")).toBeInTheDocument();
    expect(screen.getByText("0.85")).toBeInTheDocument();
  });

  it("renders return percentages", () => {
    render(<MLScoreboard models={mockModels} />);
    expect(screen.getByText("+15.3%")).toBeInTheDocument();
    expect(screen.getByText("-3.2%")).toBeInTheDocument();
  });

  it("renders win rates", () => {
    render(<MLScoreboard models={mockModels} />);
    expect(screen.getByText("68%")).toBeInTheDocument();
    expect(screen.getByText("52%")).toBeInTheDocument();
  });

  it("renders column headers", () => {
    render(<MLScoreboard models={mockModels} />);
    expect(screen.getByText("Model")).toBeInTheDocument();
    expect(screen.getByText("Sharpe")).toBeInTheDocument();
    expect(screen.getByText("Return")).toBeInTheDocument();
    expect(screen.getByText("Win%")).toBeInTheDocument();
  });

  it("highlights best sharpe model (not Buy & Hold)", () => {
    render(<MLScoreboard models={mockModels} />);
    // Find the row element (first match is the model row, second is footer)
    const matches = screen.getAllByText(/Random Forest/);
    const rfRow = matches[0].closest("div[class*='grid']");
    expect(rfRow?.className).toContain("bg-[#D4AF37]/5");
  });
});
