"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import * as Mock from "./mock-data";
import type { Decision, NewsItem, DeepReport, RiskMgmt, InvestmentPlan, MLModel, ChartInsight, Profile, JournalEntry, MarketSummary, BreakingSignal, WatchlistItem, DailyIntelData } from "./types";
import { T, API, displayDec, subtitleDec, sigLabel, confLabel, riskLabel, decColor, riskColor, sentCls, recBg, decColorJournal, nsSummary, copyWithAttribution } from "./types";
import { DecoFan, GoldRule, Heading, Mod, Row, Toggle, BullIcon, CopyBtn, MLScoreboard, BreakingBanner, MarketStrip, WatchlistGrid } from "./components";

/* Art Deco Design Atoms imported from ./components */

/* ── Probability Bar (Polymarket-inspired) ────────────────────────────── */
function ProbBar({ probs, decision }: { probs: { up: number; neutral: number; down: number }; decision: string }) {
  const up = Math.round(probs.up * 100);
  const neut = Math.round(probs.neutral * 100);
  const down = Math.round(probs.down * 100);
  const hero = decision === "SELL" ? down : up;
  const heroColor = decision === "SELL" ? "#8B0000" : "#006B3F";
  return (
    <div className="px-8 pb-5">
      <div className="flex items-center gap-4 mb-3">
        <div className="text-[36px] font-[DM_Mono] font-bold leading-none" style={{ color: heroColor }}>{hero}%</div>
        <div className="text-[10px] font-[Josefin_Sans] text-[#6B6E76] uppercase tracking-[0.14em] leading-relaxed">
          {decision === "SELL" ? "Downside" : "Upside"}<br/>Probability
        </div>
      </div>
      <div className="flex h-[6px] overflow-hidden" style={{ background: "#2A2A3E" }}>
        <div style={{ width: `${up}%`, background: "linear-gradient(90deg, #006B3F, #00875A)" }} />
        <div style={{ width: `${neut}%`, background: "linear-gradient(90deg, #C5A255, #D4AF37)" }} />
        <div style={{ width: `${down}%`, background: "linear-gradient(90deg, #8B0000, #B22222)" }} />
      </div>
      <div className="flex justify-between mt-1.5 text-[9px] font-[DM_Mono]">
        <span style={{ color: "#006B3F" }}>Up {up}%</span>
        <span style={{ color: "#C5A255" }}>Neutral {neut}%</span>
        <span style={{ color: "#8B0000" }}>Down {down}%</span>
      </div>
    </div>
  );
}

/* ── Bull vs Bear Side-by-Side ────────────────────────────────────────── */
function BullBearPanel({ reasoning, t }: { reasoning: string[]; t: Record<string, string> }) {
  const bull = reasoning.filter(r => r.startsWith("Bull:")).map(r => r.replace(/^Bull:\s*/, ""));
  const bear = reasoning.filter(r => r.startsWith("Bear:")).map(r => r.replace(/^Bear:\s*/, ""));
  const judge = reasoning.filter(r => r.startsWith("Judge:")).map(r => r.replace(/^Judge:\s*/, ""));

  if (bull.length === 0 && bear.length === 0) return null;

  return (
    <div className="border-t" style={{ borderColor: "rgba(212,175,55,0.08)" }}>
      <div className="px-7 pt-4 pb-1">
        <div className="text-[10px] font-[Josefin_Sans] text-[#C5A255] uppercase tracking-[0.16em] mb-3 font-semibold">{t.why}</div>
      </div>
      <div className="grid grid-cols-2 gap-0 px-7 pb-3">
        {/* Bull Column */}
        <div className="pr-3 border-r" style={{ borderColor: "rgba(212,175,55,0.08)" }}>
          <div className="flex items-center gap-1.5 mb-2">
            <div className="w-2 h-2 rounded-full" style={{ background: "#006B3F" }} />
            <span className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.18em]" style={{ color: "#006B3F" }}>Bull Case</span>
          </div>
          {bull.map((b, i) => (
            <div key={i} className="text-[10px] font-[Lato] text-[#F5E6CA]/65 leading-relaxed font-light mb-1.5 pl-3.5" style={{ borderLeft: "2px solid rgba(0,107,63,0.3)" }}>{b}</div>
          ))}
        </div>
        {/* Bear Column */}
        <div className="pl-3">
          <div className="flex items-center gap-1.5 mb-2">
            <div className="w-2 h-2 rounded-full" style={{ background: "#8B0000" }} />
            <span className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.18em]" style={{ color: "#8B0000" }}>Bear Case</span>
          </div>
          {bear.map((b, i) => (
            <div key={i} className="text-[10px] font-[Lato] text-[#F5E6CA]/65 leading-relaxed font-light mb-1.5 pl-3.5" style={{ borderLeft: "2px solid rgba(139,0,0,0.3)" }}>{b}</div>
          ))}
        </div>
      </div>
      {/* Judge Verdict */}
      {judge.length > 0 && (
        <div className="mx-7 mb-4 py-3 px-4" style={{ background: "rgba(212,175,55,0.04)", border: "1px solid rgba(212,175,55,0.12)" }}>
          <div className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.18em] mb-1.5" style={{ color: "#D4AF37" }}>Judge Verdict</div>
          {judge.map((j, i) => <div key={i} className="text-[11px] font-[Lato] text-[#F5E6CA]/75 leading-relaxed font-light">{j}</div>)}
        </div>
      )}
    </div>
  );
}

/* ── Investment Plan Card ─────────────────────────────────────────────── */
function InvestmentPlanCard({ plan, t }: { plan: InvestmentPlan; t: Record<string, string> }) {
  return (
    <div className="border-t" style={{ borderColor: "rgba(212,175,55,0.08)" }}>
      <div className="px-7 pt-4 pb-1">
        <div className="text-[10px] font-[Josefin_Sans] text-[#C5A255] uppercase tracking-[0.16em] mb-3 font-semibold">{t.riskMgmt}</div>
      </div>
      <div className="grid grid-cols-5 gap-2 px-7 pb-3">
        {[
          [t.entry, `$${plan.entry.toFixed(2)}`],
          [t.stop, `$${plan.stop_loss.toFixed(2)}`],
          [t.target, `$${plan.take_profit.toFixed(2)}`],
          [t.size, `${plan.position_pct}%`],
          ["R:R", plan.risk_reward],
        ].map(([l, v]) => (
          <div key={l} className="text-center py-2" style={{ background: "rgba(212,175,55,0.03)" }}>
            <div className="text-[8px] font-[Josefin_Sans] text-[#6B6E76] uppercase tracking-[0.14em] mb-1">{l}</div>
            <div className="text-[13px] font-[DM_Mono] font-medium text-[#F5E6CA]">{v}</div>
          </div>
        ))}
      </div>
      {plan.key_risks.length > 0 && (
        <div className="px-7 pb-4">
          <div className="text-[8px] font-[Josefin_Sans] text-[#6B6E76] uppercase tracking-[0.14em] mb-1.5">Key Risks</div>
          {plan.key_risks.map((r, i) => (
            <div key={i} className="text-[10px] font-[Lato] text-[#8B0000]/70 leading-relaxed font-light">• {r}</div>
          ))}
        </div>
      )}
      {plan.plan_summary && (
        <div className="px-7 pb-4 text-[11px] font-[Lato] text-[#F5E6CA]/60 leading-relaxed font-light whitespace-pre-line">{plan.plan_summary}</div>
      )}
      {plan.analysis_narrative && (
        <details className="px-7 pb-4">
          <summary className="text-[9px] font-[Josefin_Sans] text-[#C5A255] uppercase tracking-[0.12em] cursor-pointer hover:text-[#FFD700] mb-2">Investment Thesis</summary>
          <div className="text-[10px] font-[Lato] text-[#F5E6CA]/50 leading-relaxed font-light whitespace-pre-line italic">{plan.analysis_narrative}</div>
        </details>
      )}
    </div>
  );
}

/* MLScoreboard, BreakingBanner, MarketStrip, WatchlistGrid imported from ./components */

/* ── Decision Card ─────────────────────────────────────────────────────── */
function DecisionCard({ d, asset, strategy, horizon, news, risk, investmentPlan, t, zh }: {
  d: Decision | null; asset: string; strategy: string; horizon: string; news: NewsItem[]; risk: RiskMgmt | null; investmentPlan: InvestmentPlan | null; t: Record<string, string>; zh: boolean;
}) {
  const [showTech, setShowTech] = useState(false);
  const [showRisk, setShowRisk] = useState(false);

  const frameEls = (
    <>
      <div className="absolute inset-0 border pointer-events-none" style={{ borderColor: "rgba(212,175,55,0.2)" }} />
      <div className="absolute inset-[5px] border pointer-events-none" style={{ borderColor: "rgba(212,175,55,0.08)" }} />
      {[0,1,2,3].map(i => { const isTop = i < 2; const isLeft = i % 2 === 0; const o = isTop ? 0.6 : 0.3;
        return (<div key={i} className={`absolute ${isTop?"top-0":"bottom-0"} ${isLeft?"left-0":"right-0"} pointer-events-none`}>
          <div className={`absolute ${isLeft?"left-0":"right-0"} ${isTop?"top-0":"bottom-0"} w-8 h-px`} style={{ background: `linear-gradient(${isLeft?"90deg":"270deg"}, rgba(212,175,55,${o}), transparent)` }} />
          <div className={`absolute ${isLeft?"left-0":"right-0"} ${isTop?"top-0":"bottom-0"} w-px h-8`} style={{ background: `linear-gradient(${isTop?"180deg":"0deg"}, rgba(212,175,55,${o}), transparent)` }} />
          {/* Stepped inner corner */}
          <div className={`absolute ${isLeft?"left-[8px]":"right-[8px]"} ${isTop?"top-[8px]":"bottom-[8px]"} w-3 h-px`} style={{ background: `rgba(212,175,55,${o * 0.4})` }} />
          <div className={`absolute ${isLeft?"left-[8px]":"right-[8px]"} ${isTop?"top-[8px]":"bottom-[8px]"} w-px h-3`} style={{ background: `rgba(212,175,55,${o * 0.4})` }} />
        </div>);
      })}
    </>
  );

  if (!d) {
    return (
      <div className="relative" style={{ background: "linear-gradient(180deg, #1A1A2E 0%, #0D1117 100%)" }}>
        {frameEls}
        <div className="h-[2px]" style={{ background: "linear-gradient(90deg, transparent, #D4AF37, transparent)" }} />
        <div className="relative px-8 pt-8 pb-3">
          <Heading>{t.engineDec}</Heading>
          <div className="mt-6 mb-4 flex items-center justify-center gap-4">
            <DecoFan size={50} opacity={0.08} />
            <div className="text-[48px] font-[Poiret_One] leading-none tracking-[0.15em]" style={{ color: "#2A2A3E" }}>{t.standby}</div>
            <DecoFan size={50} opacity={0.08} />
          </div>
          <div className="text-center text-[12px] font-[Josefin_Sans] text-[#4A4D55] tracking-[0.1em] mb-1 font-light">{t.runToBegin}</div>
          <div className="text-center text-[9px] font-[Josefin_Sans] text-[#6B6E76]/60 tracking-[0.08em] mb-3">
            {zh ? "试试 NVDA · TSLA · QQQ — 左侧快速按钮" : "Try NVDA · TSLA · QQQ — quick buttons on the left"}
          </div>
        </div>
        <GoldRule strength={15} />
        <div className="relative grid grid-cols-3 border-t" style={{ borderColor: "rgba(212,175,55,0.1)" }}>
          {[t.signal, t.confidence, t.risk].map((l, i) => (
            <div key={l} className={`py-6 px-4 text-center ${i < 2 ? "border-r" : ""}`} style={{ borderColor: "rgba(212,175,55,0.08)" }}>
              <div className="text-[9px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.22em] mb-2 text-[#4A4D55]">{l}</div>
              <div className="text-[20px] font-[DM_Mono] font-medium text-[#2A2A3E]">—</div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const ns = nsSummary(news);
  return (
    <div className="relative" style={{ background: "linear-gradient(180deg, #1A1A2E 0%, #0D1117 100%)" }}>
      {frameEls}
      <div className="h-[2px]" style={{ background: "linear-gradient(90deg, transparent, #D4AF37 30%, #FFD700 50%, #D4AF37 70%, transparent)" }} />
      <div className="relative px-8 pt-7 pb-1"><Heading>{t.engineDec}</Heading></div>
      <div className="relative px-8 pt-4 pb-5 flex justify-between items-start">
        <div>
          <div className="text-[50px] font-[Poiret_One] leading-none tracking-[0.08em]" style={{ color: decColor(d.decision), textShadow: `0 0 40px ${decColor(d.decision)}20, 0 0 80px ${decColor(d.decision)}08` }}>{displayDec(d.decision)}</div>
          <div className="text-[12px] font-[Josefin_Sans] text-[#6B6E76] mt-2 font-light tracking-[0.06em]">{subtitleDec(d.decision, zh)}</div>
        </div>
        <div className="text-[10px] font-[Josefin_Sans] text-[#4A4D55] text-right pt-2 uppercase tracking-[0.16em] leading-relaxed font-light">{asset}<br />{strategy} ({horizon})</div>
      </div>
      <div className="relative px-8 pb-5">
        <div className="text-[13px] font-[Lato] text-[#F5E6CA] leading-relaxed py-3 px-5 font-light border-l-[2px]" style={{ borderColor: "#D4AF37", background: recBg(d.decision) }}>{d.recommendation}</div>
      </div>
      {news.length > 0 && <div className="relative px-8 pb-3 text-[10px] font-[Lato] text-[#6B6E76]">News: <span className="font-semibold" style={{ color: ns.color }}>{ns.label}</span> sentiment ({news.length} headlines)</div>}
      {/* Probability Bar */}
      {d.probabilities && <ProbBar probs={d.probabilities} decision={d.decision} />}
      <GoldRule strength={22} />
      <div className="relative grid grid-cols-3 border-t" style={{ borderColor: "rgba(212,175,55,0.1)" }}>
        {[{ h: t.signal, v: sigLabel(d.signal_strength), s: `${d.signal_strength}/100` },
          { h: t.confidence, v: confLabel(d.confidence), s: `${d.confidence.toFixed(0)}%` },
          { h: t.risk, v: riskLabel(d.risk_level), s: d.risk_level, c: riskColor(d.risk_level) },
        ].map((m, i) => (
          <div key={m.h} className={`py-6 px-5 text-center ${i < 2 ? "border-r" : ""}`} style={{ borderColor: "rgba(212,175,55,0.08)" }}>
            <div className="text-[9px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.22em] mb-2 text-[#6B6E76]">{m.h}</div>
            <div className="text-[18px] font-[DM_Mono] font-medium" style={{ color: m.c ?? "#F5E6CA" }}>{m.v}</div>
            <div className="text-[10px] font-[DM_Mono] text-[#4A4D55] mt-1">{m.s}</div>
          </div>
        ))}
      </div>
      {/* Bull vs Bear Side-by-Side */}
      <BullBearPanel reasoning={d.reasoning} t={t} />
      {/* Investment Plan */}
      {investmentPlan && <InvestmentPlanCard plan={investmentPlan} t={t} />}
      <Toggle label={t.techDetails} open={showTech} onToggle={() => setShowTech(!showTech)}>
        {d.reasoning.filter(r => !r.startsWith("Bull:") && !r.startsWith("Bear:") && !r.startsWith("Judge:")).map((r, i) =>
          <div key={i} className="text-[10px] font-[DM_Mono] text-[#6B6E76] py-0.5">{r}</div>
        )}
      </Toggle>
      {risk && <Toggle label={t.riskMgmt} open={showRisk} onToggle={() => setShowRisk(!showRisk)}>
        <div className="grid grid-cols-4 gap-3">
          {([[t.entry, `$${risk.entry.toFixed(2)}`], [t.stop, `$${risk.stop.toFixed(2)}`], [t.target, `$${risk.target.toFixed(2)}`], [t.size, `${risk.size}`]] as const).map(([l, v]) => (
            <div key={l as string} className="text-center">
              <div className="text-[9px] font-[Josefin_Sans] text-[#6B6E76] uppercase tracking-[0.14em] mb-1">{l}</div>
              <div className="text-[14px] font-[DM_Mono] font-medium text-[#F5E6CA]">{v}</div>
            </div>
          ))}
        </div>
      </Toggle>}
      {/* Copy Analysis for X */}
      <div className="relative px-8 py-3 border-t flex justify-end" style={{ borderColor: "rgba(212,175,55,0.08)" }}>
        <CopyBtn text={[
          `$${asset} — AI Trading Signal`,
          ``,
          `Action: ${d.decision}`,
          `Confidence: ${d.confidence.toFixed(0)}%`,
          `Signal: ${d.signal_strength}/100`,
          ``,
          d.reasoning.find(r => r.startsWith("Bull:")) ? `Bull: ${d.reasoning.find(r => r.startsWith("Bull:"))!.slice(5, 120).trim()}...` : "",
          d.reasoning.find(r => r.startsWith("Bear:")) ? `Bear: ${d.reasoning.find(r => r.startsWith("Bear:"))!.slice(5, 120).trim()}...` : "",
          d.reasoning.find(r => r.startsWith("Judge:")) ? `\nVerdict: ${d.reasoning.find(r => r.startsWith("Judge:"))!.slice(6, 150).trim()}` : "",
          ``,
          `Powered by Orallexa AI`,
        ].filter(Boolean).join("\n")} label={zh ? "复制分析结果" : "Copy Analysis for X"} />
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   PAGE
   ══════════════════════════════════════════════════════════════════════════ */
/* CopyBtn and copyWithAttribution imported from ./components and ./types */

/* ── Daily Intel Dashboard ────────────────────────────────────────── */
function DailyIntelView({ data, onSelectTicker, t, zh }: {
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

  // Generate FinTwit-style formatted data text for chart sections
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

      {/* Top Movers — 2 columns */}
      <Mod title={<div className="flex items-center justify-between w-full"><span>{t.topMovers}</span><CopyBtn text={data.social_posts?.movers || moversText} /></div>}>
        <div className="grid grid-cols-2 gap-3">
          {/* Gainers */}
          <div>
            <div className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] mb-2" style={{ color: "#006B3F" }}>
              {zh ? "涨幅榜" : "Gainers"}
            </div>
            {data.gainers.map((g, i) => (
              <button key={i} onClick={() => onSelectTicker(g.ticker)}
                className="w-full flex justify-between items-center py-[6px] border-b last:border-b-0 hover:bg-[#006B3F]/5 transition-colors text-left"
                style={{ borderColor: "rgba(212,175,55,0.06)" }}>
                <span className="text-[11px] font-[DM_Mono] font-medium text-[#F5E6CA]">{g.ticker}</span>
                <div className="text-right">
                  <span className="text-[11px] font-[DM_Mono] font-bold" style={{ color: "#006B3F" }}>+{g.change_pct.toFixed(1)}%</span>
                  <span className="text-[9px] font-[DM_Mono] text-[#6B6E76] ml-2">${g.price}</span>
                </div>
              </button>
            ))}
          </div>
          {/* Losers */}
          <div>
            <div className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] mb-2" style={{ color: "#8B0000" }}>
              {zh ? "跌幅榜" : "Losers"}
            </div>
            {data.losers.map((l, i) => (
              <button key={i} onClick={() => onSelectTicker(l.ticker)}
                className="w-full flex justify-between items-center py-[6px] border-b last:border-b-0 hover:bg-[#8B0000]/5 transition-colors text-left"
                style={{ borderColor: "rgba(212,175,55,0.06)" }}>
                <span className="text-[11px] font-[DM_Mono] font-medium text-[#F5E6CA]">{l.ticker}</span>
                <div className="text-right">
                  <span className="text-[11px] font-[DM_Mono] font-bold" style={{ color: "#8B0000" }}>{l.change_pct.toFixed(1)}%</span>
                  <span className="text-[9px] font-[DM_Mono] text-[#6B6E76] ml-2">${l.price}</span>
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
                <span className="text-[9px] font-[Lato] text-[#6B6E76] w-[90px] shrink-0 truncate">{s.sector}</span>
                <div className="flex-1 h-[6px] relative" style={{ background: "#2A2A3E" }}>
                  <div className="absolute top-0 h-full" style={{
                    width: `${barWidth}%`,
                    background: barColor,
                    left: pct >= 0 ? "50%" : `${50 - barWidth}%`,
                    ...(pct >= 0 ? {} : { right: "50%" }),
                  }} />
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
            <button key={i} onClick={() => onSelectTicker(p.ticker)}
              className="w-full text-left py-2 border-b last:border-b-0 hover:bg-[#D4AF37]/4 transition-colors"
              style={{ borderColor: "rgba(212,175,55,0.06)" }}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[12px] font-[DM_Mono] font-bold text-[#F5E6CA]">{p.ticker}</span>
                <span className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.1em] px-1.5 py-0.5"
                  style={{ color: dirColor(p.direction), background: `${dirColor(p.direction)}15`, border: `1px solid ${dirColor(p.direction)}30` }}>
                  {p.direction}
                </span>
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
            <button key={i} onClick={() => onSelectTicker(s.ticker)}
              className="w-full flex justify-between items-center py-[6px] border-b last:border-b-0 hover:bg-[#D4AF37]/4 transition-colors text-left"
              style={{ borderColor: "rgba(212,175,55,0.06)" }}>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-[DM_Mono] font-medium text-[#F5E6CA]">{s.ticker}</span>
                <span className="text-[8px] font-[Josefin_Sans] font-bold text-[#D4AF37] uppercase px-1 py-0.5" style={{ background: "rgba(212,175,55,0.08)", border: "1px solid rgba(212,175,55,0.2)" }}>
                  {s.volume_ratio.toFixed(0)}x vol
                </span>
              </div>
              <span className="text-[10px] font-[DM_Mono] font-medium" style={{ color: s.change_pct >= 0 ? "#006B3F" : "#8B0000" }}>
                {s.change_pct >= 0 ? "+" : ""}{s.change_pct.toFixed(1)}%
              </span>
            </button>
          ))}
        </Mod>
      )}

      {/* Orallexa Thread — ready to post */}
      {data.orallexa_thread && data.orallexa_thread.length > 0 && (
        <Mod title={zh ? "Orallexa 推文串" : "Orallexa Thread"}>
          <div className="space-y-2 mb-3">
            {data.orallexa_thread.map((tw, i) => (
              <div key={i} className="relative group">
                <div className="text-[11px] font-[Lato] text-[#F5E6CA]/75 leading-relaxed py-2 px-3 font-light"
                  style={{ background: "rgba(212,175,55,0.03)", borderLeft: `2px solid ${i === 0 ? "#D4AF37" : "rgba(212,175,55,0.15)"}` }}>
                  <span className="text-[8px] font-[DM_Mono] text-[#4A4D55] mr-2">{i + 1}/{data.orallexa_thread!.length}</span>
                  {tw}
                </div>
                <button onClick={() => { copyWithAttribution(tw); }}
                  className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity text-[8px] font-[Josefin_Sans] text-[#C5A255] hover:text-[#FFD700] px-1.5 py-0.5 uppercase"
                  style={{ background: "rgba(26,26,46,0.9)", border: "1px solid rgba(212,175,55,0.2)" }}
                  aria-label="Copy post">
                  Copy
                </button>
              </div>
            ))}
          </div>
          <button onClick={() => {
            const full = data.orallexa_thread!.map((tw, i) => `${i + 1}/${data.orallexa_thread!.length} ${tw}`).join("\n\n");
            copyWithAttribution(full);
          }}
            className="w-full py-2 text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#D4AF37] hover:text-[#FFD700] transition-colors"
            style={{ background: "rgba(212,175,55,0.06)", border: "1px solid rgba(212,175,55,0.2)" }}>
            {zh ? "复制完整推文串" : "Copy Full Thread"}
          </button>
        </Mod>
      )}

      {/* Headlines */}
      <Mod title={<div className="flex items-center justify-between w-full"><span>{t.marketIntel}</span><CopyBtn text={headlinesText} /></div>}>
        {data.headlines.map((h, i) => (
          <div key={i} className="py-[6px] border-b last:border-b-0" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
            {h.url ? (
              <a href={h.url} target="_blank" rel="noopener noreferrer"
                className="flex justify-between items-start gap-2 group hover:bg-[#D4AF37]/4 -mx-1 px-1 transition-colors">
                <div className="min-w-0">
                  <span className="text-[10px] font-[Lato] text-[#F5E6CA]/60 group-hover:text-[#F5E6CA] transition-colors leading-snug block font-light">{h.title}</span>
                  <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">{h.ticker} · {h.provider}</span>
                </div>
                <span className={`text-[8px] font-[Josefin_Sans] font-bold uppercase shrink-0 ${h.sentiment === "bullish" ? "text-[#006B3F]" : h.sentiment === "bearish" ? "text-[#8B0000]" : "text-[#6B6E76]"}`}>
                  {h.sentiment}
                </span>
              </a>
            ) : (
              <div className="flex justify-between items-start gap-2">
                <span className="text-[10px] font-[Lato] text-[#F5E6CA]/60 font-light leading-snug">{h.title}</span>
                <span className={`text-[8px] font-[Josefin_Sans] font-bold uppercase shrink-0 ${h.sentiment === "bullish" ? "text-[#006B3F]" : h.sentiment === "bearish" ? "text-[#8B0000]" : "text-[#6B6E76]"}`}>
                  {h.sentiment}
                </span>
              </div>
            )}
          </div>
        ))}
      </Mod>
    </div>
  );
}

export default function Home() {
  const [asset, setAsset] = useState("NVDA");
  const [strategy, setStrategy] = useState("INTRADAY");
  const [horizon, setHorizon] = useState("15M");
  const [context, setContext] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [showFullLog, setShowFullLog] = useState(false);
  const [lang, setLang] = useState<"EN" | "ZH">("EN");
  const t = T[lang];
  const zh = lang === "ZH";

  const [decision, setDecision] = useState<Decision | null>(null);
  const [loading, setLoading] = useState(false);
  const [deepLoading, setDeepLoading] = useState(false);
  const [deepProgress, setDeepProgress] = useState<{ step: number; total: number; label: string; label_zh: string } | null>(null);
  const [error, setError] = useState("");
  const [news, setNews] = useState<NewsItem[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [chartFile, setChartFile] = useState<File | null>(null);
  const [chartInsight, setChartInsight] = useState<ChartInsight | null>(null);
  const [deepReport, setDeepReport] = useState<DeepReport | null>(null);
  const [investmentPlan, setInvestmentPlan] = useState<InvestmentPlan | null>(null);
  const [mlModels, setMlModels] = useState<MLModel[]>([]);
  const [marketSummary, setMarketSummary] = useState<MarketSummary | null>(null);
  const [breakingSignals, setBreakingSignals] = useState<BreakingSignal[]>([]);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [watchlistInput, setWatchlistInput] = useState("NVDA,AAPL,TSLA,MSFT,GOOG");
  const [watchlistItems, setWatchlistItems] = useState<WatchlistItem[]>([]);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [useClaude, setUseClaude] = useState(false);
  const [viewMode, setViewMode] = useState<"signal" | "intel">("signal");
  const [dailyIntel, setDailyIntel] = useState<DailyIntelData | null>(null);
  const [intelLoading, setIntelLoading] = useState(false);
  const [livePrice, setLivePrice] = useState<{ price: number; change_pct: number; prev_close: number; high: number; low: number; timestamp: string } | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const apiDead = useRef(false); // true = backend unreachable, use client mocks
  const [priceFlash, setPriceFlash] = useState<"up" | "down" | null>(null);
  const [lastAnalyzedAt, setLastAnalyzedAt] = useState<string | null>(null);
  const [isOnline, setIsOnline] = useState(true);

  const fetchContext = useCallback(async () => {
    if (apiDead.current) {
      setNews(Mock.mockNews(asset).items as never[]);
      setProfile(Mock.mockProfile() as never);
      setJournal(Mock.mockJournal().entries as never[]);
      return;
    }
    try {
      const [nRes, pRes, jRes] = await Promise.all([
        fetch(`${API}/api/news/${asset}`),
        fetch(`${API}/api/profile`),
        fetch(`${API}/api/journal`),
      ]);
      if (nRes.ok) { const d = await nRes.json(); setNews(d.items || []); }
      if (pRes.ok) { setProfile(await pRes.json()); }
      if (jRes.ok) { const d = await jRes.json(); setJournal(d.entries || []); }
    } catch { setError(lang === "ZH" ? "无法连接后端 API，请检查服务是否启动" : "Cannot connect to API server. Is the backend running?"); }
  }, [asset]);

  useEffect(() => { fetchContext(); }, [fetchContext]);

  // Online/offline detection
  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => setIsOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    setIsOnline(navigator.onLine);
    return () => { window.removeEventListener("online", goOnline); window.removeEventListener("offline", goOffline); };
  }, []);

  // Auto-dismiss errors after 8 seconds
  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setError(""), 8000);
    return () => clearTimeout(timer);
  }, [error]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !loading) { e.preventDefault(); runSignal(); }
      if (e.key === "Escape" && error) { setError(""); }
      if ((e.ctrlKey || e.metaKey) && e.key === "d" && !loading) { e.preventDefault(); runDeep(); }
      if ((e.ctrlKey || e.metaKey) && e.key === "1") { e.preventDefault(); setViewMode("signal"); }
      if ((e.ctrlKey || e.metaKey) && e.key === "2") { e.preventDefault(); setViewMode("intel"); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  });

  // Check demo mode / API availability
  useEffect(() => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 3000);
    fetch(`${API}/api/status`, { signal: ctrl.signal })
      .then(r => r.json())
      .then(d => { clearTimeout(timer); if (d.demo) setIsDemo(true); })
      .catch(() => {
        clearTimeout(timer);
        // API unreachable — activate client-side demo
        apiDead.current = true;
        setIsDemo(true);
        // Seed initial data from mocks
        setNews(Mock.mockNews("NVDA").items as never[]);
        setProfile(Mock.mockProfile() as never);
        setJournal(Mock.mockJournal().entries as never[]);
        setBreakingSignals(Mock.mockBreakingSignals().signals as never[]);
        setDailyIntel(Mock.mockDailyIntel() as never);
      });
  }, []);

  // Poll breaking signals every 60s
  useEffect(() => {
    const fetchBreaking = async () => {
      if (apiDead.current) return;
      try {
        const res = await fetch(`${API}/api/breaking-signals?hours=24&limit=5`);
        if (res.ok) { const d = await res.json(); setBreakingSignals(d.signals || []); }
      } catch { /* background poll, silent fail is OK */ }
    };
    fetchBreaking();
    const interval = setInterval(fetchBreaking, 60000);
    return () => clearInterval(interval);
  }, []);

  // Auto-refresh live price every 30s when enabled
  useEffect(() => {
    if (!autoRefresh) return;
    const fetchLive = async () => {
      try {
        const res = await fetch(`${API}/api/live/${asset}`);
        if (res.ok) {
          const d = await res.json();
          if (d.price) {
            setLivePrice(prev => {
              // Flash animation on price change
              if (prev?.price && d.price !== prev.price) {
                setPriceFlash(d.price > prev.price ? "up" : "down");
                setTimeout(() => setPriceFlash(null), 800);
              }
              return d;
            });
            // Update marketSummary with live data
            if (d.price) {
              setMarketSummary(prev => ({
                ...prev,
                close: d.price,
                change_pct: d.change_pct,
                volume_ratio: prev?.volume_ratio,
                rsi: prev?.rsi,
              }));
            }
          }
        }
      } catch { /* ignore */ }
    };
    fetchLive();
    const interval = setInterval(fetchLive, 30000);
    return () => clearInterval(interval);
  }, [autoRefresh, asset]);

  const runSignal = async () => {
    setLoading(true); setError("");
    try {
      if (apiDead.current) {
        await new Promise(r => setTimeout(r, 600));
        setDecision(Mock.mockAnalyze(asset) as never);
        fetchContext();
        return;
      }
      const form = new FormData();
      form.append("ticker", asset); form.append("mode", strategy.toLowerCase()); form.append("timeframe", horizon.toLowerCase());
      if (context.trim()) form.append("context", context.trim());
      if (useClaude) form.append("use_claude", "true");
      const res = await fetch(`${API}/api/analyze`, { method: "POST", body: form });
      if (!res.ok) { const body = await res.text(); let detail = "Analysis failed"; try { const j = JSON.parse(body); detail = j.detail || detail; } catch {} throw new Error(detail); }
      const data = await res.json();
      setDecision(data); setLastAnalyzedAt(new Date().toLocaleTimeString());
      if (data.breaking_signal) setBreakingSignals(prev => [data.breaking_signal, ...prev].slice(0, 5));
      fetchContext();
    } catch (e) { setError(e instanceof Error ? e.message : "Analysis unavailable. Is the API server running?"); }
    finally { setLoading(false); }
  };

  const runDeep = async () => {
    setLoading(true); setDeepLoading(true); setError(""); setDeepProgress(null);

    if (apiDead.current) {
      try {
        const steps = Mock.DEEP_STEPS;
        for (let i = 0; i < steps.length; i++) {
          setDeepProgress({ step: i + 1, total: steps.length, label: steps[i].label, label_zh: steps[i].label_zh });
          await new Promise(r => setTimeout(r, 700));
        }
        setDeepProgress(null);
        const data = Mock.mockDeepAnalysis(asset);
        setDecision(data as never);
        if (data.reports) setDeepReport(data.reports as never);
        if (data.investment_plan) setInvestmentPlan(data.investment_plan as never);
        if (data.ml_models) setMlModels(data.ml_models as never);
        if (data.summary) setMarketSummary(data.summary as never);
        fetchContext();
      } finally { setLoading(false); setDeepLoading(false); setDeepProgress(null); }
      return;
    }

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 300000);
    try {
      const form = new FormData(); form.append("ticker", asset);
      const res = await fetch(`${API}/api/deep-analysis-stream`, { method: "POST", body: form, signal: ctrl.signal });
      clearTimeout(timer);
      if (!res.ok) { const body = await res.text(); let detail = "Unknown error"; try { const j = JSON.parse(body); detail = j.detail || j.error || body; } catch { detail = body || `HTTP ${res.status}`; } throw new Error(detail.length > 120 ? detail.slice(0, 120) + "..." : detail); }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response stream");
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        let eventType = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) { eventType = line.slice(7).trim(); continue; }
          if (line.startsWith("data: ")) {
            const payload = line.slice(6);
            try {
              const data = JSON.parse(payload);
              if (eventType === "progress") { setDeepProgress(data); }
              else if (eventType === "error") { throw new Error(data.detail || "Analysis failed"); }
              else if (eventType === "done") {
                setDeepProgress(null);
                setDecision(data); setLastAnalyzedAt(new Date().toLocaleTimeString());
                if (data.reports) setDeepReport(data.reports);
                if (data.investment_plan) {
                  const plan = data.investment_plan;
                  if (data.analysis_narrative) plan.analysis_narrative = data.analysis_narrative;
                  setInvestmentPlan(plan);
                }
                if (data.ml_models) setMlModels(data.ml_models);
                if (data.summary) setMarketSummary(data.summary);
                if (data.breaking_signal) setBreakingSignals(prev => [data.breaking_signal, ...prev].slice(0, 5));
                fetchContext();
              }
            } catch (parseErr) { if (eventType === "error") throw parseErr; }
          }
        }
      }
    } catch (e) {
      clearTimeout(timer);
      setDeepProgress(null);
      if (e instanceof DOMException && e.name === "AbortError") { setError(zh ? "深度分析超时 — 请重试或检查 API 连接" : "Deep analysis timed out — please retry or check API connection."); }
      else { setError(`Deep analysis failed: ${e instanceof Error ? e.message : "Is the API server running?"}`); }
    } finally { setLoading(false); setDeepLoading(false); setDeepProgress(null); }
  };

  const analyzeChart = async () => {
    if (!chartFile) return;
    setLoading(true); setError("");
    try {
      if (apiDead.current) {
        await new Promise(r => setTimeout(r, 800));
        const data = Mock.mockChartAnalysis(asset);
        setDecision(data as never);
        setChartInsight(data.chart_insight as never);
        setLoading(false);
        return;
      }
      const form = new FormData();
      form.append("file", chartFile); form.append("ticker", asset); form.append("timeframe", horizon.toLowerCase());
      const res = await fetch(`${API}/api/chart-analysis`, { method: "POST", body: form });
      if (!res.ok) throw new Error("Chart analysis failed");
      const data = await res.json();
      setDecision(data); setLastAnalyzedAt(new Date().toLocaleTimeString());
      const ci = data.chart_insight;
      setChartInsight(ci ? { trend: ci.trend || "—", setup: ci.setup || "—", levels: ci.levels || "—", summary: ci.summary || data.recommendation || "" } : { trend: "—", setup: "—", levels: "—", summary: data.recommendation || "" });
    } catch { setError("Chart analysis unavailable."); }
    setLoading(false);
  };

  const scanWatchlist = async () => {
    setWatchlistLoading(true); setError("");
    try {
      if (apiDead.current) {
        await new Promise(r => setTimeout(r, 500));
        const tks = watchlistInput.split(/[,，\s]+/).map(t => t.trim().toUpperCase()).filter(Boolean);
        setWatchlistItems(Mock.mockWatchlistScan(tks).tickers as never[]);
        return;
      }
      const form = new FormData();
      form.append("tickers", watchlistInput);
      const res = await fetch(`${API}/api/watchlist-scan`, { method: "POST", body: form });
      if (!res.ok) throw new Error("Watchlist scan failed");
      const data = await res.json();
      setWatchlistItems(data.tickers || []);
    } catch (e) { setError(e instanceof Error ? e.message : "Watchlist scan unavailable."); }
    finally { setWatchlistLoading(false); }
  };

  const fetchDailyIntel = useCallback(async (force = false) => {
    setIntelLoading(true);
    try {
      if (apiDead.current) {
        await new Promise(r => setTimeout(r, 300));
        setDailyIntel(Mock.mockDailyIntel() as never);
        return;
      }
      const url = force ? `${API}/api/daily-intel/refresh` : `${API}/api/daily-intel`;
      const res = await fetch(url, force ? { method: "POST" } : {});
      if (res.ok) setDailyIntel(await res.json());
    } catch { if (!apiDead.current) setError(zh ? "每日情报加载失败" : "Daily intel failed to load"); }
    finally { setIntelLoading(false); }
  }, []);

  // Auto-fetch intel when tab switches to "intel"
  useEffect(() => {
    if (viewMode === "intel" && !dailyIntel) fetchDailyIntel();
  }, [viewMode, dailyIntel, fetchDailyIntel]);

  const ns = nsSummary(news);
  const risk: RiskMgmt | null = investmentPlan ? { entry: investmentPlan.entry, stop: investmentPlan.stop_loss, target: investmentPlan.take_profit, size: investmentPlan.position_pct } : null;

  const [mobileMenu, setMobileMenu] = useState(false);

  return (
    <div className="flex flex-col h-screen min-h-screen text-[#F5E6CA] font-[Lato,system-ui,sans-serif]"
      role="application" aria-label="Orallexa Capital Intelligence Dashboard"
      style={{ background: "radial-gradient(ellipse at 30% 0%, #1A1A2E 0%, #0D1117 25%, #0A0A0F 60%, #0A0A0F 100%)" }}>

      {/* Demo Mode Banner */}
      {isDemo && (
        <div className="w-full py-2 text-center text-[10px] font-[Josefin_Sans] font-bold uppercase tracking-[0.2em] shrink-0"
          style={{ background: "linear-gradient(90deg, rgba(212,175,55,0.15), rgba(212,175,55,0.25), rgba(212,175,55,0.15))", color: "#D4AF37", borderBottom: "1px solid rgba(212,175,55,0.3)" }}>
          {zh ? "🎭 演示模式 — 展示数据非实时行情" : "🎭 Demo Mode — Simulated data for demonstration"}
        </div>
      )}

      {/* Offline Banner */}
      {!isOnline && (
        <div className="w-full py-2 text-center text-[10px] font-[Josefin_Sans] font-bold uppercase tracking-[0.2em] shrink-0"
          role="alert"
          style={{ background: "rgba(139,0,0,0.15)", color: "#FF6666", borderBottom: "1px solid rgba(139,0,0,0.3)" }}>
          {zh ? "网络已断开 — 数据可能不是最新的" : "Network offline — data may be stale"}
        </div>
      )}

      <div className="flex flex-col lg:flex-row flex-1 min-h-0">

      {/* ── MOBILE TOP BAR ── */}
      <div className="lg:hidden flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "rgba(212,175,55,0.12)", background: "#0D1117" }}>
        <div className="flex items-center gap-2">
          <BullIcon size={18} />
          <span className="font-[Poiret_One] text-[12px] tracking-[0.2em] shimmer-gold">{t.brand}</span>
        </div>
        <button onClick={() => setMobileMenu(!mobileMenu)} aria-label={mobileMenu ? "Close menu" : "Open menu"} aria-expanded={mobileMenu}
          className="mobile-menu-btn px-3 py-2 text-[#C5A255] text-[14px]" style={{ border: "1px solid rgba(212,175,55,0.2)" }}>
          {mobileMenu ? "✕" : "☰"}
        </button>
      </div>

      {/* ── LEFT SIDEBAR ── */}
      <aside className={`${mobileMenu ? "flex" : "hidden"} lg:flex w-full lg:w-[280px] border-r p-5 space-y-3 flex-col overflow-y-auto max-h-[80vh] lg:max-h-none`}
        role="navigation" aria-label="Controls"
        style={{ borderColor: "rgba(212,175,55,0.12)", background: "linear-gradient(180deg, #0D1117 0%, #0A0A0F 100%)" }}>

        {/* Brand Header with Bull */}
        <div className="pb-4 mb-1 border-b" style={{ borderColor: "rgba(212,175,55,0.15)" }}>
          <div className="flex items-center gap-3">
            <img src="/icon-192.png" alt="" width={22} height={22} style={{ borderRadius: 4 }} />
            <span className="font-[Poiret_One] text-[14px] tracking-[0.3em]"
              style={{ background: "linear-gradient(135deg, #D4AF37, #FFD700, #C5A255)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>{t.brand}</span>
            <span className="text-[9px] font-[Josefin_Sans] font-semibold text-[#006B3F]/70 tracking-[0.12em] uppercase ml-auto">{t.active}</span>
          </div>
          <div className="text-[9px] font-[Josefin_Sans] text-[#6B6E76] tracking-[0.2em] uppercase mt-2 ml-[34px] font-light">{t.subtitle}</div>
        </div>

        <div>
          <label className="block text-[9px] font-[Josefin_Sans] text-[#C5A255] uppercase tracking-[0.2em] mb-1.5 font-semibold">{t.asset}</label>
          <input value={asset} onChange={(e) => setAsset(e.target.value.toUpperCase())}
            aria-label="Ticker symbol" placeholder="NVDA" autoComplete="off" spellCheck={false}
            className="w-full px-3 py-2.5 text-[14px] font-[DM_Mono] font-medium text-[#F5E6CA] outline-none"
            style={{ background: "#2A2A3E", border: "1px solid rgba(212,175,55,0.15)" }}
            onKeyDown={(e) => { if (e.key === "Enter") runSignal(); }} />
          <div className="flex items-center gap-1.5 mt-2">
            <span className="text-[8px] font-[Josefin_Sans] text-[#4A4D55] uppercase tracking-[0.1em]">{zh ? "快速试用" : "Try"}</span>
            {[["NVDA", "AI"], ["TSLA", "EV"], ["QQQ", "Index"]].map(([tk, tag]) => (
              <button key={tk} onClick={() => { setAsset(tk); setTimeout(runSignal, 100); }}
                className="px-2 py-0.5 text-[9px] font-[DM_Mono] font-medium text-[#6B6E76] hover:text-[#D4AF37] hover:bg-[#D4AF37]/8 transition-all"
                style={{ border: "1px solid rgba(212,175,55,0.1)", borderRadius: 3 }}>
                {tk}<span className="text-[7px] text-[#4A4D55] ml-0.5">{tag}</span>
              </button>
            ))}
          </div>
        </div>

        <Mod title={t.engineStatus}>
          <Row label={t.engine} value={t.active} color="#006B3F" />
          <div className="flex items-center justify-between py-[5px]">
            <span className="text-[10px] font-[Josefin_Sans] text-[#6B6E76] uppercase tracking-[0.12em]">{t.strategy}</span>
            <div className="flex gap-1">
              {(["SCALP", "INTRADAY", "SWING"] as const).map((s) => (
                <button key={s} onClick={() => { setStrategy(s); setHorizon(s === "SCALP" ? "5M" : s === "INTRADAY" ? "15M" : "1D"); }}
                  aria-label={`Strategy: ${s}`} aria-pressed={strategy === s}
                  className={`px-2.5 py-1 text-[9px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.08em] transition-colors ${strategy === s ? "text-[#D4AF37] bg-[#D4AF37]/10" : "text-[#4A4D55] hover:text-[#C5A255]"}`}
                  style={{ border: `1px solid ${strategy === s ? "rgba(212,175,55,0.3)" : "rgba(212,175,55,0.08)"}` }}>{t[s.toLowerCase() as keyof typeof t] || s}</button>
              ))}
            </div>
          </div>
          <div className="flex items-center justify-between py-[5px]">
            <span className="text-[10px] font-[Josefin_Sans] text-[#6B6E76] uppercase tracking-[0.12em]">{t.horizon}</span>
            <div className="flex gap-1">
              {(["5M", "15M", "1H", "1D"] as const).map((h) => (
                <button key={h} onClick={() => setHorizon(h)}
                  aria-label={`Horizon: ${h}`} aria-pressed={horizon === h}
                  className={`px-2.5 py-1 text-[9px] font-[DM_Mono] font-medium transition-colors ${horizon === h ? "text-[#D4AF37] bg-[#D4AF37]/10" : "text-[#4A4D55] hover:text-[#C5A255]"}`}
                  style={{ border: `1px solid ${horizon === h ? "rgba(212,175,55,0.3)" : "rgba(212,175,55,0.08)"}` }}>{h}</button>
              ))}
            </div>
          </div>
        </Mod>

        <div>
          <label className="block text-[9px] font-[Josefin_Sans] text-[#C5A255] uppercase tracking-[0.2em] mb-1.5 font-semibold">{t.context}</label>
          <input value={context} onChange={(e) => setContext(e.target.value)} placeholder={t.contextPh}
            className="w-full px-3 py-2.5 text-[11px] font-[Lato] text-[#F5E6CA] placeholder:text-[#4A4D55] outline-none"
            style={{ background: "#2A2A3E", border: "1px solid rgba(212,175,55,0.15)" }} />
        </div>

        {/* Claude AI overlay toggle */}
        <button onClick={() => setUseClaude(!useClaude)} role="checkbox" aria-checked={useClaude}
          aria-label={zh ? "Claude AI 信号优化" : "Claude AI Overlay"}
          className={`w-full flex items-center justify-center gap-2 py-2 text-[9px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.12em] transition-all ${useClaude ? "text-[#D4AF37]" : "text-[#4A4D55] hover:text-[#C5A255]"}`}
          style={{ background: useClaude ? "rgba(212,175,55,0.06)" : "transparent", border: `1px solid ${useClaude ? "rgba(212,175,55,0.25)" : "rgba(212,175,55,0.08)"}` }}>
          <span className={`inline-block w-2 h-2 rounded-sm ${useClaude ? "bg-[#D4AF37]" : "border border-[#4A4D55]"}`} aria-hidden="true" />
          {zh ? "Claude AI 信号优化" : "Claude AI Overlay"}
        </button>

        <GoldRule strength={20} />

        {/* Primary CTA — gold gradient */}
        <button onClick={runSignal} disabled={loading} aria-label="Run signal analysis" aria-busy={loading && !deepLoading}
          data-tooltip={zh ? "快速技术分析 (Ctrl+Enter)" : "Fast technical analysis (Ctrl+Enter)"}
          className="w-full py-3 text-[11px] font-[Josefin_Sans] font-bold uppercase tracking-[0.16em] disabled:opacity-40 disabled:cursor-not-allowed text-[#0A0A0F] transition-all hover:shadow-[0_0_20px_rgba(212,175,55,0.3)]"
          style={{ background: "linear-gradient(135deg, #D4AF37, #FFD700, #C5A255)", border: "1px solid #D4AF37" }}>
          {loading && !deepLoading ? <><span className="inline-block w-3 h-3 border-2 border-[#0A0A0F] border-t-transparent rounded-full anim-spin mr-2" />{t.scanning}</> : <>{t.runSignal}<span className="hidden lg:inline text-[8px] font-[DM_Mono] ml-2 opacity-60">⌘↵</span></>}
        </button>

        {/* Secondary — outlined */}
        <button onClick={runDeep} disabled={loading} aria-label="Run deep intelligence analysis" aria-busy={deepLoading}
          data-tooltip={zh ? "多Agent深度分析 (Ctrl+D)" : "Multi-agent deep analysis (Ctrl+D)"}
          className="w-full py-3 bg-transparent text-[#C5A255] text-[11px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.16em] transition-all hover:text-[#FFD700] hover:shadow-[0_0_15px_rgba(212,175,55,0.15)] disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ border: "1px solid rgba(212,175,55,0.25)" }}>
          {deepLoading ? <><span className="inline-block w-3 h-3 border-2 border-[#C5A255] border-t-transparent rounded-full anim-spin mr-2" />{t.scanning}</> : <>{t.openIntel}<span className="hidden lg:inline text-[8px] font-[DM_Mono] ml-2 opacity-50">⌘D</span></>}
        </button>

        {/* Auto-refresh toggle */}
        <button onClick={() => setAutoRefresh(!autoRefresh)}
          className={`w-full py-2 text-[9px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.14em] transition-all ${autoRefresh ? "text-[#006B3F]" : "text-[#4A4D55] hover:text-[#C5A255]"}`}
          style={{ background: autoRefresh ? "rgba(0,107,63,0.08)" : "transparent", border: `1px solid ${autoRefresh ? "rgba(0,107,63,0.3)" : "rgba(212,175,55,0.08)"}` }}>
          <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 ${autoRefresh ? "bg-[#006B3F] animate-pulse" : "bg-[#4A4D55]"}`} />
          {autoRefresh ? (zh ? "实时刷新 ON (30s)" : "Live Refresh ON (30s)") : (zh ? "实时刷新 OFF" : "Live Refresh OFF")}
        </button>

        <Mod title={t.watchlist}>
          <input value={watchlistInput} onChange={(e) => setWatchlistInput(e.target.value.toUpperCase())} placeholder={t.watchlistPh}
            className="w-full px-3 py-2 text-[10px] font-[DM_Mono] text-[#F5E6CA] placeholder:text-[#4A4D55] outline-none mb-2"
            style={{ background: "#2A2A3E", border: "1px solid rgba(212,175,55,0.15)" }} />
          <button onClick={scanWatchlist} disabled={watchlistLoading}
            className="w-full py-2 text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] disabled:opacity-40 transition-all"
            style={{ background: "rgba(212,175,55,0.08)", border: "1px solid rgba(212,175,55,0.2)", color: "#C5A255" }}>
            {watchlistLoading ? t.scanningAll : t.scanAll}
          </button>
        </Mod>

        <div className="flex-1" />

        <Mod title={t.journal}>
          <div className="text-[10px] font-[Lato] text-[#6B6E76]">{journal.length} {t.recentLog}</div>
          <div onClick={() => setShowFullLog(!showFullLog)} className="mt-1.5 text-[9px] font-[Josefin_Sans] text-[#C5A255]/50 uppercase tracking-[0.12em] cursor-pointer hover:text-[#FFD700] transition-colors">{showFullLog ? (zh ? "收起日志" : "Hide Log") : t.viewLog}</div>
          {showFullLog && journal.length > 0 && (
            <div className="mt-2 space-y-1 max-h-[200px] overflow-y-auto">
              {journal.map((e, i) => (
                <div key={i} className="flex justify-between items-center py-1 border-b last:border-b-0" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
                  <div className="flex flex-col">
                    <span className="text-[10px] font-[Lato] text-[#F5E6CA]/70">{e.ticker} · {e.mode}</span>
                    <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">{e.timestamp}</span>
                  </div>
                  <span className="text-[10px] font-[DM_Mono] font-medium" style={{ color: e.decision === "BUY" ? "#006B3F" : e.decision === "SELL" ? "#8B0000" : "#D4AF37" }}>{e.decision}</span>
                </div>
              ))}
            </div>
          )}
        </Mod>

        <Mod title={t.snapshot}>
          <input type="file" accept="image/png,image/jpeg" onChange={(e) => setChartFile(e.target.files?.[0] ?? null)}
            className="w-full text-[10px] text-[#6B6E76] file:mr-2 file:py-1.5 file:px-3 file:border file:text-[#C5A255] file:text-[10px] file:font-semibold file:uppercase file:cursor-pointer"
            style={{ }} />
          {chartFile && <button onClick={analyzeChart} disabled={loading}
            className="w-full mt-2 py-2 text-[#0A0A0F] text-[10px] font-[Josefin_Sans] font-bold uppercase tracking-[0.1em] disabled:opacity-40"
            style={{ background: "linear-gradient(135deg, #D4AF37, #FFD700)", border: "1px solid #D4AF37" }}>{t.analyzeSnap}</button>}
        </Mod>

        <Mod title={t.voice}>
          <button
            onMouseDown={() => {
              const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
              if (!SR) { setError(t.voiceError); return; }
              const recognition = new SR();
              recognition.lang = lang === "ZH" ? "zh-CN" : "en-US";
              recognition.interimResults = false;
              recognition.onresult = (e: any) => {
                const transcript = e.results[0][0].transcript;
                if (transcript) {
                  setContext((prev) => prev ? `${prev}; ${transcript}` : transcript);
                }
              };
              recognition.onend = () => setIsRecording(false);
              recognition.onerror = () => setIsRecording(false);
              recognition.start();
              setIsRecording(true);
              (window as any).__recognition = recognition;
            }}
            onMouseUp={() => { (window as any).__recognition?.stop(); setIsRecording(false); }}
            onMouseLeave={() => { (window as any).__recognition?.stop(); setIsRecording(false); }}
            className={`w-full py-2 text-[10px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.12em] transition-colors ${isRecording ? "text-[#D4AF37]" : "text-[#6B6E76] hover:text-[#C5A255]"}`}
            style={{ background: isRecording ? "rgba(212,175,55,0.08)" : "#2A2A3E", border: `1px solid ${isRecording ? "rgba(212,175,55,0.4)" : "rgba(212,175,55,0.1)"}` }}>
            {isRecording ? t.listening : t.holdSpeak}
          </button>
        </Mod>
      </aside>

      {/* ── CENTER ── */}
      <main className="flex-1 p-4 lg:p-6 overflow-y-auto" role="main" aria-label="Analysis results">
        {/* Header bar */}
        <div className="flex items-center justify-between mb-4 lg:mb-6 pb-4 border-b" style={{ borderColor: "rgba(212,175,55,0.1)" }}>
          <div className="flex items-center gap-3 lg:gap-6">
            <div className="hidden lg:flex items-center gap-3">
              <BullIcon size={18} />
              <span className="font-[Poiret_One] text-[12px] tracking-[0.28em] shimmer-gold">Orallexa Capital Engine</span>
              <span className="text-[9px] font-[Josefin_Sans] font-semibold text-[#006B3F]/60 uppercase">{t.active}</span>
            </div>
            <div className="h-4 w-px" style={{ background: "rgba(212,175,55,0.15)" }} />
            <div className="flex gap-5">
              {([[t.asset, asset], [t.strategy, strategy], [t.horizon, horizon]] as const).map(([l, v]) => (
                <span key={l} className="text-[9px] font-[Josefin_Sans] text-[#6B6E76] uppercase tracking-[0.16em] font-light">{l}<span className="text-[#F5E6CA] font-medium ml-1.5">{v}</span></span>
              ))}
            </div>
          </div>
          {/* View toggle: Signal | Intel */}
          <div className="flex items-center mr-3" style={{ border: "1px solid rgba(212,175,55,0.15)" }}>
            <button onClick={() => setViewMode("signal")} aria-pressed={viewMode === "signal"}
              className={`px-3 py-2 text-[10px] font-[Josefin_Sans] uppercase tracking-[0.12em] font-semibold transition-colors ${viewMode === "signal" ? "text-[#D4AF37] bg-[#D4AF37]/8" : "text-[#4A4D55] hover:text-[#C5A255]"}`}>{t.signalTab}<span className="hidden lg:inline text-[7px] font-[DM_Mono] ml-1 opacity-40">1</span></button>
            <div className="w-px h-4" style={{ background: "rgba(212,175,55,0.15)" }} />
            <button onClick={() => setViewMode("intel")} aria-pressed={viewMode === "intel"}
              className={`px-3 py-2 text-[10px] font-[Josefin_Sans] uppercase tracking-[0.12em] font-semibold transition-colors ${viewMode === "intel" ? "text-[#D4AF37] bg-[#D4AF37]/8" : "text-[#4A4D55] hover:text-[#C5A255]"}`}>{t.intelTab}<span className="hidden lg:inline text-[7px] font-[DM_Mono] ml-1 opacity-40">2</span></button>
          </div>
          <div className="flex items-center" role="radiogroup" aria-label="Language" style={{ border: "1px solid rgba(212,175,55,0.15)" }}>
            <button onClick={() => setLang("EN")} role="radio" aria-checked={lang === "EN"} aria-label="English"
              className={`px-3 py-2 text-[10px] font-[Josefin_Sans] uppercase tracking-[0.12em] font-semibold transition-colors ${lang === "EN" ? "text-[#D4AF37] bg-[#D4AF37]/8" : "text-[#4A4D55] hover:text-[#C5A255]"}`}>EN</button>
            <div className="w-px h-4" style={{ background: "rgba(212,175,55,0.15)" }} />
            <button onClick={() => setLang("ZH")} role="radio" aria-checked={lang === "ZH"} aria-label="中文"
              className={`px-3 py-2 text-[10px] font-[Josefin_Sans] font-semibold transition-colors ${lang === "ZH" ? "text-[#D4AF37] bg-[#D4AF37]/8" : "text-[#4A4D55] hover:text-[#C5A255]"}`}>中文</button>
          </div>
        </div>

        {/* Connection + timestamp strip */}
        <div className="flex items-center justify-between mb-3 px-1">
          <div className="flex items-center gap-2">
            <div className={`w-1.5 h-1.5 rounded-full ${isOnline ? (apiDead.current ? "bg-[#C5A255]" : "bg-[#006B3F]") : "bg-[#8B0000]"}`} />
            <span className="text-[8px] font-[Josefin_Sans] uppercase tracking-[0.1em]"
              style={{ color: isOnline ? (apiDead.current ? "#C5A255" : "#006B3F") : "#8B0000" }}>
              {!isOnline ? (zh ? "离线" : "Offline") : apiDead.current ? (zh ? "演示模式" : "Demo") : (zh ? "已连接" : "Connected")}
            </span>
          </div>
          {lastAnalyzedAt && (
            <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">
              {zh ? "最近分析" : "Last signal"}: {lastAnalyzedAt}
            </span>
          )}
        </div>

        {error && <div className="border px-4 py-3 mb-4 anim-error" role="alert" style={{ background: "rgba(139,0,0,0.08)", borderColor: "rgba(139,0,0,0.3)" }}>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-[14px] shrink-0" style={{ color: "#8B0000" }}>⚠</span>
              <span className="text-[11px] font-[Lato] text-[#FF6666] truncate">{error}</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button onClick={() => { setError(""); runSignal(); }}
                className="px-3 py-1.5 text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.1em] text-[#D4AF37] hover:text-[#FFD700] transition-colors"
                style={{ border: "1px solid rgba(212,175,55,0.25)", background: "rgba(212,175,55,0.06)" }}>
                {zh ? "重试" : "Retry"}
              </button>
              <button onClick={() => setError("")} className="text-[12px] text-[#8B6E6E] hover:text-[#FF6666] px-1" aria-label="Dismiss error">✕</button>
            </div>
          </div>
        </div>}
        {loading && <div className="border px-4 py-4 mb-4" role="status" aria-live="polite" style={{ background: "rgba(212,175,55,0.04)", borderColor: "rgba(212,175,55,0.15)" }}>
          <div className="flex items-center justify-center gap-3">
            <span className="inline-block w-4 h-4 border-2 border-[#D4AF37] border-t-transparent rounded-full anim-spin" />
            <span className="text-[11px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.2em] shimmer-gold">
              {deepLoading ? (zh ? "深度分析中..." : "Deep analysis running...") : t.bullScan}
            </span>
          </div>
          {deepLoading && <div className="mt-3 space-y-2">
            {deepProgress && (
              <div className="flex items-center justify-center gap-2">
                <span className="text-[10px] font-[DM_Mono] text-[#D4AF37]/60">{deepProgress.step}/{deepProgress.total}</span>
                <span className="text-[10px] font-[Lato] text-[#F5E6CA]/70">{zh ? deepProgress.label_zh : deepProgress.label}</span>
              </div>
            )}
            <div className="flex justify-center gap-0.5">
              {Array.from({ length: 6 }, (_, i) => (
                <div key={i} className="h-1 w-8 rounded-full transition-all duration-500"
                  style={{ background: deepProgress && i < deepProgress.step ? "#D4AF37" : "rgba(212,175,55,0.12)" }} />
              ))}
            </div>
          </div>}
        </div>}

        {viewMode === "signal" ? (<>
          <BreakingBanner signals={breakingSignals} zh={zh} />
          <WatchlistGrid items={watchlistItems} onSelect={(tk) => { setAsset(tk); setWatchlistItems([]); }} />
          <MarketStrip summary={marketSummary} decision={decision} livePrice={livePrice} priceFlash={priceFlash} />
          <DecisionCard d={decision} asset={asset} strategy={strategy} horizon={horizon} news={news} risk={risk} investmentPlan={investmentPlan} t={t} zh={zh} />
        </>) : (<>
          {/* Intel View */}
          {intelLoading && <div className="border px-4 py-4 mb-4 text-center" role="status" style={{ background: "rgba(212,175,55,0.04)", borderColor: "rgba(212,175,55,0.15)" }}>
            <span className="inline-block w-4 h-4 border-2 border-[#D4AF37] border-t-transparent rounded-full anim-spin mr-2" />
            <span className="text-[11px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.2em] shimmer-gold">
              {zh ? "生成每日情报中..." : "Generating daily intel..."}
            </span>
          </div>}
          <DailyIntelView data={dailyIntel} onSelectTicker={(tk) => { setAsset(tk); setViewMode("signal"); }} t={t} zh={zh} />
          {dailyIntel && <div className="mt-3 flex justify-center">
            <button onClick={() => fetchDailyIntel(true)} disabled={intelLoading}
              className="px-4 py-2 text-[9px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.14em] text-[#C5A255] hover:text-[#FFD700] disabled:opacity-40 transition-colors"
              style={{ border: "1px solid rgba(212,175,55,0.2)" }}>
              {intelLoading ? <><span className="inline-block w-3 h-3 border-2 border-[#C5A255] border-t-transparent rounded-full anim-spin mr-2" />{t.refresh}</> : `↻ ${t.refresh}`}
            </button>
          </div>}
        </>)}
      </main>

      {/* ── RIGHT SIDEBAR ── */}
      <aside className="hidden lg:block w-[300px] border-l p-5 space-y-3 overflow-y-auto"
        role="complementary" aria-label="Market intelligence"
        style={{ borderColor: "rgba(212,175,55,0.12)", background: "linear-gradient(180deg, #0D1117 0%, #0A0A0F 100%)" }}>

        <Mod title={t.marketIntel}>
          {news.length > 0 ? news.map((n, i) => (
            n.url ? (
              <a key={i} href={n.url} target="_blank" rel="noopener noreferrer"
                className="group flex justify-between items-center py-[7px] border-b last:border-b-0 cursor-pointer hover:bg-[#D4AF37]/4 transition-colors -mx-1 px-1"
                style={{ borderColor: "rgba(212,175,55,0.06)" }} title={n.title}>
                <div className="pr-2 min-w-0">
                  <span className="text-[11px] font-[Lato] text-[#F5E6CA]/60 leading-snug group-hover:text-[#F5E6CA] transition-colors block truncate font-light">{n.title}</span>
                  {n.provider && <span className="text-[8px] font-[Josefin_Sans] text-[#4A4D55] mt-0.5 block">{n.provider}</span>}
                </div>
                <span className={`text-[9px] font-[Josefin_Sans] font-bold whitespace-nowrap uppercase shrink-0 ${sentCls(n.sentiment)}`}>{n.sentiment}</span>
              </a>
            ) : (
              <div key={i} className="py-[7px] border-b last:border-b-0 -mx-1 px-1" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
                <div className="flex justify-between items-center">
                  <span className="text-[11px] font-[Lato] text-[#F5E6CA]/60 leading-snug pr-2 font-light">{n.title}</span>
                  <span className={`text-[9px] font-[Josefin_Sans] font-bold whitespace-nowrap uppercase shrink-0 ${sentCls(n.sentiment)}`}>{n.sentiment}</span>
                </div>
              </div>
            )
          )) : <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="flex justify-between py-[7px]"><div className="skeleton h-3 w-3/4" /><div className="skeleton h-3 w-12" /></div>)}</div>}
          {news.length > 0 && <div className="mt-2 pt-2 border-t text-[10px] font-[Lato] text-[#6B6E76]" style={{ borderColor: "rgba(212,175,55,0.1)" }}>{t.overall}: <span className="font-semibold" style={{ color: ns.color }}>{ns.label}</span> ({ns.avg.toFixed(2)})</div>}
        </Mod>

        {mlModels.length > 0 && <MLScoreboard models={mlModels} />}

        {deepReport && (<>
          <Mod title={t.marketReport}>
            <div className="text-[11px] font-[Lato] text-[#F5E6CA]/60 leading-relaxed font-light whitespace-pre-line">
              {deepReport.market.split("\n").slice(0, 12).join("\n")}
              {deepReport.market.split("\n").length > 12 && (
                <details className="mt-1.5">
                  <summary className="text-[9px] font-[Josefin_Sans] text-[#C5A255] uppercase tracking-[0.12em] cursor-pointer hover:text-[#FFD700]">Show full report</summary>
                  <div className="mt-1.5">{deepReport.market.split("\n").slice(12).join("\n")}</div>
                </details>
              )}
            </div>
          </Mod>
          <Mod title={t.fundamentals}>
            <div className="text-[11px] font-[DM_Mono] text-[#F5E6CA]/60 leading-relaxed whitespace-pre-line">
              {deepReport.fundamentals.split("\n").slice(0, 10).join("\n")}
              {deepReport.fundamentals.split("\n").length > 10 && (
                <details className="mt-1.5">
                  <summary className="text-[9px] font-[Josefin_Sans] text-[#C5A255] uppercase tracking-[0.12em] cursor-pointer hover:text-[#FFD700]">Show full report</summary>
                  <div className="mt-1.5">{deepReport.fundamentals.split("\n").slice(10).join("\n")}</div>
                </details>
              )}
            </div>
          </Mod>
        </>)}

        {chartInsight && <Mod title={t.chartInsight}>
          {chartInsight.trend && chartInsight.trend !== "—" && <Row label={zh ? "趋势" : "Trend"} value={chartInsight.trend} />}
          {chartInsight.setup && chartInsight.setup !== "—" && <Row label={zh ? "形态" : "Setup"} value={chartInsight.setup} />}
          {chartInsight.levels && chartInsight.levels !== "—" && <Row label={zh ? "支撑/阻力" : "S/R Levels"} value={chartInsight.levels} />}
          {chartInsight.summary && <div className="mt-1 text-[11px] font-[Lato] text-[#F5E6CA]/60 leading-relaxed font-light">{chartInsight.summary}</div>}
        </Mod>}

        <Mod title={t.capitalProfile}>
          {profile ? <>
            <Row label={t.style} value={profile.style} />
            <Row label={t.winRate} value={profile.win_rate} />
            <Row label={t.today} value={profile.today} />
          </> : <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="flex justify-between py-[5px]"><div className="skeleton h-3 w-16" /><div className="skeleton h-3 w-20" /></div>)}</div>}
        </Mod>

        <Mod title={t.executionLog}>
          {journal.length > 0 ? journal.map((e, i) => (
            <div key={i} className="flex justify-between items-center py-[6px] border-b last:border-b-0" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
              <span className="text-[11px] font-[Lato] text-[#6B6E76]">{e.ticker} · {e.mode}</span>
              <span className="text-[11px] font-[DM_Mono] font-medium" style={{ color: decColorJournal(e.decision) }}>{e.decision}</span>
            </div>
          )) : <div className="text-[10px] font-[Lato] text-[#4A4D55]">No executions yet</div>}
          {profile && profile.patterns.length > 0 && (
            <div className="mt-3 pt-3 border-t" style={{ borderColor: "rgba(212,175,55,0.1)" }}>
              <Heading>{t.behaviorSignals}</Heading>
              {profile.patterns.map((p, i) => <div key={i} className="mt-1 text-[10px] font-[Lato] text-[#8B0000]/70">{p}</div>)}
            </div>
          )}
        </Mod>
      </aside>
    </div>{/* end lg:flex-row */}
    </div>
  );
}
