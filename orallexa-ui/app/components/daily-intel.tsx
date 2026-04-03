"use client";

import type { DailyIntelData } from "../types";
import { copyWithAttribution } from "../types";
import { Mod, CopyBtn } from "./atoms";

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

      {/* Morning Brief */}
      <Mod title={t.morningBrief}>
        <div className="text-[11px] font-[Lato] text-[#F5E6CA]/70 leading-relaxed font-light whitespace-pre-line">{data.summary}</div>
        <div className="mt-2 flex items-center justify-between">
          <div className="text-[8px] font-[DM_Mono] text-[#4A4D55]">{t.lastUpdated}: {data.generated_at.slice(11, 16)}</div>
          <CopyBtn text={data.social_posts?.brief || data.summary.slice(0, 280)} />
        </div>
      </Mod>

      {/* Top Movers */}
      <Mod title={<div className="flex items-center justify-between w-full"><span>{t.topMovers}</span><CopyBtn text={data.social_posts?.movers || moversText} /></div>}>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] mb-2" style={{ color: "#006B3F" }}>{zh ? "涨幅榜" : "Gainers"}</div>
            {data.gainers.map((g, i) => (
              <button key={i} onClick={() => onSelectTicker(g.ticker)} className="w-full flex justify-between items-center py-[6px] border-b last:border-b-0 hover:bg-[#006B3F]/5 transition-colors text-left" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
                <span className="text-[11px] font-[DM_Mono] font-medium text-[#F5E6CA]">{g.ticker}</span>
                <div className="text-right">
                  <span className="text-[11px] font-[DM_Mono] font-bold" style={{ color: "#006B3F" }}>+{g.change_pct.toFixed(1)}%</span>
                  <span className="text-[9px] font-[DM_Mono] text-[#8B8E96] ml-2">${g.price}</span>
                </div>
              </button>
            ))}
          </div>
          <div>
            <div className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] mb-2" style={{ color: "#8B0000" }}>{zh ? "跌幅榜" : "Losers"}</div>
            {data.losers.map((l, i) => (
              <button key={i} onClick={() => onSelectTicker(l.ticker)} className="w-full flex justify-between items-center py-[6px] border-b last:border-b-0 hover:bg-[#8B0000]/5 transition-colors text-left" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
                <span className="text-[11px] font-[DM_Mono] font-medium text-[#F5E6CA]">{l.ticker}</span>
                <div className="text-right">
                  <span className="text-[11px] font-[DM_Mono] font-bold" style={{ color: "#8B0000" }}>{l.change_pct.toFixed(1)}%</span>
                  <span className="text-[9px] font-[DM_Mono] text-[#8B8E96] ml-2">${l.price}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </Mod>

      {/* Sector Heatmap */}
      <Mod title={<div className="flex items-center justify-between w-full"><span>{t.sectorMap}</span><CopyBtn text={data.social_posts?.sectors || sectorsText} /></div>}>
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

      {/* AI Picks */}
      {data.ai_picks.length > 0 && (
        <Mod title={<div className="flex items-center justify-between w-full"><span>{t.aiPicks} — {t.worthWatching}</span><CopyBtn text={data.social_posts?.picks || picksText} /></div>}>
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
      )}

      {/* Volume Spikes */}
      {data.volume_spikes && data.volume_spikes.length > 0 && (
        <Mod title={<div className="flex items-center justify-between w-full"><span>{zh ? "成交量异动" : "Volume Spikes"}</span><CopyBtn text={data.social_posts?.volume || volumeText} /></div>}>
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

      {/* Orallexa Thread */}
      {data.orallexa_thread && data.orallexa_thread.length > 0 && (
        <Mod title={zh ? "Orallexa 推文串" : "Orallexa Thread"}>
          <div className="space-y-2 mb-3">
            {data.orallexa_thread.map((tw, i) => (
              <div key={i} className="relative group">
                <div className="text-[11px] font-[Lato] text-[#F5E6CA]/75 leading-relaxed py-2 px-3 font-light" style={{ background: "rgba(212,175,55,0.03)", borderLeft: `2px solid ${i === 0 ? "#D4AF37" : "rgba(212,175,55,0.15)"}` }}>
                  <span className="text-[8px] font-[DM_Mono] text-[#4A4D55] mr-2">{i + 1}/{data.orallexa_thread!.length}</span>
                  {tw}
                </div>
                <button onClick={() => { copyWithAttribution(tw); }} className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity text-[8px] font-[Josefin_Sans] text-[#C5A255] hover:text-[#FFD700] px-1.5 py-0.5 uppercase" style={{ background: "rgba(26,26,46,0.9)", border: "1px solid rgba(212,175,55,0.2)" }} aria-label="Copy post">Copy</button>
              </div>
            ))}
          </div>
          <button onClick={() => { const full = data.orallexa_thread!.map((tw, i) => `${i + 1}/${data.orallexa_thread!.length} ${tw}`).join("\n\n"); copyWithAttribution(full); }}
            className="w-full py-2 text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#D4AF37] hover:text-[#FFD700] transition-colors" style={{ background: "rgba(212,175,55,0.06)", border: "1px solid rgba(212,175,55,0.2)" }}>
            {zh ? "复制完整推文串" : "Copy Full Thread"}
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
    </div>
  );
}
