"use client";

import { useMemo, useState } from "react";
import { Mod, GoldRule } from "./atoms";
import type { BacktestSummary } from "../types";

/* ── Strategy display names ──────────────────────────────────────────── */
const STRATEGY_LABELS: Record<string, string> = {
  double_ma: "Double MA",
  macd_crossover: "MACD Cross",
  bollinger_breakout: "BB Breakout",
  rsi_reversal: "RSI Reversal",
  trend_momentum: "Trend + Mom",
  alpha_combo: "Alpha Combo",
  dual_thrust: "Dual Thrust",
  ensemble_vote: "Ensemble Vote",
  regime_ensemble: "Regime Ensemble",
};

const PERIOD_OPTIONS = [
  { value: "1y", labelKey: "bt1y" },
  { value: "2y", labelKey: "bt2y" },
  { value: "5y", labelKey: "bt5y" },
  { value: "max", labelKey: "btMax" },
] as const;

/* ── Metric color helpers ────────────────────────────────────────────── */
function returnColor(v: number): string {
  if (v >= 20) return "#006B3F";
  if (v >= 10) return "#4A9E6E";
  if (v >= 0) return "#8B8E96";
  return "#8B0000";
}

function sharpeColor(v: number): string {
  if (v >= 1.5) return "#006B3F";
  if (v >= 1.0) return "#4A9E6E";
  if (v >= 0.5) return "#D4AF37";
  return "#8B0000";
}

function drawdownColor(v: number): string {
  if (v <= 8) return "#006B3F";
  if (v <= 15) return "#D4AF37";
  return "#8B0000";
}

function winRateColor(v: number): string {
  if (v >= 60) return "#006B3F";
  if (v >= 50) return "#D4AF37";
  return "#8B0000";
}

function pfColor(v: number): string {
  if (v >= 1.5) return "#006B3F";
  if (v >= 1.0) return "#D4AF37";
  return "#8B0000";
}

/* ── Component ───────────────────────────────────────────────────────── */
export function BacktestPanel({
  data,
  t,
  loading,
  onPeriodChange,
}: {
  data: BacktestSummary | null;
  t: Record<string, string>;
  loading?: boolean;
  onPeriodChange?: (period: string) => void;
}) {
  const [selectedPeriod, setSelectedPeriod] = useState("2y");

  const handlePeriodChange = (period: string) => {
    setSelectedPeriod(period);
    onPeriodChange?.(period);
  };

  const sorted = useMemo(() => {
    if (!data) return [];
    return [...data.results].sort((a, b) => b.sharpe - a.sharpe);
  }, [data]);

  const maxReturn = useMemo(() => {
    if (!sorted.length) return 1;
    return Math.max(...sorted.map((r) => Math.abs(r.total_return)), 1);
  }, [sorted]);

  /* ── Period selector (always shown) ──────────────────────────────── */
  const periodSelector = (
    <div className="flex items-center gap-1 mb-3">
      <span
        className="text-[8px] font-[Josefin_Sans] uppercase tracking-[0.12em] mr-1"
        style={{ color: "#8B8E96" }}
      >
        {t.backtestPeriod}
      </span>
      {PERIOD_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => handlePeriodChange(opt.value)}
          className="px-2 py-0.5 text-[9px] font-[DM_Mono] font-medium transition-colors"
          style={{
            color: selectedPeriod === opt.value ? "#0A0A0F" : "#8B8E96",
            background:
              selectedPeriod === opt.value
                ? "linear-gradient(135deg, #D4AF37, #FFD700)"
                : "transparent",
            border:
              selectedPeriod === opt.value
                ? "1px solid #D4AF37"
                : "1px solid rgba(212,175,55,0.15)",
          }}
        >
          {t[opt.labelKey] ?? opt.value.toUpperCase()}
        </button>
      ))}
    </div>
  );

  if (!data) {
    return (
      <Mod title={t.backtestResults}>
        {periodSelector}
        {loading ? (
          <div className="flex items-center justify-center py-6 gap-2">
            <div className="w-3 h-3 border border-[#D4AF37] border-t-transparent rounded-full anim-spin" />
            <span className="text-[10px] font-[Josefin_Sans] uppercase tracking-[0.12em]" style={{ color: "#C5A255" }}>
              Running backtest...
            </span>
          </div>
        ) : (
          <p
            className="text-[11px] font-[Lato] py-4 text-center"
            style={{ color: "#8B8E96" }}
          >
            {t.noBacktestData}
          </p>
        )}
      </Mod>
    );
  }

  return (
    <Mod title={t.backtestResults}>
      {periodSelector}

      {/* Ticker + Period header */}
      <div className="flex items-center justify-between mb-2">
        <span
          className="text-[13px] font-[DM_Mono] font-bold"
          style={{ color: "#F5E6CA" }}
        >
          {data.ticker}
        </span>
        <span
          className="text-[9px] font-[Josefin_Sans] uppercase tracking-[0.14em]"
          style={{ color: "#8B8E96" }}
        >
          {data.period}
        </span>
      </div>

      {/* Best strategy callout */}
      <div
        className="flex items-center gap-2 px-3 py-2 mb-3"
        style={{
          background: "rgba(212,175,55,0.06)",
          border: "1px solid rgba(212,175,55,0.2)",
        }}
      >
        <div
          className="w-1.5 h-1.5 rotate-45"
          style={{ background: "#D4AF37" }}
        />
        <span
          className="text-[9px] font-[Josefin_Sans] uppercase tracking-[0.16em]"
          style={{ color: "#C5A255" }}
        >
          {t.bestStrategy}
        </span>
        <span
          className="text-[13px] font-[DM_Mono] font-medium ml-auto"
          style={{
            background:
              "linear-gradient(135deg, #D4AF37, #FFD700, #C5A255)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          {STRATEGY_LABELS[data.best_strategy] ?? data.best_strategy}
        </span>
      </div>

      <GoldRule strength={15} />

      {/* Loading overlay */}
      {loading && (
        <div className="flex items-center justify-center py-2 gap-2">
          <div className="w-3 h-3 border border-[#D4AF37] border-t-transparent rounded-full anim-spin" />
          <span className="text-[9px] font-[Josefin_Sans] uppercase tracking-[0.12em]" style={{ color: "#C5A255" }}>
            Updating...
          </span>
        </div>
      )}

      {/* Table header */}
      <div
        className="grid gap-1 px-1 py-2"
        style={{
          gridTemplateColumns: "minmax(90px, 1.2fr) 1fr 0.7fr 0.7fr 0.7fr 0.5fr 0.7fr",
          borderBottom: "1px solid rgba(212,175,55,0.12)",
        }}
      >
        {[
          t.strategyName,
          t.totalReturn,
          t.sharpeRatio,
          t.maxDrawdown,
          t.winRateCol,
          t.tradesCol,
          t.profitFactor,
        ].map((label) => (
          <span
            key={label}
            className="text-[8px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.12em] text-right first:text-left"
            style={{ color: "#8B8E96" }}
          >
            {label}
          </span>
        ))}
      </div>

      {/* Table rows */}
      {sorted.map((row) => {
        const isBest = row.strategy === data.best_strategy;
        const barWidth = Math.max(
          (Math.abs(row.total_return) / maxReturn) * 100,
          4
        );
        const barColor =
          row.total_return >= 0 ? "rgba(0,107,63,0.35)" : "rgba(139,0,0,0.35)";

        return (
          <div
            key={row.strategy}
            className="relative grid gap-1 px-1 py-[7px] transition-colors"
            style={{
              gridTemplateColumns: "minmax(90px, 1.2fr) 1fr 0.7fr 0.7fr 0.7fr 0.5fr 0.7fr",
              borderBottom: "1px solid rgba(212,175,55,0.06)",
              borderLeft: isBest
                ? "2px solid #D4AF37"
                : "2px solid transparent",
              background: isBest ? "rgba(212,175,55,0.04)" : "transparent",
            }}
          >
            {/* Strategy name */}
            <span
              className="text-[11px] font-[Josefin_Sans] font-medium tracking-[0.04em]"
              style={{
                color: isBest ? "#FFD700" : "#F5E6CA",
              }}
            >
              {STRATEGY_LABELS[row.strategy] ?? row.strategy}
            </span>

            {/* Total return with mini equity bar */}
            <div className="flex items-center justify-end gap-1">
              <div
                className="h-[6px] transition-all"
                style={{
                  width: `${barWidth}%`,
                  minWidth: "3px",
                  background: barColor,
                }}
              />
              <span
                className="text-[12px] font-[DM_Mono] font-medium tabular-nums"
                style={{ color: returnColor(row.total_return) }}
              >
                {row.total_return >= 0 ? "+" : ""}
                {row.total_return.toFixed(1)}%
              </span>
            </div>

            {/* Sharpe */}
            <span
              className="text-[12px] font-[DM_Mono] font-medium text-right tabular-nums"
              style={{ color: sharpeColor(row.sharpe) }}
            >
              {row.sharpe.toFixed(2)}
            </span>

            {/* Max Drawdown */}
            <span
              className="text-[12px] font-[DM_Mono] font-medium text-right tabular-nums"
              style={{ color: drawdownColor(row.max_drawdown) }}
            >
              -{row.max_drawdown.toFixed(1)}%
            </span>

            {/* Win Rate */}
            <span
              className="text-[12px] font-[DM_Mono] font-medium text-right tabular-nums"
              style={{ color: winRateColor(row.win_rate) }}
            >
              {row.win_rate.toFixed(0)}%
            </span>

            {/* Trades */}
            <span
              className="text-[12px] font-[DM_Mono] text-right tabular-nums"
              style={{ color: "#F5E6CA" }}
            >
              {row.trades}
            </span>

            {/* Profit Factor */}
            <span
              className="text-[12px] font-[DM_Mono] font-medium text-right tabular-nums"
              style={{ color: pfColor(row.profit_factor) }}
            >
              {row.profit_factor.toFixed(2)}
            </span>
          </div>
        );
      })}
    </Mod>
  );
}
