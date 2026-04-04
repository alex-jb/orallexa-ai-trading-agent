"use client";

import type { MLModel } from "../types";
import { Mod } from "./atoms";

export function MLScoreboard({ models }: { models: MLModel[] }) {
  if (models.length === 0) return null;
  const activeModels = models.filter(m => m.status !== "failed" && m.status !== "skipped");
  const failedModels = models.filter(m => m.status === "failed" || m.status === "skipped");
  const best = activeModels.length > 0
    ? activeModels.reduce((a, b) => a.sharpe > b.sharpe ? a : b)
    : null;
  return (
    <Mod title="ML Models">
      <div className="grid grid-cols-4 gap-0 text-[8px] font-[Josefin_Sans] text-[#8B8E96] uppercase tracking-[0.1em] pb-1.5 border-b mb-1" style={{ borderColor: "rgba(212,175,55,0.08)" }}>
        <span>Model</span><span className="text-right">Sharpe</span><span className="text-right">Return</span><span className="text-right">Win%</span>
      </div>
      {activeModels.map((m, i) => {
        const isBest = best && m.model === best.model && m.model !== "Buy & Hold";
        return (
          <div key={i} className={`grid grid-cols-4 gap-0 py-[5px] border-b last:border-b-0 ${isBest ? "bg-[#D4AF37]/5" : ""}`} style={{ borderColor: "rgba(212,175,55,0.04)" }}>
            <span className={`text-[10px] font-[Lato] truncate pr-1 ${isBest ? "text-[#D4AF37] font-semibold" : "text-[#F5E6CA]/60"}`}>{m.model}</span>
            <span className={`text-[10px] font-[DM_Mono] text-right ${m.sharpe > 0 ? "text-[#006B3F]" : "text-[#8B0000]"}`}>{m.sharpe.toFixed(2)}</span>
            <span className={`text-[10px] font-[DM_Mono] text-right ${m.return > 0 ? "text-[#006B3F]" : "text-[#8B0000]"}`}>{m.return > 0 ? "+" : ""}{m.return.toFixed(1)}%</span>
            <span className="text-[10px] font-[DM_Mono] text-right text-[#F5E6CA]/50">{m.win_rate.toFixed(0)}%</span>
          </div>
        );
      })}
      {failedModels.length > 0 && (
        <div className="mt-2 pt-2 border-t" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
          <div className="text-[8px] font-[Josefin_Sans] text-[#4A4D55] uppercase tracking-[0.1em] mb-1">
            {failedModels.length} model{failedModels.length > 1 ? "s" : ""} unavailable
          </div>
          {failedModels.map((m, i) => (
            <div key={i} className="flex items-center justify-between py-[3px]" title={m.error || ""}>
              <span className="text-[9px] font-[Lato] text-[#4A4D55] truncate">{m.model}</span>
              <span className="text-[7px] font-[DM_Mono] uppercase px-1 py-0.5"
                style={{ color: m.status === "failed" ? "#8B0000" : "#CD7F32", background: m.status === "failed" ? "rgba(139,0,0,0.08)" : "rgba(205,127,50,0.08)" }}>
                {m.status === "failed" ? "FAILED" : "SKIP"}
              </span>
            </div>
          ))}
        </div>
      )}
    </Mod>
  );
}
