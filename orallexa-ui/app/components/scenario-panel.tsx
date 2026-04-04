"use client";

import { useState, useEffect } from "react";
import type { ScenarioResult, PerspectivePanel, RoleMemoryStats, SwarmResult } from "../types";
import { API } from "../types";
import { Mod } from "./atoms";

/* ── Preset scenario templates ─────────────────────────────────────── */
const PRESETS_EN = [
  "Fed raises rates by 50bp unexpectedly",
  "China bans AI chip exports to US",
  "NVDA misses earnings by 15%",
  "Major crypto exchange collapse",
  "Oil spikes to $120 on Middle East conflict",
  "Surprise CPI at 6%, well above consensus",
];
const PRESETS_ZH = [
  "美联储意外加息50个基点",
  "中国禁止AI芯片出口美国",
  "NVDA财报不及预期15%",
  "大型加密交易所崩溃",
  "中东冲突导致油价飙升至$120",
  "CPI意外达到6%，远超预期",
];

/* ── Scenario Simulator Card ───────────────────────────────────────── */
export function ScenarioSimulator({ tickers, t, zh }: {
  tickers: string[]; t: Record<string, string>; zh: boolean;
}) {
  const [scenario, setScenario] = useState("");
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [swarm, setSwarm] = useState<SwarmResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const presets = zh ? PRESETS_ZH : PRESETS_EN;

  const runScenario = async () => {
    if (!scenario.trim() || loading) return;
    setLoading(true);
    setError("");
    setResult(null);
    setSwarm(null);
    try {
      const form = new FormData();
      form.append("scenario", scenario);
      form.append("tickers", tickers.join(","));
      const res = await fetch(`${API}/api/scenario`, { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Request failed" }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const scenarioData = await res.json();
      setResult(scenarioData);

      // Auto-trigger swarm simulation with scenario's portfolio impact as shock
      const shock = scenarioData.portfolio_delta_pct || 0;
      const sentMap: Record<string, number> = { "risk-off": -0.6, "risk-on": 0.6, neutral: 0 };
      const sent = sentMap[scenarioData.regime_shift] ?? 0;
      const swarmForm = new FormData();
      swarmForm.append("shock_pct", String(shock));
      swarmForm.append("sentiment", String(sent));
      swarmForm.append("ticker", tickers[0] || "NVDA");
      fetch(`${API}/api/swarm-sim`, { method: "POST", body: swarmForm })
        .then(r => r.json())
        .then(data => setSwarm(data))
        .catch(() => {});
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const dirColor = (d: string) => d === "bullish" ? "#006B3F" : d === "bearish" ? "#8B0000" : "#D4AF37";
  const sevBg = (s: string) => s === "high" ? "rgba(139,0,0,0.12)" : s === "medium" ? "rgba(212,175,55,0.08)" : "rgba(0,107,63,0.06)";

  return (
    <Mod title={t.scenario}>
      {/* Input */}
      <div className="mb-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={scenario}
            onChange={e => setScenario(e.target.value)}
            onKeyDown={e => e.key === "Enter" && runScenario()}
            placeholder={t.scenarioPh}
            className="flex-1 px-3 py-2 text-[11px] font-[Lato] text-[#F5E6CA] placeholder:text-[#4A4D55] outline-none"
            style={{ background: "#2A2A3E", border: "1px solid rgba(212,175,55,0.15)" }}
          />
          <button
            onClick={runScenario}
            disabled={loading || !scenario.trim()}
            className="px-4 py-2 text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] transition-colors"
            style={{
              background: loading ? "rgba(212,175,55,0.1)" : "rgba(212,175,55,0.15)",
              color: loading ? "#8B8E96" : "#D4AF37",
              border: "1px solid rgba(212,175,55,0.25)",
            }}
          >
            {loading ? t.scenarioRunning : t.scenarioRun}
          </button>
        </div>

        {/* Preset chips */}
        <div className="flex flex-wrap gap-1.5 mt-2">
          {presets.map((p, i) => (
            <button key={i} onClick={() => setScenario(p)}
              className="px-2 py-1 text-[8px] font-[Josefin_Sans] uppercase tracking-[0.1em] text-[#8B8E96] hover:text-[#D4AF37] transition-colors"
              style={{ background: "rgba(42,42,62,0.6)", border: "1px solid rgba(212,175,55,0.08)" }}>
              {p.length > 30 ? p.slice(0, 30) + "…" : p}
            </button>
          ))}
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center gap-2 py-4 justify-center">
          <div className="w-3 h-3 border border-[#D4AF37] border-t-transparent anim-spin" />
          <span className="text-[10px] font-[Lato] text-[#8B8E96]">
            {zh ? "AI正在推演场景影响..." : "AI simulating scenario impact..."}
          </span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="py-2 px-3 text-[10px] font-[Lato] text-[#8B0000]"
          style={{ background: "rgba(139,0,0,0.08)", border: "1px solid rgba(139,0,0,0.2)" }}>
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-3">
          {/* Summary */}
          <div className="px-3 py-2" style={{ background: "rgba(42,42,62,0.5)", border: "1px solid rgba(212,175,55,0.08)" }}>
            <div className="text-[11px] font-[Lato] text-[#F5E6CA]/80 leading-relaxed">{result.summary}</div>
            <div className="flex items-center gap-3 mt-2">
              <span className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] px-2 py-0.5"
                style={{
                  color: result.regime_shift === "risk-off" ? "#8B0000" : result.regime_shift === "risk-on" ? "#006B3F" : "#D4AF37",
                  background: result.regime_shift === "risk-off" ? "rgba(139,0,0,0.1)" : result.regime_shift === "risk-on" ? "rgba(0,107,63,0.1)" : "rgba(212,175,55,0.08)",
                }}>
                {result.regime_shift}
              </span>
              <span className="text-[8px] font-[DM_Mono] text-[#8B8E96]">
                {zh ? "置信度" : "Confidence"}: {result.confidence}%
              </span>
            </div>
          </div>

          {/* Portfolio Delta */}
          <div className="flex items-center justify-between px-3 py-2"
            style={{ background: sevBg(Math.abs(result.portfolio_delta_pct) > 3 ? "high" : Math.abs(result.portfolio_delta_pct) > 1 ? "medium" : "low") }}>
            <span className="text-[9px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#8B8E96]">
              {t.scenarioPortfolio}
            </span>
            <span className="text-[18px] font-[DM_Mono] font-bold"
              style={{ color: result.portfolio_delta_pct > 0 ? "#006B3F" : result.portfolio_delta_pct < 0 ? "#8B0000" : "#D4AF37" }}>
              {result.portfolio_delta_pct > 0 ? "+" : ""}{result.portfolio_delta_pct.toFixed(1)}%
            </span>
          </div>

          {/* Per-ticker impacts */}
          <div>
            <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.28em] text-[#D4AF37] mb-2">
              {t.scenarioImpact}
            </div>
            {result.impacts.map((imp, i) => (
              <div key={i} className="flex items-center justify-between py-[6px] border-b last:border-b-0"
                style={{ borderColor: "rgba(212,175,55,0.06)" }}>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-[DM_Mono] font-medium text-[#F5E6CA]">{imp.ticker}</span>
                    <span className="text-[8px] font-[Josefin_Sans] font-bold uppercase px-1.5 py-0.5"
                      style={{ color: dirColor(imp.direction), background: sevBg(imp.severity) }}>
                      {imp.severity}
                    </span>
                  </div>
                  <div className="text-[9px] font-[Lato] text-[#8B8E96] mt-0.5 leading-snug">{imp.reasoning}</div>
                  <div className="flex gap-3 mt-0.5">
                    <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">{imp.time_horizon}</span>
                    {imp.key_level > 0 && (
                      <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">
                        {zh ? "关键位" : "Key"}: ${imp.key_level.toFixed(0)}
                      </span>
                    )}
                  </div>
                </div>
                <div className="text-[16px] font-[DM_Mono] font-bold ml-3 shrink-0"
                  style={{ color: dirColor(imp.direction) }}>
                  {imp.impact_pct > 0 ? "+" : ""}{imp.impact_pct.toFixed(1)}%
                </div>
              </div>
            ))}
          </div>

          {/* Historical Analog */}
          {result.historical_analog?.event && (
            <div className="px-3 py-2" style={{ background: "rgba(42,42,62,0.4)", border: "1px solid rgba(212,175,55,0.06)" }}>
              <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.28em] text-[#D4AF37] mb-1">
                {t.scenarioHistory}
              </div>
              <div className="text-[10px] font-[Lato] text-[#F5E6CA]/70">
                <span className="font-medium text-[#F5E6CA]">{result.historical_analog.event}</span>
                {result.historical_analog.date && (
                  <span className="text-[#4A4D55] ml-1">({result.historical_analog.date})</span>
                )}
              </div>
              <div className="text-[9px] font-[Lato] text-[#8B8E96] mt-1">{result.historical_analog.market_reaction}</div>
            </div>
          )}

          {/* Hedging Suggestions */}
          {result.hedging_suggestions.length > 0 && (
            <div>
              <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.28em] text-[#D4AF37] mb-1">
                {t.scenarioHedge}
              </div>
              {result.hedging_suggestions.map((h, i) => (
                <div key={i} className="flex items-start gap-2 py-1">
                  <span className="text-[8px] text-[#D4AF37] mt-0.5">◆</span>
                  <span className="text-[9px] font-[Lato] text-[#8B8E96]">{h}</span>
                </div>
              ))}
            </div>
          )}

          {/* Swarm Simulation */}
          {swarm && swarm.conviction > 0 && (
            <div className="px-3 py-2" style={{ background: "rgba(42,42,62,0.4)", border: "1px solid rgba(212,175,55,0.06)" }}>
              <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.28em] text-[#D4AF37] mb-2">
                {t.swarmSim} — {t.swarmAgents}
              </div>
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="text-[8px] font-[Josefin_Sans] uppercase text-[#8B8E96] mr-1">{t.swarmConvergence}:</span>
                  <span className="text-[12px] font-[DM_Mono] font-bold"
                    style={{ color: swarm.convergence === "BUY" ? "#006B3F" : swarm.convergence === "SELL" ? "#8B0000" : "#D4AF37" }}>
                    {swarm.convergence}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-[8px] font-[Josefin_Sans] uppercase text-[#8B8E96] mr-1">{t.swarmSpeed}:</span>
                  <span className="text-[10px] font-[DM_Mono] text-[#F5E6CA]">{swarm.convergence_speed}</span>
                </div>
              </div>
              {/* Distribution bar */}
              <div className="flex h-3 w-full overflow-hidden" style={{ border: "1px solid rgba(212,175,55,0.08)" }}>
                <div style={{ width: `${swarm.buy_pct}%`, background: "rgba(0,107,63,0.6)" }} />
                <div style={{ width: `${swarm.mixed_pct}%`, background: "rgba(212,175,55,0.3)" }} />
                <div style={{ width: `${swarm.sell_pct}%`, background: "rgba(139,0,0,0.6)" }} />
              </div>
              <div className="flex justify-between mt-1">
                <span className="text-[7px] font-[DM_Mono] text-[#006B3F]">BUY {swarm.buy_pct}%</span>
                <span className="text-[7px] font-[DM_Mono] text-[#D4AF37]">MIXED {swarm.mixed_pct}%</span>
                <span className="text-[7px] font-[DM_Mono] text-[#8B0000]">SELL {swarm.sell_pct}%</span>
              </div>
              {/* Mini sparkline of convergence path */}
              {swarm.sample_path && swarm.sample_path.length > 2 && (
                <svg width="100%" height="24" viewBox="0 0 100 24" preserveAspectRatio="none" className="mt-1">
                  <line x1="0" y1="12" x2="100" y2="12" stroke="rgba(212,175,55,0.15)" strokeWidth="0.5" />
                  <polyline
                    fill="none"
                    stroke={swarm.convergence === "BUY" ? "#006B3F" : swarm.convergence === "SELL" ? "#8B0000" : "#D4AF37"}
                    strokeWidth="1.5"
                    points={swarm.sample_path.map((p, i) =>
                      `${(i / (swarm.sample_path.length - 1)) * 100},${12 - p.avg_position * 10}`
                    ).join(" ")}
                  />
                </svg>
              )}
            </div>
          )}
        </div>
      )}
    </Mod>
  );
}

/* ── Perspective Panel Card ────────────────────────────────────────── */
export function PerspectivePanelCard({ panel, t }: {
  panel: PerspectivePanel | null; t: Record<string, string>;
}) {
  const [roleStats, setRoleStats] = useState<Record<string, RoleMemoryStats>>({});

  useEffect(() => {
    fetch(`${API}/api/role-memory`)
      .then(r => r.json())
      .then(data => { if (data.roles) setRoleStats(data.roles); })
      .catch(() => {});
  }, []);

  if (!panel || !panel.perspectives?.length) return null;

  const consColor = panel.consensus === "BULLISH" ? "#006B3F" : panel.consensus === "BEARISH" ? "#8B0000" : "#D4AF37";
  const consBg = panel.consensus === "BULLISH" ? "rgba(0,107,63,0.08)" : panel.consensus === "BEARISH" ? "rgba(139,0,0,0.08)" : "rgba(212,175,55,0.06)";
  const biasColor = (b: string) => b === "BULLISH" ? "#006B3F" : b === "BEARISH" ? "#8B0000" : "#D4AF37";

  return (
    <Mod title={t.perspectivePanel}>
      {/* Consensus header */}
      <div className="flex items-center justify-between mb-3 px-2 py-2" style={{ background: consBg }}>
        <div>
          <span className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#8B8E96] mr-2">
            {t.perspectiveConsensus}
          </span>
          <span className="text-[14px] font-[DM_Mono] font-bold" style={{ color: consColor }}>
            {panel.consensus}
          </span>
        </div>
        <div className="text-right">
          <div className="text-[8px] font-[Josefin_Sans] uppercase tracking-[0.14em] text-[#8B8E96]">
            {t.perspectiveAgreement}
          </div>
          <div className="text-[13px] font-[DM_Mono] font-medium text-[#F5E6CA]">
            {panel.agreement}%
          </div>
        </div>
      </div>

      {/* Score bar visualization */}
      <div className="relative h-2 mb-3 mx-1" style={{ background: "rgba(42,42,62,0.8)" }}>
        <div className="absolute top-0 bottom-0 w-px left-1/2" style={{ background: "rgba(212,175,55,0.3)" }} />
        <div
          className="absolute top-0 bottom-0 transition-all duration-500"
          style={{
            left: panel.avg_score >= 0 ? "50%" : `${50 + panel.avg_score / 2}%`,
            width: `${Math.abs(panel.avg_score) / 2}%`,
            background: panel.avg_score > 0
              ? "linear-gradient(90deg, rgba(0,107,63,0.4), rgba(0,107,63,0.8))"
              : "linear-gradient(270deg, rgba(139,0,0,0.4), rgba(139,0,0,0.8))",
          }}
        />
      </div>

      {/* Per-role views */}
      {panel.perspectives.map((p, i) => (
        <div key={i} className="py-[7px] border-b last:border-b-0" style={{ borderColor: "rgba(212,175,55,0.06)" }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-[12px]">{p.icon}</span>
              <span className="text-[10px] font-[Josefin_Sans] font-semibold uppercase tracking-[0.1em] text-[#F5E6CA]">
                {p.role}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[8px] font-[Josefin_Sans] font-bold uppercase px-1.5 py-0.5"
                style={{ color: biasColor(p.bias), background: `${biasColor(p.bias)}15` }}>
                {p.bias}
              </span>
              <span className="text-[11px] font-[DM_Mono] font-medium" style={{ color: biasColor(p.bias) }}>
                {p.score > 0 ? "+" : ""}{p.score}
              </span>
            </div>
          </div>
          <div className="text-[9px] font-[Lato] text-[#8B8E96] mt-1 leading-snug pl-6">{p.reasoning}</div>
          <div className="flex items-center gap-2 mt-0.5 pl-6">
            <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">
              conviction: {p.conviction}%
            </span>
            <span className="text-[8px] font-[Lato] italic text-[#4A4D55]">
              {p.key_factor}
            </span>
            {/* Role memory badge */}
            {roleStats[p.role] && roleStats[p.role].total >= 3 && (() => {
              const rs = roleStats[p.role];
              const accColor = rs.accuracy >= 0.6 ? "#006B3F" : rs.accuracy >= 0.45 ? "#D4AF37" : "#8B0000";
              return (
                <span className="text-[7px] font-[DM_Mono] px-1 py-0.5"
                  style={{ color: accColor, background: `${accColor}12` }}>
                  {(rs.accuracy * 100).toFixed(0)}% ({rs.correct}/{rs.total})
                </span>
              );
            })()}
          </div>
        </div>
      ))}
    </Mod>
  );
}
