"use client";

import type { WatchlistItem } from "../types";
import { decColor, displayDec } from "../types";

export function WatchlistGrid({ items, onSelect }: { items: WatchlistItem[]; onSelect: (ticker: string) => void }) {
  if (items.length === 0) return null;
  return (
    <div className="mb-4">
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
        {items.map((item) => {
          const dc = decColor(item.decision);
          const pctColor = (item.change_pct ?? 0) >= 0 ? "#006B3F" : "#8B0000";
          const heroProb = item.decision === "SELL"
            ? Math.round((item.probabilities?.down ?? 0) * 100)
            : Math.round((item.probabilities?.up ?? 0) * 100);
          return (
            <button key={item.ticker} onClick={() => onSelect(item.ticker)}
              className="relative text-left transition-all hover:scale-[1.02]"
              style={{ background: "linear-gradient(180deg, #1A1A2E 0%, #0D1117 100%)", border: "1px solid rgba(212,175,55,0.12)" }}>
              <div className="h-[2px]" style={{ background: `linear-gradient(90deg, transparent, ${dc}, transparent)` }} />
              <div className="px-3 pt-3 pb-2">
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <div className="text-[13px] font-[DM_Mono] font-bold text-[#F5E6CA]">{item.ticker}</div>
                    {item.price && <div className="text-[10px] font-[DM_Mono] text-[#8B8E96]">${item.price.toFixed(2)}</div>}
                  </div>
                  <div className="text-right">
                    <div className="text-[18px] font-[DM_Mono] font-bold leading-none" style={{ color: dc }}>{heroProb}%</div>
                    <div className="text-[8px] font-[Josefin_Sans] text-[#8B8E96] uppercase tracking-[0.1em]">{item.decision === "SELL" ? "Down" : "Up"}</div>
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] px-1.5 py-0.5"
                    style={{ color: dc, background: `${dc}15`, border: `1px solid ${dc}30` }}>
                    {displayDec(item.decision)}
                  </span>
                  {item.change_pct != null && (
                    <span className="text-[10px] font-[DM_Mono] font-medium" style={{ color: pctColor }}>
                      {item.change_pct >= 0 ? "+" : ""}{item.change_pct.toFixed(2)}%
                    </span>
                  )}
                </div>
                <div className="flex h-[3px] mt-2 overflow-hidden" style={{ background: "#2A2A3E" }}>
                  <div style={{ width: `${Math.round((item.probabilities?.up ?? 0.33) * 100)}%`, background: "#006B3F" }} />
                  <div style={{ width: `${Math.round((item.probabilities?.neutral ?? 0.34) * 100)}%`, background: "#C5A255" }} />
                  <div style={{ width: `${Math.round((item.probabilities?.down ?? 0.33) * 100)}%`, background: "#8B0000" }} />
                </div>
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="text-[8px] font-[Josefin_Sans] text-[#4A4D55] uppercase">Conf</span>
                  <div className="flex-1 h-[2px]" style={{ background: "#2A2A3E" }}>
                    <div className="h-full" style={{ width: `${item.confidence}%`, background: "#D4AF37" }} />
                  </div>
                  <span className="text-[8px] font-[DM_Mono] text-[#8B8E96]">{item.confidence.toFixed(0)}%</span>
                </div>
              </div>
              {/* PM preview (when portfolio supplied) */}
              {item.pm_preview && (
                <div className="px-3 pb-1 pt-1 flex items-center gap-2"
                  style={{ borderTop: "1px dashed rgba(212,175,55,0.10)" }}>
                  {item.pm_preview.approved && item.pm_preview.scaled_position_pct !== undefined && (
                    <span className="text-[8px] font-[DM_Mono] px-1 py-0.5"
                      style={{ background: "rgba(0,107,63,0.10)", color: "#006B3F" }}>
                      PM ✓ {item.pm_preview.scaled_position_pct.toFixed(1)}%
                    </span>
                  )}
                  {item.pm_preview.approved === false && (
                    <span className="text-[8px] font-[Josefin_Sans] uppercase tracking-[0.12em] font-bold px-1 py-0.5"
                      style={{ background: "rgba(139,0,0,0.10)", color: "#8B0000" }}>
                      PM blocked
                    </span>
                  )}
                  {item.pm_preview.warnings && item.pm_preview.warnings.length > 0 && (
                    <span className="text-[8px] font-[DM_Mono] text-[#C5A255]"
                      title={item.pm_preview.warnings.join(" · ")}>
                      ⚠ {item.pm_preview.warnings.length}
                    </span>
                  )}
                </div>
              )}
              {/* 8-source fusion overlay (when use_fusion=true was sent) */}
              {item.fusion && (
                <div className="px-3 pb-2 pt-1 border-t" style={{ borderColor: "rgba(212,175,55,0.1)" }}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[7px] font-[Josefin_Sans] uppercase tracking-[0.14em] text-[#8B8E96]">
                      8-src
                    </span>
                    <span
                      className="text-[10px] font-[DM_Mono] font-medium"
                      style={{
                        color: item.fusion.conviction > 15 ? "#006B3F" :
                               item.fusion.conviction < -15 ? "#8B0000" : "#D4AF37",
                      }}
                    >
                      {item.fusion.conviction >= 0 ? "+" : ""}{item.fusion.conviction}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {item.fusion.top_sources.slice(0, 3).map((s, i) => (
                      <span key={i}
                        className="text-[7px] font-[DM_Mono] px-1 py-[1px]"
                        style={{
                          background: "rgba(212,175,55,0.05)",
                          color: s.score > 0 ? "#006B3F" : s.score < 0 ? "#8B0000" : "#8B8E96",
                        }}>
                        {s.name.slice(0, 6)} {s.score >= 0 ? "+" : ""}{s.score}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {item.error && <div className="px-3 pb-2 text-[8px] text-[#8B0000]/60 truncate">{item.error}</div>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
