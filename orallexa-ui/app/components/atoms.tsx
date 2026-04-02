"use client";

import { useState } from "react";
import { copyWithAttribution } from "../types";

/* ── Sunburst / fan SVG decoration ───────────────────────────────────── */
export function DecoFan({ size = 60, opacity = 0.06 }: { size?: number; opacity?: number }) {
  return (
    <svg width={size} height={size / 2} viewBox="0 0 120 60" style={{ opacity }}>
      {Array.from({ length: 9 }).map((_, i) => {
        const angle = -80 + i * 20;
        const x2 = 60 + 55 * Math.cos((angle * Math.PI) / 180);
        const y2 = 60 + 55 * Math.sin((angle * Math.PI) / 180);
        return <line key={i} x1="60" y1="60" x2={x2} y2={y2} stroke="#D4AF37" strokeWidth="1" />;
      })}
    </svg>
  );
}

export function GoldRule({ strength = 25 }: { strength?: number }) {
  const o = strength / 100;
  return (
    <div className="flex items-center gap-3 my-3 px-6">
      <div className="flex-1 h-px" style={{ background: `linear-gradient(90deg, transparent, rgba(212,175,55,${o}), transparent 80%)` }} />
      <div className="flex gap-1">
        <div className="w-[4px] h-[4px] rotate-45" style={{ background: `rgba(212,175,55,${o * 0.8})` }} />
        <div className="w-[6px] h-[6px] rotate-45" style={{ border: `1px solid rgba(212,175,55,${o * 1.2})` }} />
        <div className="w-[4px] h-[4px] rotate-45" style={{ background: `rgba(212,175,55,${o * 0.8})` }} />
      </div>
      <div className="flex-1 h-px" style={{ background: `linear-gradient(90deg, transparent 20%, rgba(212,175,55,${o}), transparent)` }} />
    </div>
  );
}

export function Heading({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 py-0.5">
      <div className="flex gap-0.5">
        <div className="w-1 h-1 rotate-45" style={{ background: "#D4AF37" }} />
        <div className="w-1.5 h-1.5 rotate-45 border" style={{ borderColor: "#D4AF37" }} />
      </div>
      <h3 className="font-[Josefin_Sans] text-[10px] font-semibold uppercase tracking-[0.28em] whitespace-nowrap px-1"
        style={{ background: "linear-gradient(135deg, #D4AF37, #FFD700, #C5A255)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
        {children}
      </h3>
      <div className="h-px flex-1" style={{ background: "linear-gradient(90deg, rgba(212,175,55,0.3), transparent)" }} />
    </div>
  );
}

/* Art Deco card with stepped corner ornaments */
export function Mod({ title, children }: { title: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="relative mb-3" style={{ background: "#1A1A2E" }}>
      <div className="absolute inset-0 border pointer-events-none" style={{ borderColor: "rgba(212,175,55,0.15)" }} />
      <div className="absolute inset-[3px] border pointer-events-none" style={{ borderColor: "rgba(212,175,55,0.06)" }} />
      {[["top-0 left-0", "t-l"], ["top-0 right-0", "t-r"], ["bottom-0 left-0", "b-l"], ["bottom-0 right-0", "b-r"]].map(([pos, key]) => {
        const isTop = key.startsWith("t");
        const isLeft = key.endsWith("l");
        const o = isTop ? 0.5 : 0.25;
        return (
          <div key={key} className={`absolute ${pos} pointer-events-none`}>
            <div className={`absolute ${isLeft ? "left-0" : "right-0"} ${isTop ? "top-0" : "bottom-0"} w-5 h-px`} style={{ background: `rgba(212,175,55,${o})` }} />
            <div className={`absolute ${isLeft ? "left-0" : "right-0"} ${isTop ? "top-0" : "bottom-0"} w-px h-5`} style={{ background: `rgba(212,175,55,${o})` }} />
            <div className={`absolute ${isLeft ? "left-[6px]" : "right-[6px]"} ${isTop ? "top-[6px]" : "bottom-[6px]"} w-2 h-px`} style={{ background: `rgba(212,175,55,${o * 0.5})` }} />
            <div className={`absolute ${isLeft ? "left-[6px]" : "right-[6px]"} ${isTop ? "top-[6px]" : "bottom-[6px]"} w-px h-2`} style={{ background: `rgba(212,175,55,${o * 0.5})` }} />
          </div>
        );
      })}
      <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: "linear-gradient(90deg, transparent, #D4AF37, transparent)" }} />
      <div className="relative px-4 pt-4 pb-2 border-b" style={{ borderColor: "rgba(212,175,55,0.08)" }}><Heading>{title}</Heading></div>
      <div className="relative px-4 py-3">{children}</div>
    </div>
  );
}

export function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex justify-between items-center py-[7px] border-b last:border-b-0" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
      <span className="text-[11px] font-[Lato] text-[#6B6E76]">{label}</span>
      <span className="text-[13px] font-[DM_Mono] font-medium" style={{ color: color ?? "#F5E6CA" }}>{value}</span>
    </div>
  );
}

export function Toggle({ label, open, onToggle, children }: { label: string; open: boolean; onToggle: () => void; children: React.ReactNode; }) {
  return (
    <div className="border-t" style={{ borderColor: "rgba(212,175,55,0.08)" }}>
      <button onClick={onToggle} aria-expanded={open} className="w-full text-left px-7 py-3 text-[10px] font-[Josefin_Sans] text-[#C5A255] uppercase tracking-[0.16em] hover:text-[#FFD700] transition-colors">
        {open ? "▾" : "▸"} {label}
      </button>
      {open && <div className="px-7 pb-4">{children}</div>}
    </div>
  );
}

export function BullIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <defs>
        <linearGradient id="bullGrad" x1="0" y1="0" x2="32" y2="32">
          <stop offset="0%" stopColor="#FFD700" />
          <stop offset="50%" stopColor="#D4AF37" />
          <stop offset="100%" stopColor="#C5A255" />
        </linearGradient>
      </defs>
      {/* Diamond frame (matching logo) */}
      <polygon points="16,2 30,16 16,30 2,16" fill="none" stroke="url(#bullGrad)" strokeWidth="1" opacity="0.6" />
      <polygon points="16,6 26,16 16,26 6,16" fill="none" stroke="url(#bullGrad)" strokeWidth="0.7" opacity="0.3" />
      {/* Geometric bull horns */}
      <path d="M11,14 L9,8 L7,6 L8,7 L10,10 L12,14" fill="url(#bullGrad)" opacity="0.9" />
      <path d="M21,14 L23,8 L25,6 L24,7 L22,10 L20,14" fill="url(#bullGrad)" opacity="0.9" />
      {/* Central orb */}
      <circle cx="16" cy="16" r="4" fill="none" stroke="url(#bullGrad)" strokeWidth="1.2" />
      <circle cx="16" cy="16" r="1.5" fill="#FFD700" opacity="0.7" />
      {/* Snout */}
      <path d="M14,20 L16,23 L18,20" fill="none" stroke="url(#bullGrad)" strokeWidth="0.8" />
    </svg>
  );
}

/* Brand mark using the official logo.svg from /public */
export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <img
      src="/logo.svg"
      alt="Orallexa Capital Intelligence"
      className={compact ? "h-[28px]" : "h-[36px]"}
      style={{ width: "auto" }}
    />
  );
}

export function CopyBtn({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  if (!text) return null;
  return (
    <button onClick={() => { copyWithAttribution(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      className="flex items-center gap-1 px-2 py-1 text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.1em] transition-all hover:text-[#FFD700] shrink-0"
      style={{ color: copied ? "#006B3F" : "#C5A255", background: copied ? "rgba(0,107,63,0.1)" : "rgba(212,175,55,0.06)", border: `1px solid ${copied ? "rgba(0,107,63,0.3)" : "rgba(212,175,55,0.15)"}` }}>
      {copied ? "Copied!" : (label || "Copy for 𝕏")}
    </button>
  );
}
