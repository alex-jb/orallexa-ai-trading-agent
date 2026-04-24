"use client";

import { Mod } from "./atoms";

export interface RegimeProposal {
  ticker: string;
  regime: "trending" | "ranging" | "volatile" | "unknown";
  strategy: string | null;
  params: Record<string, number | string>;
  reasoning: string;
  source: "heuristic" | "llm" | "none";
}

const REGIME_BADGE: Record<
  string,
  { en: string; zh: string; icon: string; color: string; bg: string }
> = {
  trending: { en: "TRENDING",  zh: "趋势行情",  icon: "📈", color: "#006B3F", bg: "rgba(0,107,63,0.10)" },
  ranging:  { en: "RANGING",   zh: "震荡行情",  icon: "↔",  color: "#D4AF37", bg: "rgba(212,175,55,0.10)" },
  volatile: { en: "VOLATILE",  zh: "高波动",    icon: "⚡", color: "#8B0000", bg: "rgba(139,0,0,0.10)" },
  unknown:  { en: "UNKNOWN",   zh: "未知",     icon: "·",   color: "#6B6E76", bg: "rgba(107,110,118,0.08)" },
};

const STRATEGY_LABELS: Record<string, { en: string; zh: string }> = {
  trend_momentum: { en: "Trend Momentum", zh: "动量趋势" },
  rsi_reversal:   { en: "RSI Reversal",   zh: "RSI 反转" },
  dual_thrust:    { en: "Dual Thrust",    zh: "双轨突破" },
  macd_crossover: { en: "MACD Crossover", zh: "MACD 交叉" },
  bollinger_breakout: { en: "Bollinger Breakout", zh: "布林带突破" },
  double_ma:      { en: "Double MA",      zh: "双均线" },
  alpha_combo:    { en: "Alpha Combo",    zh: "Alpha 组合" },
  ensemble_vote:  { en: "Ensemble Vote",  zh: "集成投票" },
  regime_ensemble: { en: "Regime Ensemble", zh: "Regime 集成" },
};

function formatParam(key: string, value: number | string): string {
  if (typeof value !== "number") return `${key}: ${value}`;
  if (key === "stop_loss" || key === "take_profit") return `${key}: ${(value * 100).toFixed(1)}%`;
  return `${key}: ${Number.isInteger(value) ? value : value.toFixed(2)}`;
}

export function RegimeCard({
  proposal,
  t,
  zh,
}: {
  proposal: RegimeProposal | null;
  t: Record<string, string>;
  zh: boolean;
}) {
  if (!proposal) return null;

  const badge = REGIME_BADGE[proposal.regime] || REGIME_BADGE.unknown;
  const strategyLabel =
    proposal.strategy && STRATEGY_LABELS[proposal.strategy]
      ? (zh ? STRATEGY_LABELS[proposal.strategy].zh : STRATEGY_LABELS[proposal.strategy].en)
      : proposal.strategy || "—";

  const sourceLabel =
    proposal.source === "llm" ? (zh ? "LLM 提议" : "LLM proposal") :
    proposal.source === "heuristic" ? (zh ? "规则" : "Heuristic") :
    (zh ? "无" : "None");

  return (
    <Mod title={t.regimeStrategy || (zh ? "行情与策略" : "Regime & Strategy")}>
      {/* Regime badge row */}
      <div className="flex items-center justify-between mb-3 px-2 py-2" style={{ background: badge.bg }}>
        <div className="flex items-center gap-3">
          <span className="text-[18px]" style={{ color: badge.color }}>{badge.icon}</span>
          <div>
            <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] text-[#8B8E96]">
              {zh ? "当前行情" : "Current Regime"}
            </div>
            <div className="text-[14px] font-[Josefin_Sans] font-bold tracking-[0.12em]" style={{ color: badge.color }}>
              {zh ? badge.zh : badge.en}
            </div>
          </div>
        </div>
        <span
          className="text-[8px] font-[Josefin_Sans] uppercase tracking-[0.14em] px-1.5 py-0.5"
          style={{
            color: badge.color,
            border: `1px solid ${badge.color}40`,
          }}
        >
          {sourceLabel}
        </span>
      </div>

      {/* Proposed strategy */}
      {proposal.strategy && (
        <div className="mb-3">
          <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] text-[#8B8E96] mb-1">
            {zh ? "建议策略" : "Proposed Strategy"}
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-[14px] font-[DM_Mono] font-medium text-[#F5E6CA]">
              {strategyLabel}
            </span>
            <span className="text-[9px] font-[DM_Mono] text-[#4A4D55]">
              ({proposal.strategy})
            </span>
          </div>
        </div>
      )}

      {/* Parameters */}
      {Object.keys(proposal.params || {}).length > 0 && (
        <div className="mb-3">
          <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] text-[#8B8E96] mb-1">
            {zh ? "参数" : "Parameters"}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(proposal.params).map(([k, v]) => (
              <span
                key={k}
                className="text-[9px] font-[DM_Mono] text-[#F5E6CA]/80 px-2 py-0.5"
                style={{ background: "rgba(212,175,55,0.05)", border: "1px solid rgba(212,175,55,0.12)" }}
              >
                {formatParam(k, v)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Reasoning */}
      {proposal.reasoning && (
        <div>
          <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] text-[#8B8E96] mb-1">
            {zh ? "理由" : "Reasoning"}
          </div>
          <p className="text-[10px] font-[Lato] text-[#F5E6CA]/75 leading-relaxed font-light">
            {proposal.reasoning}
          </p>
        </div>
      )}
    </Mod>
  );
}
