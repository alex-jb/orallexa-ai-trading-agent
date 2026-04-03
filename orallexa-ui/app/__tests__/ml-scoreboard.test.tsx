import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MLScoreboard } from "../components/ml-scoreboard";
import type { MLModel } from "../types";

const mockModels: MLModel[] = [
  { model: "Random Forest", sharpe: 1.42, return: 15.3, win_rate: 68, trades: 42 },
  { model: "MACD Cross", sharpe: 0.85, return: -3.2, win_rate: 52, trades: 30 },
  { model: "Buy & Hold", sharpe: 0.60, return: 8.1, win_rate: 55, trades: 1 },
];

describe("MLScoreboard", () => {
  it("renders nothing when models is empty", () => {
    const { container } = render(<MLScoreboard models={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders model names", () => {
    render(<MLScoreboard models={mockModels} />);
    expect(screen.getByText("Random Forest")).toBeInTheDocument();
    expect(screen.getByText("MACD Cross")).toBeInTheDocument();
    expect(screen.getByText("Buy & Hold")).toBeInTheDocument();
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
    const rfRow = screen.getByText("Random Forest").closest("div[class*='grid']");
    expect(rfRow?.className).toContain("bg-[#D4AF37]/5");
  });
});
