"use client";

import type { BreakingSignal } from "../types";

function breakingExplain(s: BreakingSignal, zh: boolean): string {
  if (s.type === "decision_flip") {
    if (zh) {
      const from = s.prev_decision === "BUY" ? "买入" : s.prev_decision === "SELL" ? "卖出" : "观望";
      const to = s.new_decision === "BUY" ? "买入" : s.new_decision === "SELL" ? "卖出" : "观望";
      return `系统建议从「${from}」变成「${to}」，方向反转，暂时别动`;
    }
    return `Signal flipped from ${s.prev_decision} to ${s.new_decision} — direction reversed, stay cautious`;
  }
  if (s.type === "probability_shift") {
    if (s.direction === "bullish") return zh ? "上涨概率大幅上升 → 偏看多，但建议等确认信号" : "Upside probability surged — leaning bullish, wait for confirmation";
    return zh ? "上涨概率大幅下降 → 偏看空，建议观望不要追" : "Upside probability dropped — leaning bearish, avoid chasing";
  }
  if (s.type === "confidence_shift") {
    const shift = s.shift_pct ?? 0;
    if (shift > 0) return zh ? "系统信心大幅提升，信号变强，可以关注" : "Confidence surged — signal strengthening, worth watching";
    return zh ? "系统信心大幅下降，信号变弱，建议观望" : "Confidence dropped — signal weakening, stay on sidelines";
  }
  return "";
}

export function BreakingBanner({ signals, zh }: { signals: BreakingSignal[]; zh: boolean }) {
  if (signals.length === 0) return null;

  const severityStyle = (s: string) => {
    if (s === "critical") return { bg: "rgba(139,0,0,0.12)", border: "rgba(139,0,0,0.4)", icon: "⚡", color: "#FF4444" };
    if (s === "high") return { bg: "rgba(212,175,55,0.08)", border: "rgba(212,175,55,0.35)", icon: "△", color: "#D4AF37" };
    return { bg: "rgba(0,107,63,0.08)", border: "rgba(0,107,63,0.3)", icon: "●", color: "#006B3F" };
  };

  return (
    <div className="mb-4 space-y-2">
      {signals.map((s, i) => {
        const st = severityStyle(s.severity);
        const hint = breakingExplain(s, zh);
        return (
          <div key={i} className="flex flex-col gap-1 px-5 py-3 border animate-pulse"
            style={{ background: st.bg, borderColor: st.border }}>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-[14px]" style={{ color: st.color }}>{st.icon}</span>
                <span className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.2em]"
                  style={{ color: st.color }}>Breaking</span>
              </div>
              <div className="h-4 w-px" style={{ background: "rgba(212,175,55,0.15)" }} />
              <span className="text-[11px] font-[Lato] text-[#F5E6CA]/80 font-light">{s.message}</span>
              <span className="ml-auto text-[8px] font-[DM_Mono] text-[#4A4D55] shrink-0">
                {s.timestamp.slice(11, 16)}
              </span>
            </div>
            {hint && (
              <span className="text-[10px] font-[Lato] text-[#F5E6CA]/50 pl-7">
                → {hint}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
