"use client";

import { useEffect, useRef, useState } from "react";
import type { BreakingSignal } from "../types";

interface Toast {
  id: string;
  signal: BreakingSignal;
  exiting: boolean;
}

export function SignalToast({ signals, onSelect }: {
  signals: BreakingSignal[];
  onSelect: (ticker: string) => void;
}) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seenRef = useRef<Set<string>>(new Set());

  // Sync external signals prop → internal toast state (legitimate external-system sync)
  useEffect(() => {
    for (const sig of signals) {
      const key = `${sig.ticker}-${sig.type}-${sig.timestamp}`;
      if (seenRef.current.has(key)) continue;
      seenRef.current.add(key);
      const id = crypto.randomUUID();
      // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing external signal prop to toast queue
      setToasts(prev => [{ id, signal: sig, exiting: false }, ...prev].slice(0, 3));

      // Auto-dismiss after 8s
      setTimeout(() => {
        setToasts(prev => prev.map(t => t.id === id ? { ...t, exiting: true } : t));
        setTimeout(() => {
          setToasts(prev => prev.filter(t => t.id !== id));
        }, 300);
      }, 8000);
    }
  }, [signals]);

  const dismiss = (id: string) => {
    setToasts(prev => prev.map(t => t.id === id ? { ...t, exiting: true } : t));
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 300);
  };

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none" role="region" aria-label="Signal notifications" aria-live="polite" style={{ maxWidth: 340 }}>
      {toasts.map(toast => {
        const s = toast.signal;
        const isBullish = s.direction === "bullish";
        const color = isBullish ? "#006B3F" : s.direction === "bearish" ? "#8B0000" : "#D4AF37";
        const icon = s.type === "volume_spike" ? "VOL" : s.type === "sentiment_shift" ? "SENT" : "BRK";

        return (
          <div key={toast.id}
            role="alert"
            tabIndex={0}
            className={`pointer-events-auto cursor-pointer ${toast.exiting ? "anim-slide-left" : "anim-slide-right"} focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#FFD700]`}
            onClick={() => { onSelect(s.ticker); dismiss(toast.id); }}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(s.ticker); dismiss(toast.id); } }}
            style={{
              background: "#1A1A2E",
              border: `1px solid ${color}40`,
              borderLeft: `3px solid ${color}`,
              opacity: toast.exiting ? 0 : 1,
              transition: "opacity 0.3s",
            }}>
            {/* Gold accent line */}
            <div className="h-[1px]" style={{ background: `linear-gradient(90deg, ${color}, transparent)` }} />
            <div className="flex items-start gap-2 px-3 py-2">
              {/* Type badge */}
              <span className="text-[7px] font-[Josefin_Sans] font-bold uppercase tracking-[0.08em] px-1.5 py-0.5 mt-0.5 shrink-0"
                style={{ color, background: `${color}15`, border: `1px solid ${color}30` }}>
                {icon}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-[DM_Mono] font-bold text-[#F5E6CA]">{s.ticker}</span>
                  {s.severity === "high" && (
                    <span className="w-[4px] h-[4px] rotate-45" style={{ background: "#D4AF37" }} />
                  )}
                </div>
                <div className="text-[9px] font-[Lato] text-[#F5E6CA]/60 font-light mt-0.5 truncate">{s.message}</div>
              </div>
              {/* Dismiss */}
              <button type="button" onClick={(e) => { e.stopPropagation(); dismiss(toast.id); }}
                className="text-[#4A4D55] hover:text-[#8B8E96] transition-colors shrink-0 mt-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#FFD700]"
                aria-label="Dismiss signal alert">
                <svg width="10" height="10" viewBox="0 0 10 10"><path d="M1 1L9 9M9 1L1 9" stroke="currentColor" strokeWidth="1.5" /></svg>
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
