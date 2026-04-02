"use client";

import type { MLModel } from "../types";
import { Mod } from "./atoms";

export function MLScoreboard({ models }: { models: MLModel[] }) {
  if (models.length === 0) return null;
  const best = models.reduce((a, b) => a.sharpe > b.sharpe ? a : b);
  return (
    <Mod title="ML Models">
      <div className="grid grid-cols-4 gap-0 text-[8px] font-[Josefin_Sans] text-[#6B6E76] uppercase tracking-[0.1em] pb-1.5 border-b mb-1" style={{ borderColor: "rgba(212,175,55,0.08)" }}>
        <span>Model</span><span className="text-right">Sharpe</span><span className="text-right">Return</span><span className="text-right">Win%</span>
      </div>
      {models.map((m, i) => {
        const isBest = m.model === best.model && m.model !== "Buy & Hold";
        return (
          <div key={i} className={`grid grid-cols-4 gap-0 py-[5px] border-b last:border-b-0 ${isBest ? "bg-[#D4AF37]/5" : ""}`} style={{ borderColor: "rgba(212,175,55,0.04)" }}>
            <span className={`text-[10px] font-[Lato] truncate pr-1 ${isBest ? "text-[#D4AF37] font-semibold" : "text-[#F5E6CA]/60"}`}>{m.model}</span>
            <span className={`text-[10px] font-[DM_Mono] text-right ${m.sharpe > 0 ? "text-[#006B3F]" : "text-[#8B0000]"}`}>{m.sharpe.toFixed(2)}</span>
            <span className={`text-[10px] font-[DM_Mono] text-right ${m.return > 0 ? "text-[#006B3F]" : "text-[#8B0000]"}`}>{m.return > 0 ? "+" : ""}{m.return.toFixed(1)}%</span>
            <span className="text-[10px] font-[DM_Mono] text-right text-[#F5E6CA]/50">{m.win_rate.toFixed(0)}%</span>
          </div>
        );
      })}
    </Mod>
  );
}
