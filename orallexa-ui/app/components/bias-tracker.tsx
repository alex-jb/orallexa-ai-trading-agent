"use client";

import { useState, useEffect } from "react";
import type { BiasProfile } from "../types";
import { API } from "../types";
import { Mod } from "./atoms";

/* ── Accuracy Ring ─────────────────────────────────────────────────── */
function AccuracyRing({ value, label, size = 64 }: { value: number; label: string; size?: number }) {
  const r = (size - 8) / 2;
  const circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - value);
  const color = value >= 0.6 ? "#006B3F" : value >= 0.45 ? "#D4AF37" : "#8B0000";

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(42,42,62,0.8)" strokeWidth="4" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="4"
          strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="butt"
          className="transition-all duration-700" />
      </svg>
      <div className="absolute flex flex-col items-center justify-center" style={{ width: size, height: size }}>
        <span className="text-[14px] font-[DM_Mono] font-bold" style={{ color }}>{(value * 100).toFixed(0)}%</span>
      </div>
      <span className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.14em] text-[#8B8E96]">{label}</span>
    </div>
  );
}

/* ── Calibration Bar ───────────────────────────────────────────────── */
function CalibrationBar({ calibration, t }: { calibration: BiasProfile["calibration"]; t: Record<string, string> }) {
  if (!calibration?.length) return null;
  const maxCount = Math.max(...calibration.map(c => c.count), 1);

  return (
    <div>
      <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.28em] text-[#D4AF37] mb-2">
        {t.biasCalibration}
      </div>
      <div className="space-y-1.5">
        {calibration.map((bucket, i) => {
          const acc = bucket.accuracy;
          const accColor = acc === null ? "#4A4D55" : acc >= 0.6 ? "#006B3F" : acc >= 0.45 ? "#D4AF37" : "#8B0000";
          const barWidth = bucket.count > 0 ? Math.max(8, (bucket.count / maxCount) * 100) : 0;

          return (
            <div key={i} className="flex items-center gap-2">
              <span className="text-[8px] font-[DM_Mono] text-[#8B8E96] w-12 shrink-0">{bucket.range}</span>
              <div className="flex-1 relative h-3" style={{ background: "rgba(42,42,62,0.5)" }}>
                <div className="absolute inset-y-0 left-0 transition-all duration-500"
                  style={{ width: `${barWidth}%`, background: `${accColor}30` }} />
              </div>
              <span className="text-[9px] font-[DM_Mono] w-8 text-right shrink-0" style={{ color: accColor }}>
                {acc !== null ? `${(acc * 100).toFixed(0)}%` : "—"}
              </span>
              <span className="text-[8px] font-[DM_Mono] text-[#4A4D55] w-6 text-right shrink-0">
                n={bucket.count}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Main Bias Tracker Card ─────���──────────────────────────────────── */
export function BiasTrackerCard({ t, zh }: { t: Record<string, string>; zh: boolean }) {
  const [profile, setProfile] = useState<BiasProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(`${API}/api/bias-profile`);
        const data = await r.json();
        if (!cancelled) { setProfile(data); setLoading(false); }
      } catch {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <Mod title={t.biasTracker}>
        <div className="flex items-center gap-2 py-4 justify-center">
          <div className="w-3 h-3 border border-[#D4AF37] border-t-transparent anim-spin" />
          <span className="text-[10px] font-[Lato] text-[#8B8E96]">
            {zh ? "分析预测历史..." : "Analyzing prediction history..."}
          </span>
        </div>
      </Mod>
    );
  }

  if (!profile || profile.status === "error") return null;

  if (profile.status === "insufficient_data") {
    return (
      <Mod title={t.biasTracker}>
        <div className="py-3 text-center">
          <span className="text-[10px] font-[Lato] text-[#8B8E96]">{t.biasInsufficient}</span>
          <div className="text-[9px] font-[DM_Mono] text-[#4A4D55] mt-1">
            {profile.total_evaluated || 0} / {profile.minimum_required || 5} {zh ? "条" : "predictions"}
          </div>
        </div>
      </Mod>
    );
  }

  const overall = profile.overall!;
  const byDir = profile.by_direction!;
  const sevColor = (s: string) => s === "high" ? "#8B0000" : s === "medium" ? "#D4AF37" : "#006B3F";

  return (
    <Mod title={t.biasTracker}>
      {/* Accuracy Rings */}
      <div className="flex justify-around items-start mb-3 py-2">
        <div className="relative flex flex-col items-center">
          <AccuracyRing value={overall.accuracy} label={t.biasAccuracy} />
        </div>
        {byDir.buy.count > 0 && (
          <div className="relative flex flex-col items-center">
            <AccuracyRing value={byDir.buy.accuracy} label={t.biasBuy} />
          </div>
        )}
        {byDir.sell.count > 0 && (
          <div className="relative flex flex-col items-center">
            <AccuracyRing value={byDir.sell.accuracy} label={t.biasSell} />
          </div>
        )}
      </div>

      {/* Stats row */}
      <div className="flex justify-between px-2 py-2 mb-3" style={{ background: "rgba(42,42,62,0.4)" }}>
        <div className="text-center">
          <div className="text-[13px] font-[DM_Mono] font-bold text-[#F5E6CA]">{overall.total}</div>
          <div className="text-[7px] font-[Josefin_Sans] uppercase tracking-[0.14em] text-[#8B8E96]">
            {zh ? "总预测" : "Predictions"}
          </div>
        </div>
        <div className="text-center">
          <div className="text-[13px] font-[DM_Mono] font-bold" style={{ color: overall.avg_return >= 0 ? "#006B3F" : "#8B0000" }}>
            {overall.avg_return >= 0 ? "+" : ""}{(overall.avg_return * 100).toFixed(1)}%
          </div>
          <div className="text-[7px] font-[Josefin_Sans] uppercase tracking-[0.14em] text-[#8B8E96]">
            {zh ? "平均收益" : "Avg Return"}
          </div>
        </div>
        <div className="text-center">
          <div className="text-[13px] font-[DM_Mono] font-bold text-[#F5E6CA]">{overall.forward_days}d</div>
          <div className="text-[7px] font-[Josefin_Sans] uppercase tracking-[0.14em] text-[#8B8E96]">
            {zh ? "前瞻期" : "Forward"}
          </div>
        </div>
      </div>

      {/* Confidence Calibration */}
      <CalibrationBar calibration={profile.calibration} t={t} />

      {/* Ticker breakdown (top 5) */}
      {profile.by_ticker && Object.keys(profile.by_ticker).length > 0 && (
        <div className="mt-3">
          <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.28em] text-[#D4AF37] mb-1.5">
            {zh ? "按标的" : "By Ticker"}
          </div>
          {Object.entries(profile.by_ticker)
            .sort(([, a], [, b]) => b.count - a.count)
            .slice(0, 5)
            .map(([tk, stats]) => {
              const accColor = stats.accuracy >= 0.6 ? "#006B3F" : stats.accuracy >= 0.45 ? "#D4AF37" : "#8B0000";
              return (
                <div key={tk} className="flex items-center justify-between py-[5px] border-b last:border-b-0"
                  style={{ borderColor: "rgba(212,175,55,0.06)" }}>
                  <span className="text-[10px] font-[DM_Mono] font-medium text-[#F5E6CA]">{tk}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-[9px] font-[DM_Mono]" style={{ color: accColor }}>
                      {(stats.accuracy * 100).toFixed(0)}%
                    </span>
                    <span className="text-[8px] font-[DM_Mono] text-[#4A4D55]">n={stats.count}</span>
                    <span className="text-[8px] font-[DM_Mono]"
                      style={{ color: stats.avg_return >= 0 ? "#006B3F" : "#8B0000" }}>
                      {stats.avg_return >= 0 ? "+" : ""}{(stats.avg_return * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
              );
            })}
        </div>
      )}

      {/* Detected Patterns */}
      {profile.patterns && profile.patterns.length > 0 && (
        <div className="mt-3">
          <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.28em] text-[#D4AF37] mb-1.5">
            {t.biasPatterns}
          </div>
          {profile.patterns.map((p, i) => (
            <div key={i} className="flex items-start gap-2 py-1.5 border-b last:border-b-0"
              style={{ borderColor: "rgba(212,175,55,0.06)" }}>
              <span className="text-[8px] font-[Josefin_Sans] font-bold uppercase px-1.5 py-0.5 shrink-0 mt-0.5"
                style={{ color: sevColor(p.severity), background: `${sevColor(p.severity)}15` }}>
                {p.severity}
              </span>
              <span className="text-[9px] font-[Lato] text-[#8B8E96] leading-snug">{p.description}</span>
            </div>
          ))}
        </div>
      )}

      {/* Recommendations */}
      {profile.recommendations && profile.recommendations.length > 0 && (
        <div className="mt-3">
          <div className="text-[8px] font-[Josefin_Sans] font-bold uppercase tracking-[0.28em] text-[#D4AF37] mb-1.5">
            {t.biasRecommendations}
          </div>
          {profile.recommendations.map((rec, i) => (
            <div key={i} className="flex items-start gap-2 py-1">
              <span className="text-[8px] text-[#D4AF37] mt-0.5">◆</span>
              <span className="text-[9px] font-[Lato] text-[#F5E6CA]/70 leading-snug">{rec}</span>
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      {profile.updated_at && (
        <div className="mt-2 pt-2 border-t text-[8px] font-[DM_Mono] text-[#4A4D55] text-right"
          style={{ borderColor: "rgba(212,175,55,0.06)" }}>
          {zh ? "更新于" : "Updated"}: {new Date(profile.updated_at).toLocaleDateString()}
        </div>
      )}
    </Mod>
  );
}
