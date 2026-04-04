"use client";

import type { Decision, MarketSummary } from "../types";

export function MarketStrip({ summary, decision, livePrice, priceFlash, wsConnected }: {
  summary: MarketSummary | null; decision: Decision | null;
  livePrice?: { price: number; change_pct: number; high: number; low: number; timestamp: string } | null;
  priceFlash?: "up" | "down" | null;
  wsConnected?: boolean;
}) {
  if (!summary && !decision && !livePrice) return null;

  const price = livePrice?.price ?? summary?.close;
  const changePct = livePrice?.change_pct ?? summary?.change_pct;
  const priceColor = priceFlash === "up" ? "#00FF88" : priceFlash === "down" ? "#FF4444" : "#F5E6CA";

  const items = [
    { label: "Price", value: price ? `$${price.toFixed(2)}` : "—", color: priceColor, flash: !!priceFlash },
    { label: "Chg%", value: changePct != null ? `${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}%` : "—",
      color: changePct != null ? (changePct >= 0 ? "#006B3F" : "#8B0000") : "#F5E6CA" },
    { label: "RSI", value: summary?.rsi ? summary.rsi.toFixed(1) : "—", color: summary?.rsi && summary.rsi > 70 ? "#8B0000" : summary?.rsi && summary.rsi < 30 ? "#006B3F" : "#F5E6CA" },
    { label: "Signal", value: decision ? `${decision.signal_strength}/100` : "—", color: decision && decision.signal_strength >= 65 ? "#006B3F" : decision && decision.signal_strength < 35 ? "#8B0000" : "#D4AF37" },
    { label: "Conf", value: decision ? `${decision.confidence.toFixed(0)}%` : "—", color: decision && decision.confidence >= 70 ? "#006B3F" : decision && decision.confidence < 30 ? "#8B0000" : "#D4AF37" },
  ];

  if (livePrice?.high && livePrice?.low) {
    items.splice(2, 0, { label: "H/L", value: `${livePrice.high}/${livePrice.low}`, color: "#F5E6CA", flash: false });
  }

  return (
    <div className="flex border mb-4" style={{ borderColor: "rgba(212,175,55,0.1)", background: "rgba(26,26,46,0.5)" }}>
      {items.map((item, i) => (
        <div key={i} className={`flex-1 py-2.5 px-3 text-center ${i < items.length - 1 ? "border-r" : ""}`}
          style={{ borderColor: "rgba(212,175,55,0.06)", transition: "background 0.3s",
            background: (item as { flash?: boolean }).flash ? (priceFlash === "up" ? "rgba(0,107,63,0.15)" : "rgba(139,0,0,0.15)") : "transparent" }}>
          <div className="text-[8px] font-[Josefin_Sans] text-[#8B8E96] uppercase tracking-[0.14em]">{item.label}</div>
          <div className="text-[13px] font-[DM_Mono] font-medium mt-0.5 transition-colors" style={{ color: item.color }}>{item.value}</div>
        </div>
      ))}
      {(livePrice?.timestamp || wsConnected != null) && (
        <div className="flex items-center gap-1 px-2" style={{ borderLeft: "1px solid rgba(212,175,55,0.06)" }}>
          <div className={`w-1.5 h-1.5 rounded-full ${wsConnected ? "bg-[#006B3F]" : livePrice ? "bg-[#D4AF37]" : "bg-[#4A4D55]"} ${wsConnected || livePrice ? "animate-pulse" : ""}`}
            title={wsConnected ? "WebSocket Live" : livePrice ? "Polling" : "Offline"} />
          {wsConnected && <span className="text-[7px] font-[DM_Mono] text-[#006B3F]/60">WS</span>}
        </div>
      )}
    </div>
  );
}
