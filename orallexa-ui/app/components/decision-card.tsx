"use client";

import { useState } from "react";
import type { Decision, NewsItem, RiskMgmt, InvestmentPlan } from "../types";
import { displayDec, subtitleDec, sigLabel, confLabel, riskLabel, decColor, riskColor, recBg, nsSummary } from "../types";
import { DecoFan, GoldRule, Heading, Toggle, CopyBtn } from "./atoms";

/* ── Probability Bar (Polymarket-inspired) ────────────────────────────── */
function ProbBar({ probs, decision, zh }: { probs: { up: number; neutral: number; down: number }; decision: string; zh: boolean }) {
  const up = Math.round(probs.up * 100);
  const neut = Math.round(probs.neutral * 100);
  const down = Math.round(probs.down * 100);
  const hero = decision === "SELL" ? down : up;
  const heroColor = decision === "SELL" ? "#8B0000" : "#006B3F";
  return (
    <div className="px-8 pb-5">
      <div className="flex items-center gap-4 mb-3">
        <div className="text-[36px] font-[DM_Mono] font-bold leading-none" style={{ color: heroColor }}>{hero}%</div>
        <div className="text-[10px] font-[Josefin_Sans] text-[#8B8E96] uppercase tracking-[0.14em] leading-relaxed">
          {decision === "SELL" ? (zh ? "下跌" : "Downside") : (zh ? "上涨" : "Upside")}<br/>{zh ? "概率" : "Probability"}
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
        <div className="pr-3 border-r" style={{ borderColor: "rgba(212,175,55,0.08)" }}>
          <div className="flex items-center gap-1.5 mb-2">
            <div className="w-2 h-2 rounded-full" style={{ background: "#006B3F" }} />
            <span className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.18em]" style={{ color: "#006B3F" }}>Bull Case</span>
          </div>
          {bull.map((b, i) => (
            <div key={i} className="text-[10px] font-[Lato] text-[#F5E6CA]/65 leading-relaxed font-light mb-1.5 pl-3.5" style={{ borderLeft: "2px solid rgba(0,107,63,0.3)" }}>{b}</div>
          ))}
        </div>
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
            <div className="text-[8px] font-[Josefin_Sans] text-[#8B8E96] uppercase tracking-[0.14em] mb-1">{l}</div>
            <div className="text-[13px] font-[DM_Mono] font-medium text-[#F5E6CA]">{v}</div>
          </div>
        ))}
      </div>
      {plan.key_risks.length > 0 && (
        <div className="px-7 pb-4">
          <div className="text-[8px] font-[Josefin_Sans] text-[#8B8E96] uppercase tracking-[0.14em] mb-1.5">Key Risks</div>
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

/* ── Decision Card ─────────────────────────────────────────────────────── */
export function DecisionCard({ d, asset, strategy, horizon, news, risk, investmentPlan, t, zh }: {
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

          {/* Pixel bull pet — NFT style mascot */}
          <div className="mt-8 mb-6 flex flex-col items-center anim-fade-in">
            <img src="/pixel_bull.png" alt="Orallexa Bull" width={96} height={104} className="mb-4 image-rendering-pixelated" style={{ imageRendering: "pixelated" }} />
            <div className="text-[48px] font-[Poiret_One] leading-none tracking-[0.2em]" style={{ background: "linear-gradient(135deg, rgba(212,175,55,0.12), rgba(255,215,0,0.18), rgba(197,162,85,0.12))", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>{t.standby}</div>
          </div>

          <div className="text-center text-[12px] font-[Josefin_Sans] tracking-[0.12em] mb-2 font-light" style={{ color: "#C5A255" }}>{t.runToBegin}</div>
          <div className="text-center text-[9px] font-[Josefin_Sans] text-[#8B8E96]/70 tracking-[0.08em] mb-1">
            {zh ? "试试 NVDA · TSLA · QQQ — 左侧快速按钮" : "Try NVDA · TSLA · QQQ — quick buttons on the left"}
          </div>
          <div className="flex items-center justify-center gap-2 mt-3 mb-2">
            <span className="h-px w-12" style={{ background: "linear-gradient(90deg, transparent, rgba(212,175,55,0.2))" }} />
            <span className="inline-block w-[4px] h-[4px] rotate-45" style={{ background: "rgba(212,175,55,0.3)" }} />
            <span className="h-px w-12" style={{ background: "linear-gradient(90deg, rgba(212,175,55,0.2), transparent)" }} />
          </div>
        </div>
        <div className="relative grid grid-cols-3 border-t" style={{ borderColor: "rgba(212,175,55,0.08)" }}>
          {[t.signal, t.confidence, t.risk].map((l, i) => (
            <div key={l} className={`py-6 px-4 text-center ${i < 2 ? "border-r" : ""}`} style={{ borderColor: "rgba(212,175,55,0.06)" }}>
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
          <div className="text-[12px] font-[Josefin_Sans] text-[#8B8E96] mt-2 font-light tracking-[0.06em]">{subtitleDec(d.decision, zh)}</div>
        </div>
        <div className="text-[10px] font-[Josefin_Sans] text-[#4A4D55] text-right pt-2 uppercase tracking-[0.16em] leading-relaxed font-light">{asset}<br />{strategy} ({horizon})</div>
      </div>
      <div className="relative px-8 pb-5">
        <div className="text-[13px] font-[Lato] text-[#F5E6CA] leading-relaxed py-3 px-5 font-light border-l-[2px]" style={{ borderColor: "#D4AF37", background: recBg(d.decision) }}>{d.recommendation}</div>
      </div>
      {news.length > 0 && <div className="relative px-8 pb-3 text-[10px] font-[Lato] text-[#8B8E96]">News: <span className="font-semibold" style={{ color: ns.color }}>{ns.label}</span> sentiment ({news.length} headlines)</div>}
      {d.probabilities && <ProbBar probs={d.probabilities} decision={d.decision} zh={zh} />}
      <GoldRule strength={22} />
      <div className="relative grid grid-cols-3 border-t" style={{ borderColor: "rgba(212,175,55,0.1)" }}>
        {[{ h: t.signal, v: sigLabel(d.signal_strength), s: `${d.signal_strength}/100` },
          { h: t.confidence, v: confLabel(d.confidence), s: `${d.confidence.toFixed(0)}%` },
          { h: t.risk, v: riskLabel(d.risk_level), s: d.risk_level, c: riskColor(d.risk_level) },
        ].map((m, i) => (
          <div key={m.h} className={`py-6 px-5 text-center ${i < 2 ? "border-r" : ""}`} style={{ borderColor: "rgba(212,175,55,0.08)" }}>
            <div className="text-[9px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.22em] mb-2 text-[#8B8E96]">{m.h}</div>
            <div className="text-[18px] font-[DM_Mono] font-medium" style={{ color: m.c ?? "#F5E6CA" }}>{m.v}</div>
            <div className="text-[10px] font-[DM_Mono] text-[#4A4D55] mt-1">{m.s}</div>
          </div>
        ))}
      </div>
      <BullBearPanel reasoning={d.reasoning} t={t} />
      {investmentPlan && <InvestmentPlanCard plan={investmentPlan} t={t} />}
      <Toggle label={t.techDetails} open={showTech} onToggle={() => setShowTech(!showTech)}>
        {d.reasoning.filter(r => !r.startsWith("Bull:") && !r.startsWith("Bear:") && !r.startsWith("Judge:")).map((r, i) =>
          <div key={i} className="text-[10px] font-[DM_Mono] text-[#8B8E96] py-0.5">{r}</div>
        )}
      </Toggle>
      {risk && <Toggle label={t.riskMgmt} open={showRisk} onToggle={() => setShowRisk(!showRisk)}>
        <div className="grid grid-cols-4 gap-3">
          {([[t.entry, `$${risk.entry.toFixed(2)}`], [t.stop, `$${risk.stop.toFixed(2)}`], [t.target, `$${risk.target.toFixed(2)}`], [t.size, `${risk.size}`]] as const).map(([l, v]) => (
            <div key={l as string} className="text-center">
              <div className="text-[9px] font-[Josefin_Sans] text-[#8B8E96] uppercase tracking-[0.14em] mb-1">{l}</div>
              <div className="text-[14px] font-[DM_Mono] font-medium text-[#F5E6CA]">{v}</div>
            </div>
          ))}
        </div>
      </Toggle>}
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
