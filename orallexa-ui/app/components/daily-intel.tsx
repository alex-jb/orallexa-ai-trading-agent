"use client";

import { useState, useRef } from "react";
import type { DailyIntelData, MacroIndicator, EconEvent, FearGreedData, MarketBreadth, OptionsFlow } from "../types";
import { copyWithAttribution } from "../types";
import { Mod, CopyBtn, CopyImageBtn } from "./atoms";

/* ── Macro Pulse Strip ─────────────────────────────────────────────── */
function MacroPulse({ indicators, t }: { indicators: MacroIndicator[]; t: Record<string, string> }) {
  return (
    <div className="relative mb-3" style={{ background: "#1A1A2E" }}>
      <div className="absolute inset-0 border pointer-events-none" style={{ borderColor: "rgba(212,175,55,0.15)" }} />
      <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: "linear-gradient(90deg, transparent, #D4AF37, transparent)" }} />
      <div className="px-4 py-3">
        <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.28em] mb-3"
          style={{ background: "linear-gradient(135deg, #D4AF37, #FFD700, #C5A255)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
          {t.macroPulse}
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          {indicators.map((ind, i) => {
            const chgColor = ind.direction === "up" ? "#006B3F" : ind.direction === "down" ? "#8B0000" : "#8B8E96";
            const arrow = ind.direction === "up" ? "▲" : ind.direction === "down" ? "▼" : "–";
            return (
              <div key={i} className="text-center py-2 px-1" style={{ background: "rgba(42,42,62,0.5)", border: "1px solid rgba(212,175,55,0.06)" }}>
                <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#8B8E96] mb-1">{ind.label}</div>
                <div className="text-[14px] font-[DM_Mono] font-bold text-[#F5E6CA] leading-none">{ind.value}</div>
                <div className="text-[9px] font-[DM_Mono] mt-1" style={{ color: chgColor }}>
                  {arrow} {ind.change >= 0 ? "+" : ""}{ind.change.toFixed(1)}%
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ── Fear & Greed Gauge ────────────────────────────────────────────── */
function FearGreedGauge({ data, t }: { data: FearGreedData; t: Record<string, string> }) {
  const score = Math.max(0, Math.min(100, data.score));
  // Semicircle: 180deg arc, needle rotates from -90 (0) to +90 (100)
  const needleAngle = -90 + (score / 100) * 180;
  const scoreColor = score <= 25 ? "#8B0000" : score <= 40 ? "#CD7F32" : score <= 60 ? "#D4AF37" : score <= 75 ? "#006B3F" : "#006B3F";
  const signalColor = (s: string) =>
    s === "extreme_fear" ? "#8B0000" : s === "fear" ? "#CD7F32" : s === "neutral" ? "#D4AF37" : s === "greed" ? "#006B3F" : "#006B3F";

  return (
    <Mod title={t.fearGreed}>
      <div className="flex flex-col items-center py-2">
        {/* Gauge SVG */}
        <div className="w-full max-w-[220px] mx-auto">
        <svg width="100%" height="auto" viewBox="0 0 200 110">
          {/* Background arc segments */}
          {[
            { start: -90, end: -54, color: "#8B0000" },
            { start: -54, end: -18, color: "#CD7F32" },
            { start: -18, end: 18, color: "#D4AF37" },
            { start: 18, end: 54, color: "#6B8E23" },
            { start: 54, end: 90, color: "#006B3F" },
          ].map((seg, i) => {
            const r = 80;
            const cx = 100, cy = 95;
            const x1 = cx + r * Math.cos((seg.start * Math.PI) / 180);
            const y1 = cy + r * Math.sin((seg.start * Math.PI) / 180);
            const x2 = cx + r * Math.cos((seg.end * Math.PI) / 180);
            const y2 = cy + r * Math.sin((seg.end * Math.PI) / 180);
            return (
              <path key={i}
                d={`M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`}
                fill="none" stroke={seg.color} strokeWidth="8" strokeLinecap="butt" opacity="0.4" />
            );
          })}
          {/* Tick marks */}
          {[0, 25, 50, 75, 100].map(v => {
            const angle = -90 + (v / 100) * 180;
            const r1 = 72, r2 = 68;
            const cx = 100, cy = 95;
            const x1 = cx + r1 * Math.cos((angle * Math.PI) / 180);
            const y1 = cy + r1 * Math.sin((angle * Math.PI) / 180);
            const x2 = cx + r2 * Math.cos((angle * Math.PI) / 180);
            const y2 = cy + r2 * Math.sin((angle * Math.PI) / 180);
            return <line key={v} x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgba(212,175,55,0.3)" strokeWidth="1" />;
          })}
          {/* Needle */}
          <line x1="100" y1="95"
            x2={100 + 60 * Math.cos((needleAngle * Math.PI) / 180)}
            y2={95 + 60 * Math.sin((needleAngle * Math.PI) / 180)}
            stroke={scoreColor} strokeWidth="2" strokeLinecap="round" />
          <circle cx="100" cy="95" r="4" fill={scoreColor} />
          <circle cx="100" cy="95" r="2" fill="#0A0A0F" />
          {/* Score text */}
          <text x="100" y="88" textAnchor="middle" fill={scoreColor}
            style={{ fontSize: "24px", fontFamily: "DM Mono", fontWeight: 700 }}>{score}</text>
          {/* Labels */}
          <text x="18" y="100" textAnchor="middle" fill="#8B0000"
            style={{ fontSize: "7px", fontFamily: "Josefin Sans", textTransform: "uppercase", letterSpacing: "0.08em" }}>{t.fearLabel}</text>
          <text x="182" y="100" textAnchor="middle" fill="#006B3F"
            style={{ fontSize: "7px", fontFamily: "Josefin Sans", textTransform: "uppercase", letterSpacing: "0.08em" }}>{t.greedLabel}</text>
        </svg>
        </div>
        <div className="text-[16px] font-[Josefin_Sans] font-bold uppercase tracking-[0.12em] -mt-2" style={{ color: scoreColor }}>{data.label}</div>
      </div>
      {/* Component breakdown */}
      <div className="space-y-1 mt-2">
        {data.components.map((c, i) => {
          const barWidth = c.value;
          const color = signalColor(c.signal);
          return (
            <div key={i} className="flex items-center gap-2 py-[2px]">
              <span className="text-[9px] font-[Lato] text-[#8B8E96] w-[100px] shrink-0 truncate">{c.name}</span>
              <div className="flex-1 h-[5px] relative" style={{ background: "#2A2A3E" }}>
                <div className="absolute top-0 left-0 h-full transition-all" style={{ width: `${barWidth}%`, background: color }} />
              </div>
              <span className="text-[9px] font-[DM_Mono] w-[28px] text-right" style={{ color }}>{c.value}</span>
            </div>
          );
        })}
      </div>
    </Mod>
  );
}

/* ── Economic Calendar ─────────────────────────────────────────────── */
function EconCalendar({ events, t, zh }: { events: EconEvent[]; t: Record<string, string>; zh: boolean }) {
  const todayStr = new Date().toISOString().slice(0, 10);
  const tomorrowStr = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  const dayLabel = (d: string) => d === todayStr ? (t.calToday || "Today") : d === tomorrowStr ? (t.calTomorrow || "Tomorrow") : d.slice(5);
  const impactDots = (impact: string) => {
    const color = impact === "high" ? "#8B0000" : impact === "medium" ? "#D4AF37" : "#8B8E96";
    const count = impact === "high" ? 3 : impact === "medium" ? 2 : 1;
    return (
      <div className="flex gap-[2px]">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="w-[5px] h-[5px] rotate-45" style={{ background: i < count ? color : "rgba(42,42,62,0.8)" }} />
        ))}
      </div>
    );
  };

  // Group by date
  const grouped = events.reduce<Record<string, EconEvent[]>>((acc, e) => {
    (acc[e.date] ??= []).push(e);
    return acc;
  }, {});

  return (
    <Mod title={t.econCalendar}>
      {Object.entries(grouped).map(([date, evts]) => (
        <div key={date} className="mb-2 last:mb-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.2em] px-1.5 py-0.5"
              style={{ color: date === todayStr ? "#D4AF37" : "#8B8E96", background: date === todayStr ? "rgba(212,175,55,0.08)" : "transparent", border: date === todayStr ? "1px solid rgba(212,175,55,0.2)" : "1px solid transparent" }}>
              {dayLabel(date)}
            </span>
            <div className="flex-1 h-px" style={{ background: "rgba(212,175,55,0.08)" }} />
          </div>
          {evts.map((ev, i) => (
            <div key={i} className="flex items-center gap-2 py-[5px] border-b last:border-b-0" style={{ borderColor: "rgba(212,175,55,0.04)" }}>
              <span className="text-[9px] font-[DM_Mono] text-[#4A4D55] w-[36px] shrink-0">{ev.time}</span>
              {impactDots(ev.impact)}
              <span className="text-[10px] font-[Lato] text-[#F5E6CA]/80 font-light flex-1 truncate">{ev.event}</span>
              {(ev.forecast || ev.previous) && (
                <div className="flex gap-2 shrink-0">
                  {ev.forecast && <span className="text-[8px] font-[DM_Mono] text-[#D4AF37]">{zh ? "预" : "F"}: {ev.forecast}</span>}
                  {ev.previous && <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">{zh ? "前" : "P"}: {ev.previous}</span>}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </Mod>
  );
}

/* ── Market Breadth ────────────────────────────────────────────────── */
function BreadthPanel({ data, t }: { data: MarketBreadth; t: Record<string, string> }) {
  const total = data.advancers + data.decliners + data.unchanged;
  const advPct = total > 0 ? (data.advancers / total) * 100 : 50;
  const decPct = total > 0 ? (data.decliners / total) * 100 : 50;
  const totalVol = data.adv_vol + data.dec_vol;
  const advVolPct = totalVol > 0 ? (data.adv_vol / totalVol) * 100 : 50;
  const fmtVol = (v: number) => v >= 1e9 ? `${(v / 1e9).toFixed(1)}B` : `${(v / 1e6).toFixed(0)}M`;

  return (
    <Mod title={t.marketBreadth}>
      {/* Advance / Decline bar */}
      <div className="mb-3">
        <div className="flex justify-between mb-1">
          <span className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em]" style={{ color: "#006B3F" }}>
            {t.advancers} {data.advancers}
          </span>
          <span className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em]" style={{ color: "#8B0000" }}>
            {data.decliners} {t.decliners}
          </span>
        </div>
        <div className="flex h-[8px] w-full overflow-hidden" style={{ background: "#2A2A3E" }}>
          <div style={{ width: `${advPct}%`, background: "#006B3F" }} />
          <div className="w-px" style={{ background: "rgba(212,175,55,0.3)" }} />
          <div style={{ width: `${decPct}%`, background: "#8B0000" }} />
        </div>
        <div className="text-center text-[8px] font-[DM_Mono] text-[#4A4D55] mt-1">
          {data.unchanged} {t.unchanged}
        </div>
      </div>

      {/* Volume split */}
      <div className="mb-3">
        <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#8B8E96] mb-1">{t.volumeLabel}</div>
        <div className="flex h-[6px] w-full overflow-hidden" style={{ background: "#2A2A3E" }}>
          <div style={{ width: `${advVolPct}%`, background: "rgba(0,107,63,0.6)" }} />
          <div style={{ width: `${100 - advVolPct}%`, background: "rgba(139,0,0,0.6)" }} />
        </div>
        <div className="flex justify-between mt-1">
          <span className="text-[8px] font-[DM_Mono]" style={{ color: "#006B3F" }}>{fmtVol(data.adv_vol)}</span>
          <span className="text-[8px] font-[DM_Mono]" style={{ color: "#8B0000" }}>{fmtVol(data.dec_vol)}</span>
        </div>
      </div>

      {/* 52-week highs/lows */}
      <div className="grid grid-cols-1 min-[360px]:grid-cols-2 gap-2 min-[360px]:gap-4">
        <div className="text-center py-2" style={{ background: "rgba(0,107,63,0.06)", border: "1px solid rgba(0,107,63,0.15)" }}>
          <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#8B8E96] mb-1">{t.newHighs}</div>
          <div className="text-[18px] font-[DM_Mono] font-bold" style={{ color: "#006B3F" }}>{data.new_highs}</div>
        </div>
        <div className="text-center py-2" style={{ background: "rgba(139,0,0,0.06)", border: "1px solid rgba(139,0,0,0.15)" }}>
          <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#8B8E96] mb-1">{t.newLows}</div>
          <div className="text-[18px] font-[DM_Mono] font-bold" style={{ color: "#8B0000" }}>{data.new_lows}</div>
        </div>
      </div>
    </Mod>
  );
}

/* ── Options Flow ──────────────────────────────────────────────────── */
function OptionsFlowPanel({ flows, onSelectTicker, t }: { flows: OptionsFlow[]; onSelectTicker: (tk: string) => void; t: Record<string, string> }) {
  return (
    <Mod title={t.optionsFlow}>
      {flows.map((f, i) => {
        const isCall = f.type === "call";
        const color = f.sentiment === "bullish" ? "#006B3F" : "#8B0000";
        return (
          <button key={i} onClick={() => onSelectTicker(f.ticker)}
            className="w-full flex items-center gap-2 py-[6px] border-b last:border-b-0 hover:bg-[#D4AF37]/4 transition-colors text-left"
            style={{ borderColor: "rgba(212,175,55,0.04)" }}>
            {/* Ticker + type badge */}
            <span className="text-[11px] font-[DM_Mono] font-bold text-[#F5E6CA] w-[42px] shrink-0">{f.ticker}</span>
            <span className="text-[7px] font-[Josefin_Sans] font-bold uppercase tracking-[0.08em] px-1.5 py-[2px] shrink-0"
              style={{ color, background: `${color}15`, border: `1px solid ${color}30` }}>
              {isCall ? t.callType : t.putType}
            </span>
            {/* Strike + expiry */}
            <div className="flex-1 min-w-0">
              <span className="text-[9px] font-[DM_Mono] text-[#F5E6CA]/60">{f.strike}</span>
              <span className="text-[8px] font-[Lato] text-[#4A4D55] ml-1">{f.expiry}</span>
            </div>
            {/* Premium */}
            <span className="text-[10px] font-[DM_Mono] font-medium shrink-0" style={{ color }}>{f.premium}</span>
            {/* Unusual flag */}
            {f.unusual && (
              <span className="w-[5px] h-[5px] rotate-45 shrink-0" style={{ background: "#D4AF37" }} title={t.unusualActivity} />
            )}
          </button>
        );
      })}
      <div className="text-[8px] font-[Lato] text-[#4A4D55] mt-2 flex items-center gap-1">
        <span className="w-[4px] h-[4px] rotate-45 inline-block" style={{ background: "#D4AF37" }} />
        = {t.unusualActivity}
      </div>
    </Mod>
  );
}

/* ── Share Row ────────────────────────────────────────────────────── */
function ShareRow({ briefText, t }: { briefText: string; t: Record<string, string> }) {
  const [copied, setCopied] = useState(false);

  const pageUrl = typeof window !== "undefined" ? window.location.href : "";
  const shareText = briefText || "AI-Powered Capital Intelligence — Orallexa";

  const handleShareX = () => {
    const url = `https://twitter.com/intent/tweet?text=${encodeURIComponent(shareText)}&url=${encodeURIComponent(pageUrl)}&via=orallexatrading`;
    window.open(url, "_blank", "noopener,noreferrer,width=550,height=420");
  };

  const handleShareLinkedIn = () => {
    const url = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(pageUrl)}`;
    window.open(url, "_blank", "noopener,noreferrer,width=550,height=420");
  };

  const handleCopyLink = () => {
    navigator.clipboard.writeText(pageUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative" style={{ background: "#1A1A2E" }}>
      <div className="absolute inset-0 border pointer-events-none" style={{ borderColor: "rgba(212,175,55,0.15)" }} />
      <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: "linear-gradient(90deg, transparent, #D4AF37, transparent)" }} />
      <div className="px-4 py-3">
        {/* Header */}
        <div className="flex items-center gap-2 mb-3">
          <div className="flex gap-0.5">
            <div className="w-1 h-1 rotate-45" style={{ background: "#D4AF37" }} />
            <div className="w-1.5 h-1.5 rotate-45 border" style={{ borderColor: "#D4AF37" }} />
          </div>
          <span className="text-[10px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.28em]"
            style={{ background: "linear-gradient(135deg, #D4AF37, #FFD700, #C5A255)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            {t.share}
          </span>
          <div className="flex-1 h-px" style={{ background: "linear-gradient(90deg, rgba(212,175,55,0.2), transparent)" }} />
        </div>

        {/* Buttons */}
        <div className="flex gap-2">
          {/* Share to X */}
          <button
            onClick={handleShareX}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 transition-colors hover:bg-[#D4AF37]/8"
            style={{ background: "rgba(42,42,62,0.5)", border: "1px solid rgba(212,175,55,0.12)" }}
            aria-label={t.shareX}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" fill="#D4AF37" />
            </svg>
            <span className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#D4AF37]">X</span>
          </button>

          {/* Share to LinkedIn */}
          <button
            onClick={handleShareLinkedIn}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 transition-colors hover:bg-[#D4AF37]/8"
            style={{ background: "rgba(42,42,62,0.5)", border: "1px solid rgba(212,175,55,0.12)" }}
            aria-label={t.shareLinkedIn}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" fill="#D4AF37" />
            </svg>
            <span className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#D4AF37]">LinkedIn</span>
          </button>

          {/* Copy Link */}
          <button
            onClick={handleCopyLink}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 transition-colors hover:bg-[#D4AF37]/8"
            style={{ background: copied ? "rgba(212,175,55,0.1)" : "rgba(42,42,62,0.5)", border: `1px solid ${copied ? "rgba(212,175,55,0.3)" : "rgba(212,175,55,0.12)"}` }}
            aria-label={t.copyLink}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              {copied ? (
                <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" fill="#D4AF37" />
              ) : (
                <path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z" fill="#D4AF37" />
              )}
            </svg>
            <span className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#D4AF37]">
              {copied ? t.copied : t.copyLink}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Sector Correlation Grid ──────────────────────────────────────── */
function SectorCorrelationGrid({ sectors, t }: { sectors: { sector: string; etf: string; change_pct: number }[]; t: Record<string, string> }) {
  if (sectors.length < 4) return null;
  const maxAbs = Math.max(...sectors.map(s => Math.abs(s.change_pct)), 0.5);
  const cellColor = (pct: number) => {
    const intensity = Math.min(Math.abs(pct) / maxAbs, 1);
    if (pct >= 0) return `rgba(0,107,63,${(intensity * 0.7 + 0.1).toFixed(2)})`;
    return `rgba(139,0,0,${(intensity * 0.7 + 0.1).toFixed(2)})`;
  };
  return (
    <Mod title={t.sectorHeatGrid || "SECTOR HEAT GRID"}>
      <div className="grid gap-[2px]" style={{ gridTemplateColumns: `repeat(${Math.min(sectors.length, 4)}, 1fr)` }}>
        {sectors.map((s, i) => (
          <div key={i} className="text-center py-2 px-1 transition-all hover:brightness-125" style={{ background: cellColor(s.change_pct), border: "1px solid rgba(212,175,55,0.04)" }}>
            <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.1em] text-[#F5E6CA]/80 truncate">{s.sector.replace("Comm ", "").replace("Consumer ", "C.")}</div>
            <div className="text-[13px] font-[DM_Mono] font-bold text-[#F5E6CA] mt-0.5">{s.change_pct >= 0 ? "+" : ""}{s.change_pct.toFixed(1)}%</div>
            <div className="text-[7px] font-[DM_Mono] text-[#F5E6CA]/40 mt-0.5">{s.etf}</div>
          </div>
        ))}
      </div>
    </Mod>
  );
}

/* ── Mini Sparkline SVG ──────────────────────────────────────────── */
function MiniSparkline({ data, color, width = 60, height = 20 }: { data: number[]; color: string; width?: number; height?: number }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`).join(" ");
  return (
    <svg width={width} height={height} className="inline-block">
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={(data.length - 1) / (data.length - 1) * width} cy={height - ((data[data.length - 1] - min) / range) * height} r="2" fill={color} />
    </svg>
  );
}

/* ── Main Daily Intel View ─────────────────────────────────────────── */
export function DailyIntelView({ data, onSelectTicker, t, zh }: {
  data: DailyIntelData | null; onSelectTicker: (tk: string) => void; t: Record<string, string>; zh: boolean;
}) {
  if (!data) return (
    <div className="space-y-4">
      {[1,2,3,4].map(i => <div key={i} className="skeleton h-24 w-full" />)}
    </div>
  );

  const moodColor = data.market_mood === "Risk-On" ? "#006B3F" : data.market_mood === "Risk-Off" ? "#8B0000" : "#D4AF37";
  const moodBg = data.market_mood === "Risk-On" ? "rgba(0,107,63,0.08)" : data.market_mood === "Risk-Off" ? "rgba(139,0,0,0.08)" : "rgba(212,175,55,0.06)";
  const dirColor = (d: string) => d === "bullish" ? "#006B3F" : d === "bearish" ? "#8B0000" : "#D4AF37";

  // Refs for image capture
  const moversRef = useRef<HTMLDivElement>(null);
  const sectorRef = useRef<HTMLDivElement>(null);
  const picksRef = useRef<HTMLDivElement>(null);
  const fearRef = useRef<HTMLDivElement>(null);

  const moversText = (() => {
    const g = data.gainers.slice(0, 5).map(m => `🟢 $${m.ticker} +${m.change_pct.toFixed(1)}% ($${m.price})`).join("\n");
    const l = data.losers.slice(0, 5).map(m => `🔴 $${m.ticker} ${m.change_pct.toFixed(1)}% ($${m.price})`).join("\n");
    return `🔥 MOVERS — ${data.date}\n\n${g || "Quiet day"}\n\n${l || "Quiet day"}\n\n#stocks #trading`;
  })();

  const sectorsText = (() => {
    const leading = data.sectors.filter(s => s.change_pct > 0).slice(0, 4).map(s => `${s.sector} +${s.change_pct.toFixed(1)}%`).join(", ");
    const lagging = data.sectors.filter(s => s.change_pct < 0).slice(-4).map(s => `${s.sector} ${s.change_pct.toFixed(1)}%`).join(", ");
    return `📊 SECTOR WATCH — ${data.date}\n\n🟢 Leading: ${leading || "—"}\n🔴 Lagging: ${lagging || "—"}\n\n#trading #markets`;
  })();

  const volumeText = (() => {
    if (!data.volume_spikes?.length) return "";
    const rows = data.volume_spikes.slice(0, 5).map(s => `$${s.ticker} — ${s.volume_ratio.toFixed(0)}x avg volume, ${s.change_pct >= 0 ? "+" : ""}${s.change_pct.toFixed(1)}%`).join("\n");
    return `🐳 UNUSUAL ACTIVITY\n\n${rows}\n\nSmart money moving. 👀`;
  })();

  const picksText = (() => {
    if (!data.ai_picks.length) return "";
    const rows = data.ai_picks.map(p => {
      const icon = p.direction === "bullish" ? "🟢" : p.direction === "bearish" ? "🔴" : "⚪";
      return `${icon} $${p.ticker} (${p.direction}) — ${p.reason}`;
    }).join("\n");
    return `🤖 AI PICKS — ${data.date}\n\n${rows}\n\n#stocks #fintwit`;
  })();

  const headlinesText = (() => {
    if (!data.headlines.length) return "";
    const rows = data.headlines.slice(0, 8).map(h => {
      const icon = h.sentiment === "bullish" ? "🟢" : h.sentiment === "bearish" ? "🔴" : "⚪";
      return `${icon} $${h.ticker}: ${h.title}`;
    }).join("\n");
    return `📰 HEADLINES — ${data.date}\n\n${rows}\n\n#stocks #trading`;
  })();

  return (
    <div className="space-y-4 anim-fade-in">
      {/* Market Mood Banner */}
      <div className="relative text-center py-6" style={{ background: moodBg, border: `1px solid ${moodColor}30` }}>
        <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: `linear-gradient(90deg, transparent, ${moodColor}, transparent)` }} />
        <div className="text-[9px] font-[Josefin_Sans] uppercase tracking-[0.3em] mb-2" style={{ color: moodColor }}>{data.date}</div>
        <div className="text-[42px] font-[Poiret_One] tracking-[0.12em] leading-none" style={{ color: moodColor }}>{data.market_mood.toUpperCase()}</div>
      </div>

      {/* Macro Pulse */}
      {data.macro && data.macro.length > 0 && <MacroPulse indicators={data.macro} t={t} />}

      {/* Fear & Greed */}
      {data.fear_greed && <div ref={fearRef}><FearGreedGauge data={data.fear_greed} t={t} /><div className="flex justify-end -mt-2 mb-3 px-4"><CopyImageBtn targetRef={fearRef} /></div></div>}

      {/* Market Breadth */}
      {data.breadth && <BreadthPanel data={data.breadth} t={t} />}

      {/* Morning Brief */}
      <Mod title={t.morningBrief}>
        <div className="text-[11px] font-[Lato] text-[#F5E6CA]/70 leading-relaxed font-light whitespace-pre-line">{data.summary}</div>
        <div className="mt-2 flex items-center justify-between">
          <div className="text-[8px] font-[DM_Mono] text-[#4A4D55]">{t.lastUpdated}: {data.generated_at.slice(11, 16)}</div>
          <CopyBtn text={data.social_posts?.brief || data.summary.slice(0, 280)} />
        </div>
      </Mod>

      {/* Top Movers */}
      <div ref={moversRef}>
      <Mod title={<div className="flex items-center justify-between w-full"><span>{t.topMovers}</span><div className="flex gap-1"><CopyBtn text={data.social_posts?.movers || moversText} /><CopyImageBtn targetRef={moversRef} /></div></div>}>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] mb-2" style={{ color: "#006B3F" }}>{t.gainersLabel}</div>
            {data.gainers.map((g, i) => {
              const volBar = Math.min((g.volume_ratio ?? 1) / 3, 1) * 100;
              return (
              <button key={i} onClick={() => onSelectTicker(g.ticker)} className="w-full flex justify-between items-center py-[6px] border-b last:border-b-0 hover:bg-[#006B3F]/5 transition-colors text-left" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-[DM_Mono] font-medium text-[#F5E6CA]">{g.ticker}</span>
                  <div className="w-[30px] h-[4px] rounded-full overflow-hidden" style={{ background: "#2A2A3E" }}>
                    <div className="h-full rounded-full" style={{ width: `${volBar}%`, background: "#006B3F" }} />
                  </div>
                </div>
                <div className="text-right">
                  <span className="text-[11px] font-[DM_Mono] font-bold" style={{ color: "#006B3F" }}>+{g.change_pct.toFixed(1)}%</span>
                  <span className="text-[9px] font-[DM_Mono] text-[#8B8E96] ml-2">${g.price}</span>
                </div>
              </button>
              );
            })}
          </div>
          <div>
            <div className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] mb-2" style={{ color: "#8B0000" }}>{t.losersLabel}</div>
            {data.losers.map((l, i) => {
              const volBar = Math.min((l.volume_ratio ?? 1) / 3, 1) * 100;
              return (
              <button key={i} onClick={() => onSelectTicker(l.ticker)} className="w-full flex justify-between items-center py-[6px] border-b last:border-b-0 hover:bg-[#8B0000]/5 transition-colors text-left" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-[DM_Mono] font-medium text-[#F5E6CA]">{l.ticker}</span>
                  <div className="w-[30px] h-[4px] rounded-full overflow-hidden" style={{ background: "#2A2A3E" }}>
                    <div className="h-full rounded-full" style={{ width: `${volBar}%`, background: "#8B0000" }} />
                  </div>
                </div>
                <div className="text-right">
                  <span className="text-[11px] font-[DM_Mono] font-bold" style={{ color: "#8B0000" }}>{l.change_pct.toFixed(1)}%</span>
                  <span className="text-[9px] font-[DM_Mono] text-[#8B8E96] ml-2">${l.price}</span>
                </div>
              </button>
              );
            })}
          </div>
        </div>
      </Mod>
      </div>

      {/* Sector Heat Grid (new visualization) */}
      <div ref={sectorRef}>
      <SectorCorrelationGrid sectors={data.sectors} t={t} />

      {/* Sector Heatmap (bar chart) */}
      <Mod title={<div className="flex items-center justify-between w-full"><span>{t.sectorMap}</span><div className="flex gap-1"><CopyBtn text={data.social_posts?.sectors || sectorsText} /><CopyImageBtn targetRef={sectorRef} /></div></div>}>
        <div className="space-y-1">
          {data.sectors.map((s, i) => {
            const pct = s.change_pct;
            const barWidth = Math.min(Math.abs(pct) * 15, 100);
            const barColor = pct >= 0 ? "#006B3F" : "#8B0000";
            return (
              <div key={i} className="flex items-center gap-2 py-[3px]">
                <span className="text-[9px] font-[Lato] text-[#8B8E96] w-[90px] shrink-0 truncate">{s.sector}</span>
                <div className="flex-1 h-[6px] relative" style={{ background: "#2A2A3E" }}>
                  <div className="absolute top-0 h-full" style={{ width: `${barWidth}%`, background: barColor, left: pct >= 0 ? "50%" : `${50 - barWidth}%`, ...(pct >= 0 ? {} : { right: "50%" }) }} />
                  <div className="absolute top-0 left-1/2 w-px h-full" style={{ background: "rgba(212,175,55,0.15)" }} />
                </div>
                <span className="text-[9px] font-[DM_Mono] w-[45px] text-right" style={{ color: barColor }}>{pct >= 0 ? "+" : ""}{pct.toFixed(1)}%</span>
              </div>
            );
          })}
        </div>
      </Mod>
      </div>

      {/* AI Picks */}
      {data.ai_picks.length > 0 && (
        <div ref={picksRef}>
        <Mod title={<div className="flex items-center justify-between w-full"><span>{t.aiPicks} — {t.worthWatching}</span><div className="flex gap-1"><CopyBtn text={data.social_posts?.picks || picksText} /><CopyImageBtn targetRef={picksRef} /></div></div>}>
          {data.ai_picks.map((p, i) => (
            <button key={i} onClick={() => onSelectTicker(p.ticker)} className="w-full text-left py-2 border-b last:border-b-0 hover:bg-[#D4AF37]/4 transition-colors" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[12px] font-[DM_Mono] font-bold text-[#F5E6CA]">{p.ticker}</span>
                <span className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.1em] px-1.5 py-0.5" style={{ color: dirColor(p.direction), background: `${dirColor(p.direction)}15`, border: `1px solid ${dirColor(p.direction)}30` }}>{p.direction}</span>
              </div>
              <div className="text-[10px] font-[Lato] text-[#F5E6CA]/60 font-light">{p.reason}</div>
              <div className="text-[9px] font-[Lato] text-[#C5A255]/50 mt-0.5">{t.catalyst}: {p.catalyst}</div>
            </button>
          ))}
        </Mod>
        </div>
      )}

      {/* Economic Calendar */}
      {data.econ_calendar && data.econ_calendar.length > 0 && <EconCalendar events={data.econ_calendar} t={t} zh={zh} />}

      {/* Volume Spikes */}
      {data.volume_spikes && data.volume_spikes.length > 0 && (
        <Mod title={<div className="flex items-center justify-between w-full"><span>{t.volumeSpikes}</span><CopyBtn text={data.social_posts?.volume || volumeText} /></div>}>
          {data.volume_spikes.map((s, i) => (
            <button key={i} onClick={() => onSelectTicker(s.ticker)} className="w-full flex justify-between items-center py-[6px] border-b last:border-b-0 hover:bg-[#D4AF37]/4 transition-colors text-left" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-[DM_Mono] font-medium text-[#F5E6CA]">{s.ticker}</span>
                <span className="text-[8px] font-[Josefin_Sans] font-bold text-[#D4AF37] uppercase px-1 py-0.5" style={{ background: "rgba(212,175,55,0.08)", border: "1px solid rgba(212,175,55,0.2)" }}>{s.volume_ratio.toFixed(0)}x vol</span>
              </div>
              <span className="text-[10px] font-[DM_Mono] font-medium" style={{ color: s.change_pct >= 0 ? "#006B3F" : "#8B0000" }}>{s.change_pct >= 0 ? "+" : ""}{s.change_pct.toFixed(1)}%</span>
            </button>
          ))}
        </Mod>
      )}

      {/* Options Flow */}
      {data.options_flow && data.options_flow.length > 0 && <OptionsFlowPanel flows={data.options_flow} onSelectTicker={onSelectTicker} t={t} />}

      {/* Orallexa Thread */}
      {data.orallexa_thread && data.orallexa_thread.length > 0 && (
        <Mod title={t.oralexaThread}>
          <div className="space-y-2 mb-3">
            {data.orallexa_thread.map((tw, i) => (
              <div key={i} className="relative group">
                <div className="text-[11px] font-[Lato] text-[#F5E6CA]/75 leading-relaxed py-2 px-3 font-light" style={{ background: "rgba(212,175,55,0.03)", borderLeft: `2px solid ${i === 0 ? "#D4AF37" : "rgba(212,175,55,0.15)"}` }}>
                  <span className="text-[8px] font-[DM_Mono] text-[#4A4D55] mr-2">{i + 1}/{data.orallexa_thread!.length}</span>
                  {tw}
                </div>
                <button onClick={() => { copyWithAttribution(tw); }} className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity text-[8px] font-[Josefin_Sans] text-[#C5A255] hover:text-[#FFD700] px-1.5 py-0.5 uppercase" style={{ background: "rgba(26,26,46,0.9)", border: "1px solid rgba(212,175,55,0.2)" }} aria-label={t.copy}>{t.copy}</button>
              </div>
            ))}
          </div>
          <button onClick={() => { const full = data.orallexa_thread!.map((tw, i) => `${i + 1}/${data.orallexa_thread!.length} ${tw}`).join("\n\n"); copyWithAttribution(full); }}
            className="w-full py-2 text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#D4AF37] hover:text-[#FFD700] transition-colors" style={{ background: "rgba(212,175,55,0.06)", border: "1px solid rgba(212,175,55,0.2)" }}>
            {t.copyFullThread}
          </button>
        </Mod>
      )}

      {/* Headlines */}
      <Mod title={<div className="flex items-center justify-between w-full"><span>{t.marketIntel}</span><CopyBtn text={headlinesText} /></div>}>
        {data.headlines.map((h, i) => (
          <div key={i} className="py-[6px] border-b last:border-b-0" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
            {h.url ? (
              <a href={h.url} target="_blank" rel="noopener noreferrer" className="flex justify-between items-start gap-2 group hover:bg-[#D4AF37]/4 -mx-1 px-1 transition-colors">
                <div className="min-w-0">
                  <span className="text-[10px] font-[Lato] text-[#F5E6CA]/60 group-hover:text-[#F5E6CA] transition-colors leading-snug block font-light">{h.title}</span>
                  <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">{h.ticker} · {h.provider}</span>
                </div>
                <span className={`text-[8px] font-[Josefin_Sans] font-bold uppercase shrink-0 ${h.sentiment === "bullish" ? "text-[#006B3F]" : h.sentiment === "bearish" ? "text-[#8B0000]" : "text-[#8B8E96]"}`}>{h.sentiment}</span>
              </a>
            ) : (
              <div className="flex justify-between items-start gap-2">
                <span className="text-[10px] font-[Lato] text-[#F5E6CA]/60 font-light leading-snug">{h.title}</span>
                <span className={`text-[8px] font-[Josefin_Sans] font-bold uppercase shrink-0 ${h.sentiment === "bullish" ? "text-[#006B3F]" : h.sentiment === "bearish" ? "text-[#8B0000]" : "text-[#8B8E96]"}`}>{h.sentiment}</span>
              </div>
            )}
          </div>
        ))}
      </Mod>

      {/* Share Row */}
      <ShareRow briefText={data.social_posts?.brief || data.summary.slice(0, 240)} t={t} />
    </div>
  );
}
