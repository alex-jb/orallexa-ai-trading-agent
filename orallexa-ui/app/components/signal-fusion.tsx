"use client";

import type { SignalFusion } from "../types";
import { Mod } from "./atoms";

const SOURCE_LABELS: Record<string, { en: string; zh: string; icon: string }> = {
  technical:      { en: "Technical",     zh: "技术面",   icon: "📈" },
  ml_ensemble:    { en: "ML Ensemble",   zh: "ML集成",   icon: "🤖" },
  news_sentiment: { en: "News",          zh: "新闻情绪",  icon: "📰" },
  options_flow:   { en: "Options",       zh: "期权异动",  icon: "🎯" },
  institutional:  { en: "Institutional", zh: "机构",     icon: "🏦" },
};

function ScoreBar({ score, weight }: { score: number; weight: number }) {
  const color = score > 10 ? "#006B3F" : score < -10 ? "#8B0000" : "#D4AF37";
  const barLeft = score >= 0 ? 50 : 50 + score / 2;
  const barWidth = Math.abs(score) / 2;
  const opacity = Math.max(0.3, weight);

  return (
    <div className="relative h-2 w-full" style={{ background: "rgba(42,42,62,0.6)" }}>
      <div className="absolute top-0 bottom-0 w-px left-1/2" style={{ background: "rgba(212,175,55,0.2)" }} />
      <div
        className="absolute top-0 bottom-0 transition-all duration-500"
        style={{
          left: `${barLeft}%`,
          width: `${barWidth}%`,
          background: color,
          opacity,
        }}
      />
    </div>
  );
}

export function SignalFusionCard({ fusion, t, zh }: {
  fusion: SignalFusion | null; t: Record<string, string>; zh: boolean;
}) {
  if (!fusion || !fusion.sources || fusion.n_sources === 0) return null;

  const convColor = fusion.conviction > 15 ? "#006B3F" : fusion.conviction < -15 ? "#8B0000" : "#D4AF37";
  const convBg = fusion.conviction > 15 ? "rgba(0,107,63,0.08)" : fusion.conviction < -15 ? "rgba(139,0,0,0.08)" : "rgba(212,175,55,0.06)";

  return (
    <Mod title={t.signalFusion}>
      {/* Conviction header */}
      <div className="flex items-center justify-between mb-3 px-2 py-2" style={{ background: convBg }}>
        <div>
          <span className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#8B8E96] mr-2">
            {t.fusionConviction}
          </span>
          <span className="text-[18px] font-[DM_Mono] font-bold" style={{ color: convColor }}>
            {fusion.conviction > 0 ? "+" : ""}{fusion.conviction}
          </span>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-[10px] font-[Josefin_Sans] font-bold uppercase" style={{ color: convColor }}>
            {fusion.direction}
          </span>
          <span className="text-[8px] font-[DM_Mono] text-[#8B8E96]">
            {fusion.n_sources} {zh ? "个来源" : "sources"} · {fusion.confidence}% {zh ? "一致" : "agree"}
          </span>
        </div>
      </div>

      {/* Per-source breakdown */}
      <div className="space-y-2">
        {Object.entries(fusion.sources)
          .filter(([, s]) => s.available)
          .sort(([, a], [, b]) => Math.abs(b.score) - Math.abs(a.score))
          .map(([key, source]) => {
            const label = SOURCE_LABELS[key] || { en: key, zh: key, icon: "📊" };
            const scoreColor = source.score > 10 ? "#006B3F" : source.score < -10 ? "#8B0000" : "#D4AF37";

            return (
              <div key={key}>
                <div className="flex items-center justify-between mb-0.5">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px]">{label.icon}</span>
                    <span className="text-[9px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.1em] text-[#F5E6CA]">
                      {zh ? label.zh : label.en}
                    </span>
                    <span className="text-[7px] font-[DM_Mono] text-[#4A4D55]">
                      w={((source.normalized_weight || 0) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <span className="text-[11px] font-[DM_Mono] font-medium" style={{ color: scoreColor }}>
                    {source.score > 0 ? "+" : ""}{source.score}
                  </span>
                </div>
                <ScoreBar score={source.score} weight={source.normalized_weight || 0} />

                {/* Extra details for options */}
                {key === "options_flow" && source.pc_ratio !== undefined && (
                  <div className="flex gap-3 mt-0.5 pl-5">
                    <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">P/C: {source.pc_ratio}</span>
                    {source.max_pain && (
                      <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">
                        Max Pain: ${source.max_pain}
                      </span>
                    )}
                    {(source.unusual_calls?.length || 0) > 0 && (
                      <span className="text-[8px] font-[DM_Mono] text-[#006B3F]">
                        {source.unusual_calls!.length} unusual calls
                      </span>
                    )}
                    {(source.unusual_puts?.length || 0) > 0 && (
                      <span className="text-[8px] font-[DM_Mono] text-[#8B0000]">
                        {source.unusual_puts!.length} unusual puts
                      </span>
                    )}
                  </div>
                )}

                {/* Extra details for institutional */}
                {key === "institutional" && (
                  <div className="flex gap-3 mt-0.5 pl-5">
                    {source.short_pct !== undefined && source.short_pct > 0 && (
                      <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">
                        Short: {source.short_pct}%
                      </span>
                    )}
                    {(source.insider_transactions?.length || 0) > 0 && (
                      <span className="text-[8px] font-[DM_Mono] text-[#8B8E96]">
                        {source.insider_transactions!.length} insider txns
                      </span>
                    )}
                  </div>
                )}

                {/* Technical signals */}
                {key === "technical" && source.signals && source.signals.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-0.5 pl-5">
                    {source.signals.map((sig, i) => (
                      <span key={i} className="text-[7px] font-[DM_Mono] text-[#4A4D55] px-1 py-0.5"
                        style={{ background: "rgba(42,42,62,0.5)" }}>
                        {sig}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </Mod>
  );
}
