"use client";

import type { PortfolioManagerVerdict } from "../types";
import { Mod } from "./atoms";

export function PortfolioManagerCard({
  verdict,
  t,
  zh,
}: {
  verdict: PortfolioManagerVerdict | null;
  t: Record<string, string>;
  zh: boolean;
}) {
  if (!verdict) return null;

  // Swallowed-exception breadcrumb: upstream PM call failed
  if (verdict.approved === null) {
    return (
      <Mod title={t.portfolioManager || (zh ? "组合管理" : "Portfolio Manager")}>
        <div className="flex items-center gap-2 px-2 py-2"
          style={{ background: "rgba(107,110,118,0.10)", border: "1px solid rgba(107,110,118,0.25)" }}>
          <span className="text-[14px] text-[#6B6E76]">·</span>
          <span className="text-[10px] font-[Lato] text-[#8B8E96]">
            {zh ? "PM 检查失败" : "PM check failed"}
            {verdict.error ? ` — ${verdict.error}` : ""}
          </span>
        </div>
      </Mod>
    );
  }

  const approved = verdict.approved;
  const color = approved ? "#006B3F" : "#8B0000";
  const bg = approved ? "rgba(0,107,63,0.10)" : "rgba(139,0,0,0.10)";
  const icon = approved ? "✓" : "✗";
  const label = approved
    ? (t.pmApproved || (zh ? "已批准" : "Approved"))
    : (t.pmRejected || (zh ? "已拒绝" : "Rejected"));

  return (
    <Mod title={t.portfolioManager || (zh ? "组合管理" : "Portfolio Manager")}>
      {/* Verdict banner */}
      <div
        className="flex items-center justify-between mb-3 px-2 py-2"
        style={{ background: bg, border: `1px solid ${color}40` }}
      >
        <div className="flex items-center gap-2">
          <span className="text-[16px] font-bold" style={{ color }}>{icon}</span>
          <span className="text-[12px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em]" style={{ color }}>
            {label}
          </span>
        </div>
        {verdict.scaled_position_pct !== undefined && approved && (
          <div className="flex flex-col items-end">
            <span className="text-[8px] font-[Josefin_Sans] uppercase tracking-[0.14em] text-[#8B8E96]">
              {t.pmPosition || (zh ? "仓位" : "Position")}
            </span>
            <span className="text-[14px] font-[DM_Mono] font-medium" style={{ color }}>
              {verdict.scaled_position_pct.toFixed(1)}%
            </span>
          </div>
        )}
      </div>

      {/* Reason */}
      {verdict.reason && (
        <div className="mb-3">
          <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] text-[#8B8E96] mb-1">
            {zh ? "理由" : "Reason"}
          </div>
          <p className="text-[10px] font-[Lato] text-[#F5E6CA]/80 leading-relaxed">
            {verdict.reason}
          </p>
        </div>
      )}

      {/* Warnings */}
      {verdict.warnings && verdict.warnings.length > 0 && (
        <div className="mb-3">
          <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] mb-1"
            style={{ color: "#D4AF37" }}>
            {t.pmWarnings || (zh ? "警告" : "Warnings")}
          </div>
          <ul className="space-y-0.5">
            {verdict.warnings.map((w, i) => (
              <li key={i} className="text-[10px] font-[Lato] text-[#F5E6CA]/75 flex gap-1.5">
                <span style={{ color: "#D4AF37" }}>⚠</span>
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Confidence adjustment */}
      {verdict.original_confidence !== undefined
        && verdict.adjusted_confidence !== undefined
        && verdict.original_confidence !== verdict.adjusted_confidence && (
        <div className="flex gap-4 text-[9px] font-[DM_Mono] text-[#8B8E96]">
          <span>
            {zh ? "原始置信度" : "Orig conf"}: {verdict.original_confidence}
          </span>
          <span>→</span>
          <span style={{ color: verdict.adjusted_confidence < verdict.original_confidence ? "#D4AF37" : "#006B3F" }}>
            {zh ? "调整后" : "adjusted"}: {verdict.adjusted_confidence}
          </span>
        </div>
      )}
    </Mod>
  );
}
